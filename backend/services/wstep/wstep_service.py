"""
MS-WSTEP orchestration: RST -> issued/renewed certificate.

The WSTEP analogue of ``services/scep/scep_service.py`` — protocol
orchestration kept separate from wire-format parsing (``rst_parser.py``),
signature verification (``ws_security.py``), and response construction
(``rstr_builder.py``). Both entry points call
``CAService.sign_csr_from_crypto`` directly for the actual issuance,
following EST's pattern (``api/est_protocol.py``'s ``simpleenroll``/
``simplereenroll``) rather than SCEP's inlined ``x509.CertificateBuilder``
tech debt.
"""
import base64
import logging

from flask import g, has_app_context
import re

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from models import Certificate
from services.ad_connector import renewal_identity
from services.ca.ca_signing import AlreadySuperseded
from services.ca_service import CAService
from services.policy_service import PolicyViolation
from services.protocol_approval import AlreadyIssued
from utils.csr_extensions import extensions_of
from utils.datetime_utils import utc_now
from utils.csr_diagnostics import WEAK_CSR_HASH_ALGORITHMS, weak_csr_hash_algorithm
from utils import key_algorithms
from utils.issuance_defaults import default_issue_key_type
from utils.key_type import validate_enrollment_csr
from utils.request_names import RequestRejected
from utils.san_parse import is_valid_san_email
from utils.upn_san import build_upn_other_name

from . import ws_security

logger = logging.getLogger(__name__)

# AD DN RDN attribute names (as ldap3's parse_dn returns them from a real
# AD distinguishedName) -> the x509.Name attribute OID they map to. Covers
# the components a real ADCS User certificate's directory-path subject
# uses (confirmed in the lab: CN=Roy Hagland, CN=Users, DC=hagland,
# DC=domain) plus the other standard DN attributes AD may plausibly return.
_DN_ATTR_OIDS = {
    'CN': NameOID.COMMON_NAME,
    'OU': NameOID.ORGANIZATIONAL_UNIT_NAME,
    'O': NameOID.ORGANIZATION_NAME,
    'DC': NameOID.DOMAIN_COMPONENT,
    'L': NameOID.LOCALITY_NAME,
    'S': NameOID.STATE_OR_PROVINCE_NAME,
    'ST': NameOID.STATE_OR_PROVINCE_NAME,
    'C': NameOID.COUNTRY_NAME,
}


class HeldForApproval(Exception):
    """A policy holds the request: ``approval`` is the request answering it
    (pending, or decided and not yet delivered)."""

    def __init__(self, approval):
        super().__init__(f'Held for approval #{approval.id}')
        self.approval = approval


def _pass_gate(gate, csr, template, subject, san, signing_cert=None):
    """None when *gate* lets the request through, else the error to answer;
    raises :class:`HeldForApproval` when a policy holds it."""
    if gate is None:
        return None
    from services.protocol_approval import ApprovalGateUnavailable
    try:
        approval = gate(csr=csr, template=template, subject=subject, san=san, signing_cert=signing_cert)
    except ApprovalGateUnavailable:
        return ServerError('Policy evaluation failed')
    if approval is not None:
        raise HeldForApproval(approval)
    return None


class ServerError(str):
    """An error message for a failure on the CA's side, faulted as SOAP env:Receiver (HTTP 500)."""


# One text for an unknown realm and a disabled profile: the client learns nothing of the profiles
REALM_NOT_SERVED = "The requester's realm is not served"
NOT_IN_GROUP = 'Requester is not authorized to enroll against this {what}'


def _x509_name_from_dn_components(dn_components, email=None):
    """Build an x509.Name from AD DN RDN components (attr, value) pairs.

    ``dn_components`` arrives leaf-to-root (AD's own ``distinguishedName``
    string order, e.g. ``[('CN', 'Roy Hagland'), ('CN', 'Users'), ('DC',
    'hagland'), ('DC', 'domain')]``) -- but ``x509.Name`` expects attributes
    in root-to-leaf (DER SEQUENCE) order and reverses internally for RFC4514
    display. Confirmed empirically: building ``x509.Name`` directly from
    AD's leaf-first order produces ``rfc4514_string()`` == "DC=domain,
    DC=hagland,CN=Users,CN=Roy Hagland" -- backwards from the real
    ADCS-issued cert's own "CN=Roy Hagland, CN=Users, DC=hagland,
    DC=domain". The components must be reversed here, once, or every
    AD-derived user subject silently comes out RDN-reversed.

    ``email``, when given, is appended last (i.e. most-specific/leaf-most
    in RFC4514 display: "E=roy.hagland@hagland.domain,CN=Roy
    Hagland,..."), the conventional placement for an emailAddress RDN.
    Optional -- see ``lookup_user_ad_identity``'s docstring for why a
    missing AD ``mail`` attribute must never block subject derivation.

    None if any DN component's attribute type isn't recognized -- fail
    closed rather than silently dropping or mis-mapping a component real
    ADCS would have included.
    """
    attrs = []
    for attr_name, value in reversed(dn_components):
        oid = _DN_ATTR_OIDS.get(attr_name.upper())
        if oid is None:
            logger.warning(
                "AD Connector: unrecognized DN attribute %r building subject "
                "from AD -- refusing to derive a partial subject", attr_name,
            )
            return None
        attrs.append(x509.NameAttribute(oid, value))
    if not attrs:
        return None
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    return x509.Name(attrs)

# Why a SHA-1 CSR fails is_signature_valid, and what to tell the client about
# it, is written once in utils/csr_diagnostics — EST had the same copy.
_WEAK_CSR_HASH_ALGORITHMS = WEAK_CSR_HASH_ALGORITHMS
_weak_csr_hash_algorithm = weak_csr_hash_algorithm


def _is_naked_csr(csr):
    """No CN and no SubjectAlternativeName at all -- what real Windows GPO
    machine autoenrollment deliberately submits for machine templates,
    trusting the CA to derive the subject from AD (see
    ``issue``'s ``kerberos_principal`` handling and
    ``services/ad_connector/lookup.py``). Factored out of ``_validate_csr``
    so ``issue()`` can check the same condition directly, rather than
    string-matching ``_validate_csr``'s error message."""
    cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    has_cn = bool(cn_attrs and str(cn_attrs[0].value).strip())
    return not has_cn and _san_values(csr) is None


def _validate_csr(csr, require_pop=True, allow_naked_subject=False):
    """Similar to EST's ``_validate_est_csr``: proof of possession,
    subject identity present, key-strength policy. Reimplemented locally
    rather than extracted into a shared module, matching the existing
    precedent that EST and SCEP each keep their own copy.

    Two deliberate differences from EST:

    - ``require_pop=False`` skips the self-signature check. Real Windows
      "Full PKCS#7" requests (see ``rst_parser._unwrap_pkcs7_csr``) embed
      a PKCS#10 CertificationRequest whose own self-signature does not
      reliably verify — proof of possession there comes from the *outer*
      CMS SignedData's signature instead, checked separately by
      ``_verify_pkcs7_pop`` (``issue()``). A renewal, already authenticated by
      the old certificate, takes either proof for a new key (``_new_key_proof``).
    - An empty Subject is accepted when the CSR carries a
      SubjectAlternativeName instead (SAN-only identity is standard
      modern TLS practice).

    ``allow_naked_subject``: skip the "must have CN or SAN" check -- set by
    ``issue()``, which refuses a naked CSR itself once it knows whether the
    AD Connector built a subject. Every other check (PoP, key strength)
    still applies unconditionally regardless of this flag.

    Returns an error string, or None if the CSR is acceptable.
    """
    # Key policy before proof of possession: a FIPS provider without ML-DSA
    # cannot verify such a request, whose refusal must name FIPS, not PoP.
    key_err = validate_enrollment_csr(csr)
    if key_err:
        return key_err
    if require_pop:
        try:
            signature_valid = csr.is_signature_valid
        except Exception:
            signature_valid = False
        if not signature_valid:
            weak_algo = _weak_csr_hash_algorithm(csr)
            if weak_algo:
                return (
                    f'CSR signed with an unsupported hash algorithm ({weak_algo}); '
                    'use SHA-256 or stronger'
                )
            return 'CSR signature invalid (proof of possession failed)'

    if not allow_naked_subject and _is_naked_csr(csr):
        return 'CSR subject must include a non-empty CN or a SubjectAltName'

    return None


