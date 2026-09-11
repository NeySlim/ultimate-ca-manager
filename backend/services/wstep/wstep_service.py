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

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from models import Certificate
from services.ca_service import CAService
from utils.datetime_utils import utc_now
from utils.key_type import validate_enrollment_public_key
from utils.san_parse import is_valid_san_email
from utils.serial_format import serial_variants
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

# ``cryptography``'s CertificateSigningRequest.is_signature_valid reports
# False for a SHA-1-signed CSR even when the signature is mathematically
# valid (confirmed by verifying the same signature manually with
# public_key.verify(..., hashes.SHA1())) -- it isn't reporting tampering,
# it's refusing to vouch for a weak hash algorithm. Windows' certreq.exe
# defaults to SHA-1 unless an INF explicitly sets HashAlgorithm=sha256, so
# this is a real, common case worth a specific message rather than the
# generic "signature invalid" one, which reads as if the request were
# corrupted.
_WEAK_CSR_HASH_ALGORITHMS = {'md5', 'sha1'}


def _weak_csr_hash_algorithm(csr):
    """The CSR's signature hash algorithm name, if it's one of the weak
    ones ``is_signature_valid`` refuses to validate. None otherwise
    (including when the algorithm can't be determined at all, e.g. Ed25519)."""
    try:
        algo = csr.signature_hash_algorithm
    except Exception:
        return None
    if algo is not None and algo.name in _WEAK_CSR_HASH_ALGORITHMS:
        return algo.name
    return None


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
      ``_verify_pkcs7_pop`` (only ``issue()`` calls it — see its
      docstring for why).
    - An empty Subject is accepted when the CSR carries a
      SubjectAlternativeName instead (SAN-only identity is standard
      modern TLS practice).

    ``allow_naked_subject``: skip the "must have CN or SAN" check -- only
    set by ``issue()`` when it has *already* independently derived a
    replacement subject via the AD Connector for a Kerberos machine
    principal. Every other check (PoP, key strength) still applies
    unconditionally regardless of this flag; a naked CSR never gets a free
    pass on those.

    Returns an error string, or None if the CSR is acceptable.
    """
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

    key_err = validate_enrollment_public_key(csr.public_key())
    if key_err:
        return key_err

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
    (the only ones that call this — ``renew()`` doesn't: a renewal RST is
    already WS-Security-signed by an existing, UCM-trusted certificate)
    had no cryptographic proof at all that a PKCS#7-wrapped CSR's
    submitter controlled the CSR's private key. A holder of the shared
    UsernamePassword credential could submit any public key — one they
    don't control — and receive a UCM-issued certificate binding it to
    whatever subject the CSR (or an AD-derived override) requested.

    Returns an error string, or None if the envelope proves possession.
    """
    from services.scep.message_parser import verify_cms_signature

    try:
        signer_infos = outer_signed_data['signer_infos']
    except Exception:
        return 'Invalid PKCS#7 envelope'
    if len(signer_infos) == 0:
        return 'PKCS#7 envelope has no signature'

    sid = signer_infos[0]['sid']
    if sid.name != 'subject_key_identifier':
        return 'PKCS#7 envelope does not identify itself by the request key'

    csr_pubkey = csr.public_key()
    expected_ski = x509.SubjectKeyIdentifier.from_public_key(csr_pubkey).digest
    try:
        actual_ski = sid.chosen.native
    except Exception:
        return 'Invalid PKCS#7 envelope'
    if actual_ski != expected_ski:
        return 'PKCS#7 envelope signer does not match the CSR public key'

    try:
        verify_cms_signature(outer_signed_data, csr_pubkey)
    except Exception:
        return 'PKCS#7 envelope signature invalid (proof of possession failed)'

    return None


def _san_values(cert_or_csr):
    """SAN entries as a set of (type, value) pairs — mirrors EST's
    ``_san_values``, order/criticality irrelevant to identity match."""
    try:
        ext = cert_or_csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)
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