def _verify_pkcs7_pop(csr, outer_signed_data):
    """Proof of possession for a PKCS#7/CMC-wrapped CSR, via the outer
    envelope's own CMS signature — see ``rst_parser.ParsedRST.outer_signed_data``.

    Confirmed against a real Windows client request captured from the lab
    (2026-08-09, win11.hagland.domain -> ucm2.vm.hagland.home): real
    CertEnroll "Full PKCS#7" requests embed no certificate at all (the
    outer SignedData's ``certificates`` is empty) — the sole SignerInfo
    identifies itself purely via a ``subjectKeyIdentifier`` that is the
    RFC 5280 §4.2.1.2 method-1 SKI (SHA-1 of the SubjectPublicKeyInfo) of
    the *same* key as the inner CSR, and the CMS signature verifies
    directly against that CSR's own public key. So the outer signature
    genuinely proves possession of the CSR's private key, just not via a
    certificate the way SCEP's equivalent check does.

    Without this, ``issue()``'s UsernamePassword/Kerberos-bound paths
    (and both renewal paths for a new key) had no cryptographic proof at all
    that a PKCS#7-wrapped CSR's submitter controlled the CSR's private key. A holder of the shared
    UsernamePassword credential could submit any public key — one they
    don't control — and receive a UCM-issued certificate binding it to
    whatever subject the CSR (or an AD-derived override) requested.

    Returns an error string, or None if the envelope proves possession.
    """
    from fips_mode import FipsRestricted
    from services.scep.message_parser import verify_cms_signature

    try:
        signer_infos = list(outer_signed_data['signer_infos'])
    except Exception:
        return 'Invalid PKCS#7 envelope'
    if not signer_infos:
        return 'PKCS#7 envelope has no signature'

    try:
        csr_pubkey = csr.public_key()
    except Exception:
        return 'Unsupported CSR public key'
    expected_ski = x509.SubjectKeyIdentifier.from_public_key(csr_pubkey).digest
    # A renewal also carries the renewed certificate's SignerInfo, and DER
    # sorts a SET OF by encoding: the request key's may come in any position
    signer_info, named_by_key = None, False
    for candidate in signer_infos:
        try:
            sid = candidate['sid']
            if sid.name != 'subject_key_identifier':
                continue
            named_by_key = True
            if sid.chosen.native == expected_ski:
                signer_info = candidate
                break
        except Exception:
            return 'Invalid PKCS#7 envelope'
    if not named_by_key:
        return 'PKCS#7 envelope does not identify itself by the request key'
    if signer_info is None:
        return 'PKCS#7 envelope signer does not match the CSR public key'

    try:
        verify_cms_signature(outer_signed_data, csr_pubkey, signer_info=signer_info)
    except FipsRestricted as e:
        logger.warning("WSTEP: request envelope refused in FIPS mode: %s", e)
        return f'PKCS#7 envelope refused: {e}'
    except Exception as e:
        logger.warning("WSTEP: request envelope signature check failed: %s", e)
        return 'PKCS#7 envelope signature invalid (proof of possession failed)'

    return None


def _san_values(cert_or_csr):
    """SAN entries as a set of (type, value) pairs — mirrors EST's
    ``_san_values``, order/criticality irrelevant to identity match."""
    try:
        ext = extensions_of(cert_or_csr).get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return None
    return {(type(name).__name__, str(getattr(name, 'value', name))) for name in ext.value}


def _san_matches(signing_cert, csr):
    """Mirrors EST's ``_reenroll_san_matches``: a CSR without SAN is
    accepted (tolerant of clients that omit it), but a CSR that does
    include SAN must match the signing certificate's SAN exactly."""
    csr_sans = _san_values(csr)
    if csr_sans is None:
        return True
    cert_sans = _san_values(signing_cert) or set()
    return csr_sans == cert_sans


def _load_csr(csr_der):
    try:
        return x509.load_der_x509_csr(csr_der), None
    except Exception:
        return None, 'Invalid CSR encoding'


def _match_template(ca, csr, principal=None, *, profile):
    """The template a request is issued under: the one it names (``_named_template``),
    else the best match of its requested EKUs against the CA's advertised
    templates (the same set XCEP's GetPolicies exposed).

    The EKU match is the fallback for requests naming no template; XCEP announces
    each template's extension (1.3.6.1.4.1.311.21.7) so that CertEnroll names it.

    This is a real limitation, not a corner case: two templates can
    legitimately want the same EKU (e.g. "Web Server" and "VPN Server"
    both want serverAuth-only), and ties break on lowest template id —
    arbitrary but deterministic. Returns ``(template, refusal)``: the matched
    ``CertificateTemplate`` row or ``None`` if nothing matches at all, and a
    refusal when the request's EKUs match only a template its key does not fit
    (family, curve or size). A template the key does not fit that scores 0 is no match:
    the request falls back to no template, which is safe because the Enroll
    ACL and pinned fields then fall back to every template of the CA (a CA
    offering none is refused by the callers).

    ``principal`` (Kerberos binding): the templates of its kind (a computer, or
    a user, generalFlags) are matched first, as a Windows client only offers those.
    ``profile``: the Windows enrollment profile served, whose template list narrows the CA's.

    Callers use the matched row three ways: its policy OID (via
    ``_template_oid_for``) for the issued cert's
    ``ms_certificate_template_oid`` — a real Windows client fails
    CX509Enrollment::Enroll with CERTSRV_E_PROPERTY_EMPTY when the cert
    carries no Certificate Template extension — and its own configured
    EKUs (``_template_extra_ekus``) as both ``extra_ekus`` and the
    ``template_ekus`` that replace the request's.
    """
    named, refusal, has_name = _named_template(ca, csr, profile=profile)
    if has_name:
        return named, refusal

    try:
        from models import CertificateTemplate
        from services.xcep.policy_builder import _resolve_templates_for_ca
    except Exception:
        return None, None

    all_active = CertificateTemplate.query.filter_by(is_active=True).all()
    candidates = [t for t in _resolve_templates_for_ca(ca, all_active, profile=profile)
                  if _template_key_type(t, ca.id) is not None]
    if not candidates:
        return None, None

    csr_eku = _eku_oids(csr) or set()

    # The match is made among the templates the request key fits (a P-384 key
    # is not issued under a P-256 template sharing its EKUs); a request whose
    # EKUs name only a template of another key is refused.
    csr_label = _csr_key_label(csr)
    same = [t for t in candidates if _template_takes_key(t, csr_label, ca.id)]
    if principal:
        from services.ad_connector.lookup import is_machine_principal
        other_kind = 'directory' if is_machine_principal(principal) else 'machine'
        best, _score = _best_eku_match([t for t in same if _subject_source(t) != other_kind], csr_eku)
        if best is not None:
            return best, None
    best, _score = _best_eku_match(same, csr_eku)
    if best is not None:
        return best, None
    other, score = _best_eku_match([t for t in candidates if t not in same], csr_eku)
    if other is not None and score > 0:
        return None, _key_refusal(other, csr_label, ca.id)
    return None, None


# szOID_ENROLL_CERTTYPE_EXTENSION (MS-WCCE 2.2.2.7.7.1): the template's name
_ENROLL_CERTTYPE_OID = x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2')


def _template_identifiers(csr):
    """``(OID, name)`` of the template the request names, each None when absent;
    ValueError for an unreadable one."""
    from asn1crypto import core as asn1_core

    extensions = extensions_of(csr)
    oid = name = None
    try:
        oid = extensions.get_extension_for_class(x509.MSCertificateTemplate).value.template_id.dotted_string
    except x509.ExtensionNotFound:
        pass
    try:
        raw = extensions.get_extension_for_oid(_ENROLL_CERTTYPE_OID).value.value
    except x509.ExtensionNotFound:
        return oid, None
    value = asn1_core.load(raw)
    if not isinstance(value, (asn1_core.BMPString, asn1_core.UTF8String)) or not value.native.strip():
        raise ValueError('certificate template name')
    return oid, value.native.strip()


def _named_template(ca, csr, *, profile):
    """``(template, refusal, named)`` for the template the request names by OID or
    name (MS-WCCE 3.2.2.6.2.1.4.1): an identifier this CA does not offer, two that
    disagree, or EKUs or a key the template does not issue are refused."""
    from services.xcep.policy_builder import _policy_oid_for_template

    try:
        oid, name = _template_identifiers(csr)
    except (TypeError, ValueError):
        return None, 'Invalid certificate template extension in the request', True
    if oid is None and name is None:
        return None, None, False
    offered = _ca_templates(ca, profile=profile)
    found = []
    if oid is not None:
        cas = _policy_oid_cas(ca, profile=profile)
        by_oid = [t for t in offered if oid in {_policy_oid_for_template(c, t) for c in cas}]
        if not by_oid:
            return None, f'Certificate template {oid} is not offered by this CA', True
        found.append(by_oid[0])
    if name is not None:
        by_name = [t for t in offered if (t.name or '').casefold() == name.casefold()]
        if not by_name:
            return None, f"Certificate template '{name}' is not offered by this CA", True
        if len(by_name) > 1:
            return None, f"Certificate template name '{name}' is ambiguous", True
        found.append(by_name[0])
    if len({t.id for t in found}) > 1:
        return None, 'The request names two different certificate templates', True
    template = found[0]
    csr_label = _csr_key_label(csr)
    if not _template_takes_key(template, csr_label, ca.id):
        return None, _key_refusal(template, csr_label, ca.id), True
    allowed = set(_template_configured_ekus(template))
    if allowed and (_eku_oids(csr) or set()) - allowed:
        return None, (f"Template '{template.name}' does not issue the Extended Key Usages "
                      'the request asks for'), True
    return template, None, True


def _policy_oid_cas(ca, *, profile):
    """The CAs whose policy OIDs a request may name: *ca*, and the profile's policy CA when set apart."""
    from models import CA
    refid = profile.policy_ca_refid if profile is not None else None
    xcep_ca = CA.query.filter_by(refid=refid).first() if refid and refid != ca.refid else None
    return [ca, xcep_ca] if xcep_ca is not None else [ca]


def _template_oid_for(ca, template, wanted, *, profile):
    """The template OID a certificate carries: ``wanted`` when it is one of the template's,
    else the one XCEP announces (another CA's on a split setup), which autoenrollment looks for."""
    from services.xcep.policy_builder import _policy_oid_for_template
    cas = _policy_oid_cas(ca, profile=profile)
    if wanted is not None and wanted in {_policy_oid_for_template(c, template) for c in cas}:
        return wanted
    return _policy_oid_for_template(cas[-1], template)


_POLICY_OID_SHAPE = re.compile(r'1\.3\.6\.1\.4\.1\.311\.21\.8\.\d+\.\d+\.\d+\.\d+\.1\.(\d+)')


def _template_id_of_policy_oid(oid):
    """The template id a UCM-shaped policy OID ends with, None otherwise; the prefix is not checked."""
    m = _POLICY_OID_SHAPE.fullmatch(oid or '')
    return int(m.group(1)) if m else None


def _template_ext_oid(cert_or_csr):
    try:
        return extensions_of(cert_or_csr).get_extension_for_class(
            x509.MSCertificateTemplate).value.template_id.dotted_string
    except (x509.ExtensionNotFound, ValueError):
        return None


def _eku_oids(cert_or_csr):
    """Dotted EKU OIDs, or None without an ExtendedKeyUsage extension."""
    try:
        return {oid.dotted_string
                for oid in extensions_of(cert_or_csr).get_extension_for_class(x509.ExtendedKeyUsage).value}
    except x509.ExtensionNotFound:
        return None


def _renewal_template(ca, renewed_cert, csr, *, profile):
    """``(template, extra_ekus, issued_ekus, refusal)`` for a renewal. As in AD CS, a
    renewal keeps the template named in the renewed certificate (MS-CRTD
    certificateTemplate) and issues its EKUs (``issued_ekus`` replaces the CSR's);
    a request asking for more is refused."""
    csr_eku = _eku_oids(csr) or set()
    try:
        template_oid = renewed_cert.extensions.get_extension_for_class(
            x509.MSCertificateTemplate).value.template_id.dotted_string
    except x509.ExtensionNotFound:
        template_oid = None

    if template_oid is None:
        # Older certificate without the extension: matched from the request as
        # on issuance, but never beyond the EKUs it already carries
        matched, refusal = _match_template(ca, csr, profile=profile)
        if refusal:
            return None, [], None, refusal
        if matched is not None and issues_only_capped_ekus(matched):
            return None, [], None, _capped_only_refusal(matched)
        if matched is None and not _ca_templates(ca, profile=profile):
            return None, [], None, ServerError('This CA offers no certificate template')
        extra = _template_extra_ekus(matched)
        prior = _eku_oids(renewed_cert)
        if prior is None:
            return matched, extra, None, None
        if csr_eku - prior:
            return None, [], None, ('Renewal cannot add Extended Key Usages the certificate '
                                    'being renewed does not carry')
        # A broader template is not stamped (the next renewal would inherit its
        # EKUs): the renewal is then at par with the certificate's own EKUs
        if set(extra) - prior or not extra:
            return None, [oid for oid in extra if oid in prior], _issuable_ekus(prior), None
        return matched, extra, extra, None

    # The OID was derived from one of this instance's CAs (the XCEP CA of the time, which
    # xcep_ca_refid may no longer name); another instance's prefix names no template here
    from models import CA
    from services.xcep.policy_builder import _policy_oid_for_template
    template_id = _template_id_of_policy_oid(template_oid)
    template = next((t for t in _ca_templates(ca, profile=profile) if t.id == template_id), None)
    if template is not None and template_oid not in {
            _policy_oid_for_template(c, template) for c in CA.query.all()}:
        template = None
    if template is None:
        return None, [], None, ('The certificate template of the certificate being renewed '
                                'is not offered by this CA')
    if issues_only_capped_ekus(template):
        return None, [], None, _capped_only_refusal(template)
    if not _template_takes_key(template, _csr_key_label(csr), ca.id):
        return None, [], None, _key_refusal(template, _csr_key_label(csr), ca.id)
    extra = _template_extra_ekus(template)
    # The request may name what XCEP advertised (capped EKUs included, dropped at
    # issuance); a template without EKUs keeps the renewal within the old ones
    allowed = set(_template_configured_ekus(template)) or _eku_oids(renewed_cert)
    if allowed is not None and csr_eku - allowed:
        other, _refusal = _match_template(ca, csr, profile=profile)
        asked = (f"template '{other.name}'" if other is not None and other.id != template.id
                 else 'other Extended Key Usages')
        return None, [], None, f"Renewal stays on template '{template.name}'; the request asks for {asked}"
    return template, extra, extra or None, None


def _issuable_ekus(prior):
    """The EKUs of a renewed certificate a renewal may carry over: valid, never a capped one."""
    from utils.eku_validation import MAX_EKU_COUNT, PROTOCOL_UNBINDABLE_EKU_OIDS, validate_oid
    kept = [oid for oid in sorted(prior)
            if oid not in PROTOCOL_UNBINDABLE_EKU_OIDS and validate_oid(oid) is None]
    return kept[:MAX_EKU_COUNT] or None


def _ca_templates(ca, *, profile):
    """Active templates offered by *ca* to *profile*, as XCEP advertises them."""
    from models import CertificateTemplate
    from services.xcep.policy_builder import _resolve_templates_for_ca
    return _resolve_templates_for_ca(ca, CertificateTemplate.query.filter_by(is_active=True).all(),
                                     profile=profile)


def _best_eku_match(candidates, csr_eku):
    """(best template, its score), (None, -1) when none scores 0 or more."""
    best, best_score = None, -1
    for template in candidates:
        # Same resolver as issuance: the template is scored on the purposes
        # it will really issue, whatever spelling it uses
        template_eku = set(_template_extra_ekus(template))
        # A template whose EKUs are all capped (OCSP Signing) would score 0 against a bare
        # request: only a request asking for one of them matches it, and is then refused
        configured = set(_template_configured_ekus(template))
        if configured and not template_eku and not csr_eku & configured:
            continue
        score = len(csr_eku & template_eku) - len(template_eku - csr_eku)
        if score > best_score or (score == best_score and best is not None and template.id < best.id):
            best, best_score = template, score
    return (best, best_score) if best is not None and best_score >= 0 else (None, -1)


def _template_key_type(template, ca_id=None):
    """The key label *template* issues, its own or the default; None (logged) when it names
    none and the policies allow no default: the template is then left out, not the CA."""
    if template.key_type:
        return template.key_type
    try:
        return default_issue_key_type(ca_id, template_id=template.id)
    except PolicyViolation as exc:
        # One line per template and request: the filter, label and refusal helpers all ask
        seen = g.setdefault('_wstep_left_out', set()) if has_app_context() else set()
        if template.id not in seen:
            seen.add(template.id)
            logger.warning("WSTEP: template %r left out: %s", template.name, exc)
        return None


def _template_key_label(template, ca_id=None):
    label = _template_key_type(template, ca_id)
    alg = key_algorithms.get(label) if label else None
    return alg.label if alg is not None else str(template.key_type)


def _key_refusal(template, csr_label, ca_id=None):
    if _template_key_type(template, ca_id) is None:
        return (f"Template '{template.name}' names no key type and the issuance policies "
                'allow no default one')
    return f"Template '{template.name}' issues {_template_key_label(template, ca_id)} keys, not {csr_label}"


def _template_takes_key(template, csr_label, ca_id=None):
    """Whether a key of ``csr_label`` fits ``template``: same curve or ML-DSA
    set, an RSA key at least as long. An unknown key fits any non-ML-DSA template;
    no key fits a template whose default key the policies refuse."""
    label = _template_key_type(template, ca_id)
    if label is None:
        return False
    wanted = key_algorithms.get(label)
    got = key_algorithms.get(csr_label)
    if wanted is None:
        return True
    if got is None:
        return wanted.family != 'ML-DSA'
    if wanted.family != got.family:
        return False
    if wanted.family == 'RSA':
        return got.key_size >= wanted.key_size
    return got.label == wanted.label