def _match_template(ca, csr):
    """Best-effort match of the CSR's requested EKU against the CA's
    advertised templates (the same set XCEP's GetPolicies exposed).

    There is no explicit "which template did you pick" signal in the RST
    or CSR to key off instead: a real captured Windows request's CMC
    control_sequence was empty and the CSR carried no separate
    CertificateTemplateName attribute. So this infers the template from
    what the CSR itself asks for (its EKU set).

    This is a real limitation, not a corner case: two templates can
    legitimately want the same EKU (e.g. "Web Server" and "VPN Server"
    both want serverAuth-only), and ties break on lowest template id —
    arbitrary but deterministic. Returns the matched ``CertificateTemplate``
    row, or ``None`` if nothing matches at all.

    Callers use the matched row two ways: its policy OID (via
    ``policy_builder._policy_oid_for_template``) for the issued cert's
    ``ms_certificate_template_oid`` — a real Windows client fails
    CX509Enrollment::Enroll with CERTSRV_E_PROPERTY_EMPTY when the cert
    carries no Certificate Template extension — and its own configured
    EKUs (``_template_extra_ekus``) as ``extra_ekus``.
    """
    try:
        import json

        from models import CertificateTemplate
        from services.xcep.policy_builder import _resolve_templates_for_ca
    except Exception:
        return None

    all_active = CertificateTemplate.query.filter_by(is_active=True).all()
    candidates = _resolve_templates_for_ca(ca, all_active)
    if not candidates:
        return None

    try:
        csr_eku = {
            oid.dotted_string
            for oid in csr.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        }
    except x509.ExtensionNotFound:
        csr_eku = set()

    best, best_score = None, -1
    for template in candidates:
        try:
            parsed = json.loads(template.extensions_template or '{}')
        except (TypeError, ValueError):
            parsed = {}
        names = parsed.get('extended_key_usage') if isinstance(parsed, dict) else None
        # Same resolver as issuance: the template is scored on the purposes
        # it will really issue, whatever spelling it uses
        template_eku = set(_template_extra_ekus(template))
        score = len(csr_eku & template_eku) - len(template_eku - csr_eku)
        if score > best_score or (score == best_score and best is not None and template.id < best.id):
            best, best_score = template, score

    if best is None or best_score < 0:
        return None
    return best


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
    from utils.eku_validation import PROTOCOL_UNBINDABLE_EKU_OIDS, normalize_extra_ekus
    # Same cap as the other protocol endpoints, Smartcard Logon excepted:
    # issuing it is what WSTEP templates are for (AD-bound identities)
    capped = PROTOCOL_UNBINDABLE_EKU_OIDS - {'1.3.6.1.4.1.311.20.2.2'}
    oids = []
    for name in names:
        if not isinstance(name, str):
            continue
        resolved, err = normalize_extra_ekus([name])
        if err or not resolved:
            # An unknown name is dropped, the others still apply
            logger.warning('WSTEP: template %s EKU %r ignored (%s)', template.id, name, err)
            continue
        if resolved[0] in capped:
            logger.warning('WSTEP: template %s EKU %r is never issued to an enrollee; dropped',
                           template.id, name)
            continue
        if resolved[0] not in oids:
            oids.append(resolved[0])
    return oids