def _csr_key_label(csr):
    info = key_algorithms.post_quantum_info(csr.public_key_algorithm_oid)
    if info is not None:
        return info.label
    public_key = csr.public_key()
    return (key_algorithms.label_for_public_key(public_key)
            or key_algorithms.key_algo_for_public_key(public_key))


def _template_extra_ekus(template):
    """The EKU OIDs (dotted strings) an admin configured on ``template``,
    for the ``extra_ekus`` kwarg of ``CAService.sign_csr_from_crypto``.

    Upstream's CSR-EKU cap (security audit v2.203 item #3) caps whatever
    EKU a CSR carries to what the resolved ``cert_type`` permits, and never
    honours Microsoft Smartcard Logon from a CSR's own EKU extension at
    all, regardless of cert_type — an operator who wants it has to pass it
    explicitly. WSTEP has no cert_type granular enough to express "whatever
    this specific template needs" (a CA can mix serverAuth-only and
    Smartcard-Logon templates), so it passes the matched template's own
    configured EKUs here instead: extra_ekus is merged in uncapped, since
    it's exactly the admin intent the cap is designed to still allow.
    Returns ``[]`` for ``None``/an unconfigured template.
    """
    from utils.eku_validation import PROTOCOL_UNBINDABLE_EKU_OIDS
    # Same cap as the other protocol endpoints, Smartcard Logon excepted:
    # issuing it is what WSTEP templates are for (AD-bound identities)
    capped = PROTOCOL_UNBINDABLE_EKU_OIDS - {'1.3.6.1.4.1.311.20.2.2'}
    oids = []
    for oid in _template_configured_ekus(template):
        if oid in capped:
            logger.warning('WSTEP: template %s EKU %s is never issued to an enrollee; dropped',
                           template.id, oid)
            continue
        oids.append(oid)
    return oids


_CLIENT_AUTH = '1.3.6.1.5.5.7.3.2'
_SMARTCARD_LOGON = '1.3.6.1.4.1.311.20.2.2'


def issues_only_capped_ekus(template):
    """Whether every EKU ``template`` configures is capped: signed, it would fall back to
    the server profile, so it is neither announced nor issued under."""
    from utils.eku_validation import PROTOCOL_UNBINDABLE_EKU_OIDS
    configured = set(_template_configured_ekus(template))
    return bool(configured) and configured <= PROTOCOL_UNBINDABLE_EKU_OIDS - {_SMARTCARD_LOGON}


def _capped_only_refusal(template):
    return (f"Template '{template.name}' configures only Extended Key Usages "
            'this service does not issue')


def _template_profile(template, csr):
    """(cert_type, Key Usage names or None) the trunk signs ``csr`` under: as in AD CS,
    an S/MIME or EFS template and a Smartcard Logon one keep keyEncipherment, and a
    user template's CN (jdoe) names no host. Templates with serverAuth stay server ones;
    a request without Key Usage gets the one the template configures."""
    try:
        extensions_of(csr).get_extension_for_class(x509.KeyUsage)
        csr_ku = True
    except x509.ExtensionNotFound:
        csr_ku = False
    from utils.eku_validation import PROTOCOL_UNBINDABLE_EKU_OIDS
    from utils.request_names import cert_type_for_ekus
    configured = None if csr_ku else (_template_configured_ku(template) or None)
    # The EKUs the certificate gets (_template_extra_ekus), typed as SCEP types its own
    ekus = set(_template_configured_ekus(template)) - (PROTOCOL_UNBINDABLE_EKU_OIDS - {_SMARTCARD_LOGON})
    cert_type = cert_type_for_ekus(ekus)
    if cert_type == 'client_cert' and _SMARTCARD_LOGON in ekus and ekus <= {_CLIENT_AUTH, _SMARTCARD_LOGON}:
        return cert_type, configured or (None if csr_ku else ['digitalSignature', 'keyEncipherment'])
    return cert_type, configured


def _template_configured_ku(template):
    """The Key Usage names ``template`` configures, [] when none."""
    import json

    try:
        parsed = json.loads(getattr(template, 'extensions_template', None) or '{}')
    except (TypeError, ValueError):
        return []
    names = parsed.get('key_usage') if isinstance(parsed, dict) else None
    return [n for n in names if isinstance(n, str)] if isinstance(names, list) else []


def _template_configured_ekus(template):
    """Every EKU OID ``template`` configures, as XCEP advertises them, before the protocol cap."""
    import json

    if template is None:
        return []
    try:
        parsed = json.loads(template.extensions_template or '{}')
    except (TypeError, ValueError):
        return []
    names = parsed.get('extended_key_usage') if isinstance(parsed, dict) else None
    if not isinstance(names, list):
        return []
    # One resolver for every spelling (the UI writes msSmartcardLogin, the
    # XCEP policy smartcardLogon): a template that issued correctly on the
    # issue form issues the same purposes over WSTEP
    from utils.eku_validation import normalize_extra_ekus
    oids = []
    for name in names:
        if not isinstance(name, str):
            continue
        resolved, err = normalize_extra_ekus([name])
        if err or not resolved:
            # An unknown name is dropped, the others still apply
            logger.warning('WSTEP: template %s EKU %r ignored (%s)', template.id, name, err)
            continue
        if resolved[0] not in oids:
            oids.append(resolved[0])
    return oids


def _required_enroll_acl_groups(ca, matched_template, *, profile):
    """The AD group(s) whose membership satisfies the Enroll ACL for this
    issuance attempt, as a de-duplicated list -- empty if nothing is
    restricted.

    When ``_match_template`` found a specific template, only that
    template's own ``allowed_ad_group`` applies (if set): a confident
    match (a populated CSR whose EKU set scored best against exactly one
    template) is unambiguous.

    When it found nothing (``matched_template is None``), this falls back
    to every ``allowed_ad_group`` set across all templates resolvable for
    this CA. This matters because ``matched_template is None`` is not a
    rare edge case here -- it's what *every* naked CSR from real Windows
    GPO machine autoenrollment produces, since a naked CSR carries no EKU
    extension at all and therefore scores negative against any template
    that declares EKUs (see ``_match_template``'s docstring), and it names
    no template either (311.21.7 or 311.20.2).
    Silently treating "no match" as "no gate" would mean the Enroll ACL
    never actually applies to unattended autoenrollment -- the primary
    scenario it exists to restrict -- so an unmatched naked CSR must
    satisfy ANY restricted template's group instead of none of them.

    A group set on ``profile`` replaces the templates' for every issuance of it (A3).
    """
    from services.windows_profiles import profile_group
    group = profile_group(profile)
    if group:
        return [group]
    if matched_template is not None:
        return [matched_template.allowed_ad_group] if matched_template.allowed_ad_group else []

    candidates = _ca_templates(ca, profile=profile)
    groups = []
    seen = set()
    for template in candidates:
        group = template.allowed_ad_group
        if group and group not in seen:
            seen.add(group)
            groups.append(group)
    return groups


_PINNED_FIELD_OIDS = {
    'C': NameOID.COUNTRY_NAME,
    'ST': NameOID.STATE_OR_PROVINCE_NAME,
    'L': NameOID.LOCALITY_NAME,
    'O': NameOID.ORGANIZATION_NAME,
    'OU': NameOID.ORGANIZATIONAL_UNIT_NAME,
}
# Conventional root-to-leaf order (x509.Name's own storage/DER order --
# see _x509_name_from_dn_components's docstring) for the pinned block,
# ahead of whatever CN/DC/E= attributes remain.
_PINNED_FIELD_ORDER = ['C', 'ST', 'L', 'O', 'OU']


def _template_pinned_fields(template):
    """``{field: value}`` for a template's ``pinned_subject_fields`` JSON
    column, filtered to the known pinnable keys (O/OU/C/ST/L -- never CN)
    with a truthy value. ``{}`` for no template, no column value, or
    unparseable JSON -- never raises. A profile's column reads the same way."""
    if not template or not template.pinned_subject_fields:
        return {}
    try:
        import json
        raw = json.loads(template.pinned_subject_fields)
    except (TypeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in _PINNED_FIELD_OIDS and v and isinstance(v, str)}


def _required_pinned_subject_fields(ca, matched_template, *, profile):
    """Pinned O/OU/C/ST/L values to force onto this WSTEP issuance's
    subject, overriding whatever the client's CSR (or AD-derivation)
    supplied for that specific field -- CN/SAN are never touched here.

    Mirrors ``_required_enroll_acl_groups``'s template-resolution shape: a
    confident ``_match_template`` result trusts only that template's own
    pins, while an unmatched CSR (typically naked -- see that function's
    docstring for why this is the common case for GPO autoenrollment, not
    an edge case) falls back to every template resolvable for this CA.

    Unlike Enroll ACL's groups, though, pinned field *values* can't be
    OR'd across multiple fallback candidates -- there's no "any of these
    satisfies" semantics for "what should O actually be." If two
    CA-resolvable candidates pin the same field to different values, that
    field is skipped (not enforced) and a warning is logged, rather than
    silently picking a winner an admin never chose. Non-conflicting
    fields, and CN/SAN, still apply normally.

    Fields pinned on ``profile`` replace the templates' for every issuance of it (A3).
    """
    # Decided on the parsed result: a profile pinning nothing usable keeps the templates' pins
    fields = _template_pinned_fields(profile)
    if fields:
        return fields
    if matched_template is not None:
        return _template_pinned_fields(matched_template)

    candidates = _ca_templates(ca, profile=profile)

    seen = {}
    for template in candidates:
        for field, value in _template_pinned_fields(template).items():
            seen.setdefault(field, set()).add(value)

    result = {}
    for field, values in seen.items():
        if len(values) == 1:
            result[field] = next(iter(values))
        else:
            logger.warning(
                "WSTEP pinned subject fields: conflicting values for %r "
                "across CA-wide candidate templates (%r) -- skipping",
                field, sorted(values),
            )
    return result


def _merge_pinned_subject_fields(subject, pinned_fields):
    """Rebuilds ``subject`` (an ``x509.Name``) with ``pinned_fields``' RDNs
    forced in, replacing any existing attribute of the same type and
    leaving everything else (CN, DC components, E=...) untouched and in
    its existing relative position. ``x509.Name`` is immutable, so this
    always rebuilds the full attribute list -- same approach as
    ``_x509_name_from_dn_components``. No-op (returns ``subject``
    unchanged) when ``pinned_fields`` is empty."""
    if not pinned_fields:
        return subject
    pinned_oids = {_PINNED_FIELD_OIDS[f] for f in pinned_fields}
    remaining = [attr for attr in subject if attr.oid not in pinned_oids]
    pinned_attrs = [
        x509.NameAttribute(_PINNED_FIELD_OIDS[f], pinned_fields[f])
        for f in _PINNED_FIELD_ORDER if f in pinned_fields
    ]
    return x509.Name(pinned_attrs + remaining)


def _user_ad_derivation_enabled(ca, *, profile):
    """Whether any template resolvable for ``ca`` has opted into
    AD-derived user subjects (``CertificateTemplate.ad_derived_subject``).

    Deliberately independent of ``_match_template``: a naked CSR (the only
    kind this applies to without a matched template, see ``_directory_subject``)
    usually names no template and carries no EKU extension, so it scores
    negative against any candidate template that declares EKUs at all. This
    only asks "did an admin opt any template into AD-derivation for this CA,"
    mirroring how the machine branch has no template dependency either.
    """
    candidates = _ca_templates(ca, profile=profile)
    return any(getattr(t, 'ad_derived_subject', False) for t in candidates)


def _template_validity(template, default_days):
    """The matched template's validity, which XCEP advertises; *default_days* without one."""
    days = getattr(template, 'validity_days', None)
    return int(days) if days else default_days


def _subject_source(template):
    """'machine', 'directory' or 'request': who names the subject of ``template``
    on the Kerberos binding, as its announced subjectNameFlags say."""
    from services.xcep.policy_builder import (
        CT_FLAG_ENROLLEE_SUPPLIES_SUBJECT, is_machine_template, subject_name_flags)
    if subject_name_flags(template) & CT_FLAG_ENROLLEE_SUPPLIES_SUBJECT:
        return 'request'
    return 'machine' if is_machine_template(template) else 'directory'


def _directory_subject(ca, template, csr, principal, sam_account_name, connector, *, profile):
    """``(override_subject, override_san, refusal)`` for a Kerberos-bound request.

    A template whose subject is built by the CA (MS-WCCE 3.2.2.6.2.1.4.5.9: the CA
    MUST ignore the request's subject) takes it from AD, never from the CSR, and
    only for its kind of principal. A naked CSR, or one matching no template, is
    built from AD too: only a matched template announcing a client-supplied
    subject keeps the request's. A template's common name pattern replaces the CN alone."""
    from services.ad_connector import lookup

    is_machine = lookup.is_machine_principal(principal)
    source = _subject_source(template) if template is not None else None
    if source == 'machine' and not is_machine:
        return None, None, f"Template '{template.name}' is issued to computers, not users"
    if source == 'directory' and is_machine:
        return None, None, f"Template '{template.name}' is issued to users, not computers"

    naked = _is_naked_csr(csr)
    built_by_ca = source in ('machine', 'directory') or (source is None and not naked)
    if not (naked or built_by_ca):
        return None, None, None

    patterned = template if _cn_pattern_applies(template) else None
    subject, san, reached = None, None, True
    unresolved = 'could not resolve the requester'
    if sam_account_name and is_machine:
        if patterned is not None:
            computer = lookup.lookup_computer_identity(connector, sam_account_name)
            dns_hostname = computer['dns_hostname'] if computer else computer
        else:
            dns_hostname = lookup.lookup_computer_dns_hostname(connector, sam_account_name)
        reached = dns_hostname is not lookup.UNREACHABLE
        if dns_hostname:
            subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns_hostname)])
            # MS-WCCE: the dNSHostName is the DNS SAN; a CSR without SAN gets it from the CN
            san = [x509.DNSName(dns_hostname)] if _san_values(csr) is not None else None
            if patterned is not None:
                subject, refusal = _machine_pattern_subject(patterned, computer, profile=profile)
                if refusal:
                    return None, None, refusal
                # The CN no longer names the host: the SAN it implied is given as such
                san = san if san is not None else _cn_implied_dns_san(patterned, csr, dns_hostname)
    elif sam_account_name and (source == 'directory' or _user_ad_derivation_enabled(ca, profile=profile)):
        subject, san = _user_directory_subject(connector, sam_account_name, patterned, profile=profile)
        if isinstance(subject, _PatternRefusal):
            return None, None, str(subject)
        if subject is lookup.UNREACHABLE:
            reached, subject = False, None
        elif subject is lookup.NO_UPN:
            subject, unresolved = None, 'found the account but it has no userPrincipalName'
        elif subject is _UNUSABLE_DN:
            subject, unresolved = None, "found the account but could not read its directory path"
        elif subject is None:
            unresolved = 'found no account for the requester'

    # The requester is not at fault when the directory cannot answer: env:Receiver
    if subject is None and not reached:
        return None, None, ServerError('The directory that builds the certificate subject could not be reached')
    if subject is None and built_by_ca and not naked:
        if template is None and sam_account_name and not is_machine:
            return None, None, 'The request matches no certificate template whose subject it may supply'
        return None, None, f'The certificate subject is built from Active Directory, which {unresolved}'
    return subject, san, None


_UNUSABLE_DN = object()


class _PatternRefusal(str):
    """The requester's directory object cannot fill the template's common name pattern."""


def _cn_pattern_applies(template):
    """Whether ``template`` carries a common name pattern for a subject the CA builds."""
    return (template is not None and bool(getattr(template, 'subject_cn_pattern', None))
            and _subject_source(template) in ('machine', 'directory'))


def _pattern_subject(template, values, dn_components, email=None):
    """``(x509.Name, None)`` built from ``template``'s pattern, or ``(None, refusal)``.

    The rendered value is one CN attribute, never parsed as a DN; with
    ``subject_cn_keep_path`` the object's DN follows, its own leaf RDN replaced."""
    from services.wstep import cn_pattern
    name, why = cn_pattern.render(template.subject_cn_pattern, values)
    if why:
        return None, _PatternRefusal(f"Template '{template.name}' cannot build its common name: {why}")
    if not template.subject_cn_keep_path:
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]), None
    subject = (_x509_name_from_dn_components([('CN', name)] + list(dn_components[1:]), email=email)
               if dn_components else None)
    if subject is None:
        return None, _PatternRefusal(f"Template '{template.name}' cannot build its common name: "
                                     'the directory path of the requester cannot be read')
    return subject, None


def _common_values(dn_components, profile):
    from services.wstep import cn_pattern
    return {'domain': cn_pattern.domain_of_dn(dn_components or []), 'realm': getattr(profile, 'realm', None)}


def _machine_pattern_subject(template, computer, *, profile):
    """The patterned subject of a computer from ``lookup_computer_identity``'s answer."""
    sam = computer.get('sam_account_name') or ''
    values = dict(_common_values(computer.get('dn_components'), profile),
                  hostname=sam[:-1] if sam.endswith('$') else sam, fqdn=computer.get('dns_hostname'))
    return _pattern_subject(template, values, computer.get('dn_components'))