def _required_enroll_acl_groups(ca, matched_template):
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
    that declares EKUs (see ``_match_template``'s docstring), and MS-WSTEP
    has no other per-request template-selection signal to fall back on.
    Silently treating "no match" as "no gate" would mean the Enroll ACL
    never actually applies to unattended autoenrollment -- the primary
    scenario it exists to restrict -- so an unmatched naked CSR must
    satisfy ANY restricted template's group instead of none of them.
    """
    if matched_template is not None:
        return [matched_template.allowed_ad_group] if matched_template.allowed_ad_group else []

    try:
        from models import CertificateTemplate
        from services.xcep.policy_builder import _resolve_templates_for_ca
    except Exception:
        return []

    all_active = CertificateTemplate.query.filter_by(is_active=True).all()
    candidates = _resolve_templates_for_ca(ca, all_active)
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
    unparseable JSON -- never raises."""
    if not template or not template.pinned_subject_fields:
        return {}
    try:
        import json
        raw = json.loads(template.pinned_subject_fields)
    except (TypeError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if k in _PINNED_FIELD_OIDS and v}


def _required_pinned_subject_fields(ca, matched_template):
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
    """
    if matched_template is not None:
        return _template_pinned_fields(matched_template)

    try:
        from models import CertificateTemplate
        from services.xcep.policy_builder import _resolve_templates_for_ca
    except Exception:
        return {}

    all_active = CertificateTemplate.query.filter_by(is_active=True).all()
    candidates = _resolve_templates_for_ca(ca, all_active)

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


def _user_ad_derivation_enabled(ca):
    """Whether any template resolvable for ``ca`` has opted into
    AD-derived user subjects (``CertificateTemplate.ad_derived_subject``).

    Deliberately independent of ``_match_template``'s EKU-based
    scoring above: a naked CSR (the only kind this ever applies to — see
    ``issue()``) carries no EKU extension, so it scores negative against
    any candidate template that declares EKUs at all, meaning EKU-based
    matching alone would almost always find nothing and this feature would
    silently never fire. This only asks "did an admin opt any template
    into AD-derivation for this CA," mirroring how the machine branch below
    has no template dependency either — MS-WSTEP's wire protocol has no
    template-selection signal to check instead (see ``_match_template``'s
    docstring).
    """
    try:
        from models import CertificateTemplate
        from services.xcep.policy_builder import _resolve_templates_for_ca
    except Exception:
        return False

    all_active = CertificateTemplate.query.filter_by(is_active=True).all()
    candidates = _resolve_templates_for_ca(ca, all_active)
    return any(getattr(t, 'ad_derived_subject', False) for t in candidates)


def issue(ca, csr_der, validity_days, source='wstep', require_pop=True, kerberos_principal=None,
          outer_signed_data=None):
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
    UsernamePassword one, which has no Kerberos identity to give). When set
    and the CSR is naked (see ``_is_naked_csr``), attempts to derive a
    subject via the AD Connector (``services/ad_connector/lookup.py``)
    instead of rejecting outright -- what real Windows GPO autoenrollment
    needs, since it deliberately submits a subject-less CSR for templates
    configured to build the subject from AD, trusting the CA to fill it in
    server-side the same way real ADCS does:

    - Machine principal: ``CN=<computer's AD dnsHostName>``, no SAN needed
      (the certificate's own CN synthesizes a matching SAN downstream).
      Unconditional on any template -- MS-WSTEP has no template-selection
      signal to gate it on (see ``_match_template``'s docstring), and
      this is the already lab-verified path; it must not gain a new
      failure mode from the toggle below.
    - User principal: the AD user object's own directory-path DN as the
      subject, plus its ``userPrincipalName`` as a SAN OtherName -- matches
      a real ADCS-issued User certificate's shape exactly (confirmed
      against the lab: ``CN=Roy Hagland, CN=Users, DC=hagland, DC=domain``
      + ``Other Name:Principal Name=roy.hagland@hagland.domain``). Only
      attempted when at least one template resolvable for ``ca`` has opted
      in via ``CertificateTemplate.ad_derived_subject`` (see
      ``_user_ad_derivation_enabled``) -- unlike the machine path, this is
      new behavior, so it's admin opt-in per template rather than always-on.
      If the AD user object also has a ``mail`` attribute, it's added as a
      leaf-most ``E=`` subject RDN and an SAN RFC822Name -- opportunistic,
      never required: real ADCS's own CT_FLAG_SUBJECT_REQUIRE_EMAIL hard-
      declines autoenrollment for any user without one, which would make a
      single template unusable for a mixed user base, so UCM never
      advertises that requirement (see policy_builder.py's
      ``_USER_AD_DERIVED_SUBJECT_NAME_FLAGS``) and simply includes the
      email when present, omits it otherwise.

    Falls through to the normal naked-CSR rejection if the connector isn't
    configured, no template has opted in, or the lookup fails for any
    reason (account not found, LDAP unreachable, no userPrincipalName
    set, ...).

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
    and the SID lookup for this specific request fails for any reason,
    issuance is refused rather than silently issuing a weaker-mapped cert.
    UsernamePassword-bound calls never get this either, same reason as
    Enroll ACL: no per-request principal to resolve a SID for.
    """
    csr, err = _load_csr(csr_der)
    if err:
        return None, err

    override_subject = None
    override_san = None
    kerberos_sam_account_name = None
    if kerberos_principal:
        from services.ad_connector import lookup
        parsed = lookup.parse_kerberos_principal(kerberos_principal)
        if parsed and not lookup.realm_matches_connector(parsed[1]):
            # Kerberos cross-realm trust means the ticket's realm isn't
            # necessarily the domain the AD Connector is configured
            # against; sAMAccountName alone (parsed[0]) isn't globally
            # unique the way a realm-qualified principal is, so a mismatch
            # here must not fall through to a same-named account lookup in
            # the wrong domain -- see lookup.realm_matches_connector. Also
            # denies the Enroll ACL check below a sam_account_name to check,
            # which fails that check closed rather than skipping it.
            logger.warning(
                "AD Connector: Kerberos principal %r realm does not match the "
                "configured connector's domain -- refusing to derive a subject",
                kerberos_principal,
            )
            parsed = None
        if parsed:
            kerberos_sam_account_name = parsed[0]

    # Strong certificate mapping (KB5014754): embed the authenticated
    # requester's AD SID as the SID security extension, matching real
    # ADCS's own automatic behavior since a 2021-era hotfix -- unlike
    # every other WSTEP AD Connector feature here, this is unconditional,
    # not a per-template opt-in, and independent of _is_naked_csr below:
    # the SID identifies who authenticated, not what subject was
    # requested, so it applies to naked AND manually-typed Kerberos-bound
    # CSRs alike. "AD Connector not configured at all" and "configured but
    # this lookup failed" are deliberately different outcomes -- the
    # former means the feature doesn't apply (checked directly against
    # ADConnectorConfig, since lookup.py's functions collapse both cases
    # to the same None), the latter refuses issuance rather than silently
    # issuing a weaker-mapped cert.
    requester_sid = None
    if kerberos_sam_account_name:
        from models import ADConnectorConfig

        ad_config = ADConnectorConfig.get_singleton()
        if ad_config and ad_config.enabled:
            requester_sid = lookup.lookup_object_sid(kerberos_sam_account_name)
            if requester_sid is None:
                logger.warning(
                    "WSTEP: could not resolve requester SID for %r via AD "
                    "Connector -- refusing issuance (strong certificate mapping)",
                    kerberos_sam_account_name,
                )
                return None, 'Could not resolve requester identity for strong certificate mapping'

    if kerberos_sam_account_name and _is_naked_csr(csr):
        if lookup.is_machine_principal(kerberos_principal):
            dns_hostname = lookup.lookup_computer_dns_hostname(kerberos_sam_account_name)
            if dns_hostname:
                override_subject = x509.Name(
                    [x509.NameAttribute(NameOID.COMMON_NAME, dns_hostname)]
                )
        elif _user_ad_derivation_enabled(ca):
            identity = lookup.lookup_user_ad_identity(kerberos_sam_account_name)
            if identity:
                # AD's mail attribute is optional -- validated (not just
                # truthy) before use, since it's untrusted directory
                # data reaching straight into a certificate subject/SAN.
                # A malformed value degrades to "no email", never a
                # crash or a bogus RDN.
                email = identity.get('mail')
                if email and not is_valid_san_email(email):
                    logger.warning(
                        "AD Connector: ignoring malformed mail attribute %r for %r",
                        email, kerberos_sam_account_name,
                    )
                    email = None
                derived_subject = _x509_name_from_dn_components(identity['dn_components'], email=email)
                if derived_subject is not None:
                    override_subject = derived_subject
                    override_san = [build_upn_other_name(identity['upn'])]
                    if email:
                        override_san.append(x509.RFC822Name(email))

    err = _validate_csr(
        csr, require_pop=require_pop, allow_naked_subject=override_subject is not None
    )
    if err:
        return None, err

    if outer_signed_data is not None:
        err = _verify_pkcs7_pop(csr, outer_signed_data)
        if err:
            return None, err

    matched_template = _match_template(ca, csr)
    template_oid = None
    if matched_template is not None:
        from services.xcep.policy_builder import _policy_oid_for_template
        template_oid = _policy_oid_for_template(ca, matched_template)

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
    pinned_fields = _required_pinned_subject_fields(ca, matched_template)
    if pinned_fields:
        base_subject = override_subject if override_subject is not None else csr.subject
        override_subject = _merge_pinned_subject_fields(base_subject, pinned_fields)

    # Enroll ACL: only gates the Kerberos-bound path -- the UsernamePassword
    # path authenticates a single shared SystemConfig credential, not a
    # per-request principal, so there's no identity here to check group
    # membership for. See _required_enroll_acl_groups for why an unmatched
    # (typically naked) CSR checks against every restricted template for
    # the CA rather than being skipped. A missing/unresolved
    # sam_account_name (parse failure, cross-realm mismatch) denies rather
    # than skips the check, same as an AD lookup failure inside
    # is_member_of_group -- this is a security gate, not a best-effort
    # convenience lookup.
    if kerberos_principal:
        required_groups = _required_enroll_acl_groups(ca, matched_template)
        if required_groups and (
            not kerberos_sam_account_name
            or not any(
                lookup.is_member_of_group(kerberos_sam_account_name, group)
                for group in required_groups
            )
        ):
            logger.warning(
                "WSTEP Enroll ACL: principal %r denied (requires membership in one of %r)",
                kerberos_principal, required_groups,
            )
            return None, 'Requester is not authorized to enroll against this template'

    try:
        cert_pem, _serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=csr, validity_days=validity_days, source=source,
            require_pop=require_pop,
            ms_certificate_template_oid=template_oid,
            override_subject=override_subject,
            override_san=override_san,
            requester_sid=requester_sid,
            # Upstream's CSR-EKU cap (see _template_extra_ekus) never
            # honours Microsoft Smartcard Logon from a CSR's own EKU
            # extension, whatever cert_type is — extra_ekus is the only
            # way a Smartcard Logon template still issues correctly.
            extra_ekus=_template_extra_ekus(matched_template),
        )
    except Exception as e:
        logger.error('WSTEP issue failed: %s', e)
        return None, 'Certificate issuance failed'

    return cert_pem, None