def _user_pattern_subject(template, identity, email, *, profile):
    """The patterned subject of a user from ``lookup_user_ad_identity``'s answer; ``email``
    is its mail once validated, kept in the subject only with the directory path."""
    values = dict(_common_values(identity['dn_components'], profile),
                  username=identity.get('sam_account_name'), upn=identity.get('upn'), mail=email,
                  displayName=identity.get('display_name'), givenName=identity.get('given_name'),
                  surname=identity.get('surname'))
    return _pattern_subject(template, values, identity['dn_components'], email=email)


def _cn_implied_dns_san(template, csr, dns_hostname):
    """The SAN that ``CN=<dns_hostname>`` gives a request without SAN in ``TrustStoreService.sign_csr``
    (``cn_implied_names``, then the template's SAN types), for a CN that no longer is the host."""
    from services.template_service import allowed_san_types, san_type_of
    from utils.request_names import cn_implied_names
    cert_type, _ku = _template_profile(template, csr)
    implied = cn_implied_names(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns_hostname)]), cert_type)
    allowed = allowed_san_types(template)
    return [n for n in implied if allowed is None or san_type_of(n) in allowed]


def _user_directory_subject(connector, sam_account_name, patterned=None, *, profile):
    """(subject, SAN) from the AD user object: its DN, its UPN, its mail when valid;
    (``lookup.UNREACHABLE``, None) when the directory could not answer, (``lookup.NO_UPN``, None)
    when the account has no userPrincipalName, (:class:`_PatternRefusal`, None) when the
    ``patterned`` template's common name cannot be built."""
    from services.ad_connector import lookup

    identity = lookup.lookup_user_ad_identity(connector, sam_account_name)
    if identity is lookup.UNREACHABLE:
        return identity, None
    if identity is lookup.NO_UPN:
        return identity, None
    if not identity:
        return None, None
    # AD's mail attribute is optional -- validated (not just truthy) before use,
    # since it's untrusted directory data reaching a certificate subject/SAN.
    email = identity.get('mail')
    if email and not is_valid_san_email(email):
        logger.warning("AD Connector: ignoring malformed mail attribute %r for %r",
                       email, sam_account_name)
        email = None
    if patterned is not None:
        subject, refusal = _user_pattern_subject(patterned, identity, email, profile=profile)
        if refusal:
            return refusal, None
    else:
        subject = _x509_name_from_dn_components(identity['dn_components'], email=email)
    if subject is None:
        return _UNUSABLE_DN, None
    san = [build_upn_other_name(identity['upn'])]
    if email:
        san.append(x509.RFC822Name(email))
    return subject, san


def issue(ca, csr_der, validity_days, source='wstep', require_pop=True, kerberos_principal=None,
          outer_signed_data=None, gate=None, on_stored=None, *, profile):
    """UsernamePassword- or Kerberos-bound initial enrollment. Returns
    (cert_pem, error).

    ``require_pop=False`` is passed by ``wstep_protocol.py`` when the CSR
    was unwrapped from a PKCS#7/CMC envelope (``ParsedRST.was_pkcs7_wrapped``)
    — see ``_validate_csr`` for why that inner CSR's self-signature can't
    be relied on for real Windows clients. ``outer_signed_data`` (also only
    passed in that case — ``ParsedRST.outer_signed_data``) is verified via
    ``_verify_pkcs7_pop`` instead, so a PKCS#7-wrapped CSR is never accepted
    with no proof of possession at all.

    ``kerberos_principal``: the authenticated Kerberos principal, e.g.
    ``'WIN11$@HAGLAND.DOMAIN'`` (machine) or ``'roy.hagland@HAGLAND.DOMAIN'``
    (user) -- passed *only* by the Kerberos-bound CES route (never the
    UsernamePassword one, which has no Kerberos identity to give, and whose
    XCEP policy announces a client-supplied subject for every template).
    The subject then follows the template's announced subjectNameFlags (see
    ``_directory_subject``): a machine template takes ``CN=<dnsHostName>``
    and that DNS name as SAN, a "Build subject from Active Directory"
    template the user's directory-path DN plus its ``userPrincipalName``
    (and ``mail`` when valid) as SAN, whatever the CSR asks, and each refuses
    the other kind of principal; a template's ``subject_cn_pattern`` replaces that CN
    alone (``_pattern_subject``), the SAN and SID staying. A naked CSR (see ``_is_naked_csr``), or one
    matching no template, is built the same way, as GPO autoenrollment expects;
    a user's only when a template opted in (``_user_ad_derivation_enabled``).
    Only a matched template announcing a client-supplied subject keeps the CSR's.
    Derivation never fails open: a naked CSR falls through to the normal
    rejection, a populated one under a CA-built template or none is refused.

    ``profile``: the Windows enrollment profile serving the request; a Kerberos principal is
    issued only by the enabled profile of its own realm, with that profile's connector.

    Enroll ACL: see ``_required_enroll_acl_groups`` for exactly which
    template's ``allowed_ad_group`` applies (the matched template's own,
    or -- for an unmatched/naked CSR -- every restricted template
    resolvable for ``ca``). If that set is non-empty, ``kerberos_principal``
    must resolve to a sam_account_name that ``lookup.is_member_of_group``
    confirms is a member of at least one of them (nested groups included)
    -- otherwise issuance is refused with a fault, not silently downgraded.
    UsernamePassword-bound calls (``kerberos_principal=None``) are never
    gated, since that path authenticates a single shared SystemConfig
    credential with no per-request principal to check membership for.

    Strong certificate mapping (KB5014754): whenever ``kerberos_principal``
    resolves to a sam_account_name AND the AD Connector is configured and
    enabled, the requester's own AD SID is embedded as the SID security
    extension (see ``services/trust_store/csr_operations_mixin.py``'s
    ``_ad_security_extension``) -- matching real ADCS's own automatic
    behavior, unlike every other AD Connector feature here, this is
    unconditional rather than a per-template opt-in, and independent of
    whether the CSR is naked. If the AD Connector isn't configured/enabled
    at all, this simply doesn't apply (no error) -- but if it IS enabled
    and the principal is of another realm, names no account, or the SID
    lookup for this specific request fails for any reason, issuance is
    refused rather than silently issuing a weaker-mapped cert.
    UsernamePassword-bound calls never get this either, same reason as
    Enroll ACL: no per-request principal to resolve a SID for.
    """
    csr, err = _load_csr(csr_der)
    if err:
        return None, err

    override_subject = None
    override_san = None
    kerberos_sam_account_name = None
    requester_sid = None
    connector = None
    if kerberos_principal:
        from services.ad_connector import lookup
        from services.windows_profiles import kerberos_route, profile_connector

        # The route resolved the profile; an approval replays it: both must still be the realm's own
        routed, _realm, _refusal = kerberos_route(kerberos_principal)
        if profile is None or routed is None or routed.id != profile.id or not profile.enabled:
            return None, REALM_NOT_SERVED
        connector = profile_connector(profile)
        # An enabled connector that cannot resolve the requester refuses: issuing anyway
        # would drop the SID extension (KB5014754) and the Enroll ACL's account.
        account = lookup.connector_account(connector, kerberos_principal)
        if account is lookup.UNREACHABLE:
            logger.warning("WSTEP: the AD Connector cannot resolve %r: %s", kerberos_principal,
                           lookup.connector_config_fault(connector) or 'its settings changed')
            return None, ServerError(renewal_identity.UNRESOLVED_MESSAGE)
        if account is lookup.FOREIGN_REALM:
            # sAMAccountName is unique only within its domain: never look it up in another
            logger.warning("WSTEP: Kerberos principal %r is not of the AD Connector's realm",
                           kerberos_principal)
            return None, "The requester's realm is not served by the directory connector"
        if account is lookup.NO_ACCOUNT:
            return None, "The requester's principal names no directory account"
        kerberos_sam_account_name = account

    # Strong certificate mapping (KB5014754): the authenticated requester's AD SID goes into
    # the SID security extension, as AD CS does, whatever the template and the CSR's subject.
    # With the connector off there is no account (no extension); with it on, a failed lookup refuses.
    if kerberos_sam_account_name:
        requester_sid = lookup.lookup_object_sid(connector, kerberos_sam_account_name)
        if not requester_sid:
            logger.warning(
                "WSTEP: could not resolve requester SID for %r via AD "
                "Connector -- refusing issuance (strong certificate mapping)",
                kerberos_sam_account_name,
            )
            if requester_sid is lookup.UNREACHABLE:
                return None, ServerError(renewal_identity.UNRESOLVED_MESSAGE)
            if requester_sid is lookup.UNUSABLE_SID:
                return None, 'The requester has no usable directory identity'
            return None, renewal_identity.NOT_FOUND_MESSAGE

    err = _validate_csr(csr, require_pop=require_pop, allow_naked_subject=True)
    if err:
        return None, err

    if outer_signed_data is not None:
        err = _verify_pkcs7_pop(csr, outer_signed_data)
        if err:
            return None, err

    matched_template, refusal = _match_template(ca, csr, kerberos_principal, profile=profile)
    if refusal:
        return None, refusal
    if matched_template is not None and issues_only_capped_ekus(matched_template):
        return None, _capped_only_refusal(matched_template)
    # No active template offered (pins all off, or none active at all): nothing would carry an Enroll ACL
    if matched_template is None and not _ca_templates(ca, profile=profile):
        return None, ServerError('This CA offers no certificate template')
    template_oid = None
    if matched_template is not None:
        template_oid = _template_oid_for(ca, matched_template, _template_ext_oid(csr), profile=profile)

    if kerberos_principal:
        override_subject, override_san, refusal = _directory_subject(
            ca, matched_template, csr, kerberos_principal, kerberos_sam_account_name, connector,
            profile=profile)
        if refusal:
            return None, refusal
        # Without EKUs the default profile would give serverAuth to the name the request chose
        if (override_subject is None and matched_template is not None
                and _subject_source(matched_template) == 'request'
                and not _template_extra_ekus(matched_template)):
            return None, ServerError(f"Template '{matched_template.name}' lets the request name "
                                     'its subject but configures no Extended Key Usage')
    if override_subject is None and _is_naked_csr(csr):
        return None, 'CSR subject must include a non-empty CN or a SubjectAltName'

    # Pinned subject fields ("hybrid subject template"): O/OU/C/ST/L an
    # admin has forced onto this template, overriding whatever the client's
    # own CSR (or the AD-derivation above) supplied for that specific
    # field -- CN/SAN stay dynamic either way. Applies to every WSTEP
    # issuance path (Kerberos-bound naked or manually-typed CSR, and
    # UsernamePassword-bound alike), unlike Enroll ACL, since pinning
    # doesn't need a per-request AD identity, just the matched template's
    # own static config. Runs after _validate_csr above, so it can never
    # rescue an otherwise-rejected fully-naked CSR into being issuable --
    # it only ever overlays onto a request whose subject is already valid.
    pinned_fields = _required_pinned_subject_fields(ca, matched_template, profile=profile)
    if pinned_fields:
        base_subject = override_subject if override_subject is not None else csr.subject
        override_subject = _merge_pinned_subject_fields(base_subject, pinned_fields)

    # Enroll ACL: only gates the Kerberos-bound path -- the UsernamePassword
    # path authenticates a single shared SystemConfig credential, not a
    # per-request principal, so there's no identity here to check group
    # membership for. See _required_enroll_acl_groups for why an unmatched
    # (typically naked) CSR checks against every restricted template for
    # the CA rather than being skipped. With the connector off there is no
    # sam_account_name and a restricted template is denied, never skipped:
    # this is a security gate, not a best-effort convenience lookup.
    if kerberos_principal:
        required_groups = _required_enroll_acl_groups(ca, matched_template, profile=profile)
        allowed, unreachable = False, False
        for group in (required_groups if kerberos_sam_account_name else []):
            answer = lookup.is_member_of_group(connector, kerberos_sam_account_name, group)
            if answer:
                allowed = True
                break
            unreachable = unreachable or answer is lookup.UNREACHABLE
        if required_groups and not allowed:
            logger.warning(
                "WSTEP Enroll ACL: principal %r denied (requires membership in one of %r)",
                kerberos_principal, required_groups,
            )
            if unreachable:
                return None, ServerError('The directory could not be reached to check enrollment rights')
            # Names what required the group: the profile's replaces the template's
            from services.windows_profiles import profile_group
            return None, NOT_IN_GROUP.format(what='profile' if profile_group(profile) else 'template')

    # The approval gate sees the subject and names the certificate will carry
    err = _pass_gate(gate, csr, matched_template,
                     override_subject if override_subject is not None else csr.subject, override_san)
    if err:
        return None, err

    cert_type, template_ku = _template_profile(matched_template, csr)
    try:
        cert_pem, _serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=csr, validity_days=_template_validity(matched_template, validity_days),
            source=source, require_pop=require_pop,
            ms_certificate_template_oid=template_oid,
            override_subject=override_subject,
            override_san=override_san,
            requester_sid=requester_sid,
            # Upstream's CSR-EKU cap (see _template_extra_ekus) never
            # honours Microsoft Smartcard Logon from a CSR's own EKU
            # extension, whatever cert_type is — extra_ekus is the only
            # way a Smartcard Logon template still issues correctly.
            extra_ekus=_template_extra_ekus(matched_template),
            # As in AD CS and on renewal, the template's EKUs replace the request's
            template_ekus=_template_extra_ekus(matched_template) or None,
            policy_template_id=getattr(matched_template, 'id', None),
            template_id=getattr(matched_template, 'id', None),
            cert_type=cert_type, template_key_usage=template_ku, on_stored=on_stored,
            windows_profile_id=getattr(profile, 'id', None),
        )
    except PolicyViolation as e:  # the route logs the refusal it answers
        return None, f'Policy violation: {e}'
    except RequestRejected as e:
        logger.warning('WSTEP issue refused: %s', e)
        return None, str(e)
    except AlreadyIssued:
        raise
    except Exception as e:
        logger.error('WSTEP issue failed: %s', e)
        return None, ServerError('Certificate issuance failed')

    return cert_pem, None


def signed_request_certificate(security_header, csr_element):
    """``(cert, error)``: the certificate whose key signs the RST (WS-Security XML-DSig), once
    the signature verifies and covers the CSR. ``csr_element``: see ``rst_parser.ParsedRST``
    and ``ws_security.SignedContent`` for why ``csr_der`` alone is not trusted."""
    try:
        signing_cert_der, signed_content = ws_security.verify_signed_request(security_header)
    except ws_security.WSSecurityError as e:
        return None, str(e)
    if not signed_content.covers(csr_element):
        return None, 'CSR is not covered by the request signature'
    try:
        return x509.load_der_x509_certificate(signing_cert_der), None
    except Exception:
        return None, 'Invalid signing certificate'


def tls_client_certificate(client_cert_pem):
    """``(cert, error)`` of the TLS client certificate a renewal on the Certificate binding needs."""
    if not client_cert_pem:
        return None, 'Renewal requires the certificate being renewed as TLS client certificate'
    try:
        return x509.load_pem_x509_certificate(
            client_cert_pem.encode() if isinstance(client_cert_pem, str) else client_cert_pem), None
    except Exception:
        return None, 'Invalid client certificate'


def renew(ca, signing_cert, csr_der, validity_days, source='wstep', require_pop=True,
          outer_signed_data=None, gate=None, *, profile):
    """Certificate-bound renewal: the RST is signed with the client's current certificate's
    private key, ``signing_cert`` from ``signed_request_certificate``. Returns (cert_pem, error).

    ``require_pop``: see ``issue()``; renewal RSTs can arrive PKCS#7/CMC-
    wrapped too. The WS-Security signature proves the current key; a new key
    in a wrapped request proves itself through ``outer_signed_data``.
    """
    db_cert, err = _renewable_certificate(ca, signing_cert)
    if err:
        return None, err

    csr, err = _load_csr(csr_der)
    if err:
        return None, err
    if not require_pop:
        err = _new_key_proof(csr, signing_cert, outer_signed_data)
        if err:
            return None, err
    return _sign_renewal(ca, signing_cert, db_cert, csr, validity_days, source, require_pop, gate=gate,
                         profile=profile)


def _new_key_proof(csr, renewed_cert, outer_signed_data):
    """None when the CSR keeps the renewed key, or the new key proves itself by the
    CSR's self-signature or a SignerInfo of its own. Key policy first."""
    err = _validate_csr(csr, require_pop=False)
    if err:
        return err
    try:
        same_key = csr.public_key() == renewed_cert.public_key()
    except Exception:
        return 'Unsupported public key'
    if same_key:
        return None
    try:
        if csr.is_signature_valid:
            return None
    except Exception:
        pass
    if outer_signed_data is None:
        return 'Renewal with a new key requires its proof of possession'
    return _verify_pkcs7_pop(csr, outer_signed_data)