def renew(ca, csr_der, security_header, csr_element, validity_days, source='wstep', require_pop=True):
    """Certificate-bound renewal: the RST is signed with the client's
    current certificate's private key. Returns (cert_pem, error).

    ``require_pop`` — see ``issue()``; renewal RSTs can arrive PKCS#7/CMC-
    wrapped too, and the outer WS-Security signature already authenticates
    the caller here, so the inner CSR's own self-signature matters even
    less than it does for the UsernamePassword-bound issue path.

    ``csr_element``: see ``rst_parser.ParsedRST.csr_element`` and
    ``ws_security.SignedContent`` for why this must be checked against
    the verified signature rather than trusting ``csr_der`` alone.
    """
    try:
        signing_cert_der, signed_content = ws_security.verify_signed_request(security_header)
    except ws_security.WSSecurityError as e:
        return None, str(e)

    if not signed_content.covers(csr_element):
        return None, 'CSR is not covered by the request signature'

    try:
        signing_cert = x509.load_der_x509_certificate(signing_cert_der)
    except Exception:
        return None, 'Invalid signing certificate'

    # Serial number and subject are both public, so matching on them alone
    # (as this used to) lets an attacker forge a self-signed lookalike and
    # renew under a victim's identity. Require a byte-for-byte match against
    # a certificate UCM itself issued from this same CA.
    from services.cert.issued_lookup import (
        OK, REVOKED, EXPIRED, NOT_YET_VALID, SUPERSEDED, issued_certificate_status,
    )
    db_cert, status = issued_certificate_status(ca, signing_cert)
    if status != OK:
        return None, {
            REVOKED: 'Signing certificate has been revoked',
            EXPIRED: 'Signing certificate has expired',
            NOT_YET_VALID: 'Signing certificate is not yet valid',
            SUPERSEDED: 'Signing certificate has been superseded by a newer one',
        }.get(status, 'Signing certificate is not recognized')

    csr, err = _load_csr(csr_der)
    if err:
        return None, err

    err = _validate_csr(csr, require_pop=require_pop)
    if err:
        return None, err

    if signing_cert.subject != csr.subject:
        return None, 'CSR subject does not match signing certificate'
    if not _san_matches(signing_cert, csr):
        return None, 'CSR SubjectAltName does not match signing certificate'

    matched_template = _match_template(ca, csr)
    template_oid = None
    if matched_template is not None:
        from services.xcep.policy_builder import _policy_oid_for_template
        template_oid = _policy_oid_for_template(ca, matched_template)

    try:
        cert_pem, _serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=csr, validity_days=validity_days, source=source,
            renewal_of=signing_cert, require_pop=require_pop,
            supersedes=db_cert,
            ms_certificate_template_oid=template_oid,
            # See issue()'s matching kwarg for why.
            extra_ekus=_template_extra_ekus(matched_template),
        )
    except Exception as e:
        logger.error('WSTEP renew failed: %s', e)
        return None, 'Certificate renewal failed'

    return cert_pem, None