def renew_with_client_certificate(ca, client_cert, csr_der, outer_signed_data, validity_days,
                                  source='wstep', gate=None, *, profile):
    """Renewal on the Certificate binding as Windows sends it: authenticated by the TLS
    client certificate (``tls_client_certificate``), which must also sign the CMS request
    (MS-WSTEP, RFC 5272). Returns (cert_pem, error)."""
    db_cert, err = _renewable_certificate(ca, client_cert)
    if err:
        return None, err

    if outer_signed_data is None:
        return None, 'Renewal request is not signed by the certificate being renewed'
    err = _verify_renewal_signer(outer_signed_data, client_cert)
    if err:
        return None, err

    csr, err = _load_csr(csr_der)
    if err:
        return None, err
    # A new key proves itself with its own SignerInfo; the same key is proven above
    err = _new_key_proof(csr, client_cert, outer_signed_data)
    if err:
        return None, err
    return _sign_renewal(ca, client_cert, db_cert, csr, validity_days, source, require_pop=False, gate=gate,
                         profile=profile)


def _verify_renewal_signer(outer_signed_data, cert):
    """None when a SignerInfo naming ``cert`` (issuer and serial, or key
    identifier) verifies with its key, else an error string."""
    from asn1crypto import x509 as asn1_x509

    from fips_mode import FipsRestricted
    from services.scep.message_parser import verify_cms_signature

    cert_der = cert.public_bytes(Encoding.DER)
    issuer = asn1_x509.Certificate.load(cert_der).issuer.dump()
    try:
        key_ids = {x509.SubjectKeyIdentifier.from_public_key(cert.public_key()).digest}
    except Exception:
        return 'Unsupported public key'
    try:
        key_ids.add(cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest)
    except x509.ExtensionNotFound:
        pass

    try:
        signer_infos = list(outer_signed_data['signer_infos'])
    except Exception:
        return 'Invalid PKCS#7 envelope'
    for signer_info in signer_infos:
        try:
            sid = signer_info['sid']
            if sid.name == 'issuer_and_serial_number':
                names_cert = (sid.chosen['issuer'].dump() == issuer
                              and sid.chosen['serial_number'].native == cert.serial_number)
            else:
                names_cert = sid.chosen.native in key_ids
        except Exception:
            return 'Invalid PKCS#7 envelope'
        if not names_cert:
            continue
        try:
            verify_cms_signature(outer_signed_data, cert, signer_info=signer_info)
        except FipsRestricted as e:
            logger.warning("WSTEP: renewal envelope refused in FIPS mode: %s", e)
            return f'PKCS#7 envelope refused: {e}'
        except Exception as e:
            logger.warning("WSTEP: renewal envelope signature check failed: %s", e)
            return 'Renewal request signature invalid (proof of possession failed)'
        return None
    return 'Renewal request is not signed by the certificate being renewed'


def renewed_serial(ca, outer_signed_data):
    """The serial of a certificate of *ca* whose key signs the request envelope, as Windows
    signs a renewal on the Kerberos binding; None for an initial enrollment. For the audit only."""
    from services.cert.issued_lookup import issued_certificate_status
    try:
        choices = list(outer_signed_data['certificates'] or []) if outer_signed_data is not None else []
    except Exception:
        return None
    for choice in choices:
        try:
            if choice.name != 'certificate':
                continue
            cert = x509.load_der_x509_certificate(choice.chosen.dump())
        except Exception:
            continue
        row, _status = issued_certificate_status(ca, cert)
        if row is not None and _verify_renewal_signer(outer_signed_data, cert) is None:
            return cert.serial_number
    return None


def _renewable_certificate(ca, cert):
    """(row, None) when ``cert`` is, byte for byte, a certificate this CA issued
    and still holds; (row or None, error) otherwise. Serial and subject are
    public, so a self-signed lookalike must not pass."""
    from services.cert.issued_lookup import (
        OK, REVOKED, EXPIRED, NOT_YET_VALID, SUPERSEDED, issued_certificate_status,
    )
    db_cert, status = issued_certificate_status(ca, cert)
    if status != OK:
        return db_cert, {
            REVOKED: 'Signing certificate has been revoked',
            EXPIRED: 'Signing certificate has expired',
            NOT_YET_VALID: 'Signing certificate is not yet valid',
            SUPERSEDED: 'Signing certificate has been superseded by a newer one',
        }.get(status, 'Signing certificate is not recognized')
    return db_cert, None


def _renewal_pattern_subject(template, found, *, profile):
    """``(subject, refusal)`` of a renewal under ``template``'s common name pattern, from the
    account its SID names (``found``, filled by ``renewal_requester_sid``): one more search."""
    from services.ad_connector import lookup
    account, connector = found.get('account'), found.get('connector')
    if not account:
        return None, (f"Template '{template.name}' builds its common name from the directory, "
                      'which cannot name the account of the certificate being renewed')
    machine = account.endswith('$')
    if (_subject_source(template) == 'machine') != machine:
        what = 'computers, not users' if not machine else 'users, not computers'
        return None, f"Template '{template.name}' is issued to {what}"
    if machine:
        identity = lookup.lookup_computer_identity(connector, account)
    else:
        identity = lookup.lookup_user_ad_identity(connector, account)
    if identity is lookup.UNREACHABLE:
        return None, ServerError('The directory that builds the certificate subject could not be reached')
    if identity is lookup.NO_UPN:
        return None, ('The certificate subject is built from Active Directory, which found the '
                      'account but it has no userPrincipalName')
    if not identity:
        return None, renewal_identity.NOT_FOUND_MESSAGE
    if machine:
        return _machine_pattern_subject(template, identity, profile=profile)
    email = identity.get('mail')
    return _user_pattern_subject(template, identity, email if email and is_valid_san_email(email) else None,
                                 profile=profile)


def _sign_renewal(ca, signing_cert, db_cert, csr, validity_days, source, require_pop, gate=None,
                  on_stored=None, *, profile):
    """Issue the renewal once the caller has authenticated ``signing_cert``, under the
    profile recorded on ``db_cert`` alone: ``profile`` must be that one."""
    from services.windows_profiles import certificate_profile, profile_sid_connectors
    recorded, refusal = certificate_profile(db_cert)
    if refusal:
        return None, refusal
    if profile is None or recorded.id != profile.id:
        return None, 'Signing certificate belongs to another Windows enrollment profile'

    err = _validate_csr(csr, require_pop=require_pop)
    if err:
        return None, err

    if signing_cert.subject != csr.subject:
        return None, 'CSR subject does not match signing certificate'
    if not _san_matches(signing_cert, csr):
        return None, 'CSR SubjectAltName does not match signing certificate'

    matched_template, extra_ekus, issued_ekus, refusal = _renewal_template(ca, signing_cert, csr, profile=profile)
    if refusal:
        return None, refusal
    template_oid = None
    if matched_template is not None:
        template_oid = _template_oid_for(ca, matched_template, _template_ext_oid(signing_cert), profile=profile)

    # A8: the SID alone is checked again, by the profile's connector only
    found = {}
    try:
        requester_sid = renewal_identity.renewal_requester_sid(
            signing_cert, x509.load_pem_x509_certificate(base64.b64decode(ca.crt)), 'WSTEP',
            connectors_for=lambda sid: profile_sid_connectors(profile, sid), found=found)
    except renewal_identity.RenewalIdentityUnresolved as e:
        return None, ServerError(str(e))
    except renewal_identity.RenewalAccountGone as e:
        return None, str(e)

    # The pattern in force names the renewed certificate, as on issuance; its SAN stays the request's
    override_subject = None
    if _cn_pattern_applies(matched_template):
        override_subject, refusal = _renewal_pattern_subject(matched_template, found, profile=profile)
        if refusal:
            return None, refusal
        override_subject = _merge_pinned_subject_fields(
            override_subject, _required_pinned_subject_fields(ca, matched_template, profile=profile))

    err = _pass_gate(gate, csr, matched_template,
                     override_subject if override_subject is not None else csr.subject, None,
                     signing_cert=signing_cert)
    if err:
        return None, err

    cert_type, template_ku = _template_profile(matched_template, csr)
    try:
        cert_pem, _serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=csr, validity_days=_template_validity(matched_template, validity_days),
            source=source, renewal_of=signing_cert, require_pop=require_pop,
            supersedes=db_cert,
            ms_certificate_template_oid=template_oid,
            override_subject=override_subject,
            requester_sid=requester_sid,
            # See issue()'s matching kwarg for why.
            extra_ekus=extra_ekus,
            template_ekus=issued_ekus,
            policy_template_id=getattr(matched_template, 'id', None),
            template_id=getattr(matched_template, 'id', None),
            cert_type=cert_type, template_key_usage=template_ku, on_stored=on_stored,
            windows_profile_id=profile.id,
        )
    except AlreadySuperseded:
        return None, 'Signing certificate has been superseded by a newer one'
    except PolicyViolation as e:  # the route logs the refusal it answers
        return None, f'Policy violation: {e}'
    except RequestRejected as e:
        logger.warning('WSTEP renew refused: %s', e)
        return None, str(e)
    except AlreadyIssued:
        raise
    except Exception as e:
        logger.error('WSTEP renew failed: %s', e)
        return None, ServerError('Certificate renewal failed')

    return cert_pem, None
