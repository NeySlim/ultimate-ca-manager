"""
CSR operations mixin for TrustStoreService
"""
import ipaddress
import logging
from datetime import timedelta
from typing import List, Optional, Tuple

from cryptography import x509
from utils.eku_validation import add_ocsp_nocheck_if_responder
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend

from utils.datetime_utils import utc_now, cert_not_before
from utils.x509_aki import authority_key_identifier_from_issuer
from utils.leaf_key_usage import constrain_builder_key_usage
from .constants import HASH_ALGORITHMS
from .key_operations_mixin import KeyOperationsMixin
from .constraints_mixin import ConstraintsMixin
from utils.key_codec import private_key_to_pem

logger = logging.getLogger(__name__)

_MS_CERTIFICATE_TEMPLATE_OID = x509.ObjectIdentifier('1.3.6.1.4.1.311.21.7')


from utils.signing_hash import signing_hash_for


def _certificate_template_extension(template_oid, major=100, minor=0):
    """Build the Microsoft CertificateTemplateOID extension (MS-CRTD):
    ``SEQUENCE { templateID OBJECT IDENTIFIER, major INTEGER, minor
    INTEGER }``. ``cryptography`` has no native type for it, so it's
    hand-built with asn1crypto and wrapped as UnrecognizedExtension —
    same approach already used for CMC parsing in
    services/wstep/rst_parser.py. major/minor are arbitrary (Windows
    doesn't validate them against anything server-side); 100/0 mirrors
    a typical real ADCS template's default major version."""
    from asn1crypto import core as asn1_core

    class _TemplateVersion(asn1_core.Integer):
        pass

    class _CertificateTemplateOID(asn1_core.Sequence):
        _fields = [
            ('template_id', asn1_core.ObjectIdentifier),
            ('template_major_version', _TemplateVersion),
            ('template_minor_version', _TemplateVersion, {'optional': True}),
        ]

    der = _CertificateTemplateOID({
        'template_id': template_oid,
        'template_major_version': major,
        'template_minor_version': minor,
    }).dump()
    return x509.UnrecognizedExtension(_MS_CERTIFICATE_TEMPLATE_OID, der)


_SID_SECURITY_EXT_OID = x509.ObjectIdentifier('1.3.6.1.4.1.311.25.2')
_NTDS_OBJECT_SID_OID = '1.3.6.1.4.1.311.25.2.1'


def _ad_security_extension(sid_string):
    """Build the Microsoft SID security extension
    (``szOID_NTDS_CA_SECURITY_EXT``, 1.3.6.1.4.1.311.25.2) real ADCS embeds
    on AD-authenticated issuances for KB5014754 strong certificate mapping:
    ``SEQUENCE OF [0] { type OBJECT IDENTIFIER, value [0] EXPLICIT OCTET
    STRING }``, one entry, the OCTET STRING holding the requester's SID in
    its ``"S-1-5-21-..."`` string form (not raw binary -- confirmed by
    capturing a real cert's extension in the lab). ``cryptography`` has no
    native type for this either, so hand-built with asn1crypto and wrapped
    as UnrecognizedExtension -- same approach as
    ``_certificate_template_extension`` above. Byte-for-byte verified
    against a real ADCS-issued certificate's own extension for the same
    SID (see test_ad_security_extension.py)."""
    from asn1crypto import core as asn1_core

    class _SidValue(asn1_core.OctetString):
        pass

    class _SecurityExtEntry(asn1_core.Sequence):
        class_ = 2  # context
        tag = 0
        _fields = [
            ('type', asn1_core.ObjectIdentifier),
            ('value', _SidValue, {'explicit': 0}),
        ]

    class _SecurityExt(asn1_core.SequenceOf):
        _child_spec = _SecurityExtEntry

    entry = _SecurityExtEntry({
        'type': _NTDS_OBJECT_SID_OID,
        'value': sid_string.encode('ascii'),
    })
    der = _SecurityExt([entry]).dump()
    return x509.UnrecognizedExtension(_SID_SECURITY_EXT_OID, der)


_LEAF_CA_ONLY_EXTENSION_OIDS = frozenset({
    ExtensionOID.NAME_CONSTRAINTS,
    ExtensionOID.POLICY_CONSTRAINTS,
    ExtensionOID.INHIBIT_ANY_POLICY,
})

# The only extensions a leaf CSR may contribute to the issued certificate.
# Everything else on a leaf is the issuer's to set: CRL Distribution Points,
# AIA and Certificate Policies come from the CA configuration below, the
# Microsoft template and SID security extensions only from the WSTEP kwargs,
# SKI/AKI from the keys. Copying unknown extensions verbatim let an enrollee
# that reached this trunk through ACME, EST or WSTEP choose the revocation
# endpoints of its own certificate, or carry a szOID_NTDS_CA_SECURITY_EXT of
# its choosing -- the strong-mapping bypass KB5014754 closes. The SCEP
# builder applies a stricter list of the same kind (SAN, KU and EKU only);
# sub-CA CSRs (an operator holding write:cas signs those deliberately) keep
# the wider behaviour. The CA-only constraints of
# _LEAF_CA_ONLY_EXTENSION_OIDS are among what a leaf never gets from its CSR.
_LEAF_CSR_COPYABLE_EXTENSION_OIDS = frozenset({
    ExtensionOID.SUBJECT_ALTERNATIVE_NAME,
    ExtensionOID.KEY_USAGE,
    ExtensionOID.EXTENDED_KEY_USAGE,
    ExtensionOID.BASIC_CONSTRAINTS,
    ExtensionOID.TLS_FEATURE,
    ExtensionOID.OCSP_NO_CHECK,
})

# EKUs a leaf cert signed from a CSR must never carry: an OCSPSigning leaf that
# chains to the CA is trusted by validators as a delegated OCSP responder for
# the whole CA (it can sign "good" for revoked certs), and timeStamping grants
# trusted-timestamp authority. Neither may be obtained by a protocol client
# (ACME/EST) that only proved domain control or mTLS. Admin-configured delegated
# responders are issued through the dedicated certificate-creation path, not here.
_LEAF_FORBIDDEN_EKU_OIDS = frozenset({
    x509.ExtendedKeyUsageOID.OCSP_SIGNING,
    x509.ExtendedKeyUsageOID.TIME_STAMPING,
})

# anyExtendedKeyUsage defeats EKU chaining entirely: a leaf carrying it is
# usable for every purpose, which makes any per-type EKU policy meaningless.
# Never honoured from a CSR on any protocol path (ACME/EST/renewal). NB: the
# admin Sign-CSR endpoints pass allow_sensitive_ekus=True and are deliberately
# uncapped (explicit operator intent), so this block-list does not apply there.
_ANY_EKU_OID = x509.ObjectIdentifier('2.5.29.37.0')

# Microsoft Smartcard Logon — grants Active Directory interactive logon when
# paired with a UPN SAN. Never honoured from CSR-supplied EKU on a protocol
# path (same admin-path caveat as above); an operator who genuinely wants it
# passes it explicitly via ``extra_ekus``.
_SMARTCARD_LOGON_OID = x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2.2')

# Per-certificate-type EKU ceiling for CSR-supplied Extended Key Usage.
#
# Without this, whatever EKU a CSR carries is copied onto the leaf, so a client
# that only proved DNS control (ACME finalize signs with cert_type
# 'server_cert') could mint a codeSigning or emailProtection certificate. The
# resolved certificate type — not the requester's CSR — decides what the leaf
# may be used for. Operator-supplied ``extra_ekus`` are deliberate admin intent
# and are merged in separately, so they are not capped here.
_TLS_EKUS = frozenset({
    x509.ExtendedKeyUsageOID.SERVER_AUTH,
    x509.ExtendedKeyUsageOID.CLIENT_AUTH,
})
_CERT_TYPE_ALLOWED_EKUS = {
    'server_cert': _TLS_EKUS,
    'server': _TLS_EKUS,
    'host': _TLS_EKUS,
    'client_cert': _TLS_EKUS,
    'usr_cert': _TLS_EKUS,
    'user': _TLS_EKUS,
    'combined_cert': _TLS_EKUS,
    'combined_server_client': _TLS_EKUS,
    'code_signing': frozenset({x509.ExtendedKeyUsageOID.CODE_SIGNING}),
    'email_cert': frozenset({
        x509.ExtendedKeyUsageOID.EMAIL_PROTECTION,
        x509.ExtendedKeyUsageOID.CLIENT_AUTH,
    }),
    # EST device enrollment — same reviewed allow-list SCEP applies to its
    # protocol enrollees (scep_service._ALLOWED_EKU_OIDS): both protocols
    # enroll the same kinds of devices, and a narrower EST ceiling silently
    # strips EKUs (e.g. ipsecIKE on a VPN gateway) that the equivalent SCEP
    # enrollment would keep.
    'device_cert': frozenset({
        x509.ExtendedKeyUsageOID.SERVER_AUTH,
        x509.ExtendedKeyUsageOID.CLIENT_AUTH,
        x509.ExtendedKeyUsageOID.EMAIL_PROTECTION,
        x509.ExtendedKeyUsageOID.CODE_SIGNING,
        x509.ExtendedKeyUsageOID.IPSEC_IKE,
    }),
}


def _default_ekus_for_cert_type(cert_type):
    """The EKU profile a leaf of *cert_type* carries when its CSR supplies no
    usable EKU.

    Shared by the no-EKU-in-CSR default and the every-EKU-refused fallback in
    ``_filter_csr_ekus`` so both shapes resolve to the same profile: a CSR
    that requests nothing and a CSR whose every request is refused must not
    end up with different key purposes. Types without a profile (e.g. the
    deliberate ``custom`` type) return an empty list.
    """
    if cert_type in ('server_cert', 'server', 'host'):
        return [x509.ExtendedKeyUsageOID.SERVER_AUTH]
    if cert_type in ('usr_cert', 'client_cert', 'user'):
        return [x509.ExtendedKeyUsageOID.CLIENT_AUTH]
    if cert_type in ('combined_server_client', 'combined_cert', 'device_cert'):
        return [
            x509.ExtendedKeyUsageOID.SERVER_AUTH,
            x509.ExtendedKeyUsageOID.CLIENT_AUTH,
        ]
    if cert_type == 'code_signing':
        return [x509.ExtendedKeyUsageOID.CODE_SIGNING]
    if cert_type == 'email_cert':
        return [x509.ExtendedKeyUsageOID.EMAIL_PROTECTION]
    return []


_TEMPLATE_KU_FLAGS = {
    'digitalsignature': 'digital_signature',
    'keyencipherment': 'key_encipherment',
    'contentcommitment': 'content_commitment',
    'nonrepudiation': 'content_commitment',
    'dataencipherment': 'data_encipherment',
    'keyagreement': 'key_agreement',
}


def _template_key_purposes(template_ext, allow_sensitive_ekus=False):
    """(KeyUsage or None, EKU OIDs or None) a bound template imposes on a leaf.

    Mirrors what the issue form (#226) and SCEP profiles (#228) do with a
    template's ``extensions_template``: a non-empty ``key_usage`` list
    replaces the CSR's KeyUsage, a non-empty ``extended_key_usage`` list
    replaces its EKUs. CA bits are never taken from a template. EKUs the
    protocol paths never hand out (OCSPSigning, timeStamping, anyEKU,
    Smartcard Logon) are dropped with a warning unless the caller is the
    admin Sign-CSR path.

    The EKU result distinguishes "the template has no EKU policy" (None:
    the CSR's own EKUs apply, filtered as usual) from "it has one but every
    entry was refused" ([]: the CSR's request must not slip back in; the
    caller issues the cert_type default profile instead).
    """
    if not isinstance(template_ext, dict):
        return None, None
    from utils.eku_validation import normalize_extra_ekus, to_object_identifiers

    usage = None
    ku_names = template_ext.get('key_usage')
    if isinstance(ku_names, list) and ku_names:
        flags = dict(
            digital_signature=False, content_commitment=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False,
        )
        for name in ku_names:
            attr = _TEMPLATE_KU_FLAGS.get(str(name).lower())
            if attr:
                flags[attr] = True
        if any(flags.values()):
            usage = x509.KeyUsage(**flags)

    ekus = None
    eku_names = template_ext.get('extended_key_usage')
    if isinstance(eku_names, list) and eku_names:
        ekus = []
        oid_strs, err = normalize_extra_ekus(eku_names)
        if err:
            raise ValueError(f'Invalid template EKUs: {err}')
        for oid in to_object_identifiers(oid_strs):
            if not allow_sensitive_ekus and (
                oid in _LEAF_FORBIDDEN_EKU_OIDS
                or oid in (_ANY_EKU_OID, _SMARTCARD_LOGON_OID)
            ):
                logger.warning(
                    "sign_csr: dropped template EKU %s — never issued to "
                    "protocol enrollees", oid.dotted_string,
                )
                continue
            ekus.append(oid)
    return usage, ekus


def _prior_ekus(renewal_of):
    """EKUs the certificate being renewed already carries ([] if none)."""
    if renewal_of is None:
        return []
    try:
        return list(renewal_of.extensions.get_extension_for_oid(
            ExtensionOID.EXTENDED_KEY_USAGE
        ).value)
    except x509.ExtensionNotFound:
        return []


def _filter_csr_ekus(eku_oids, cert_type, allow_sensitive_ekus, renewal_of=None):
    """Cap CSR-supplied EKUs for a leaf to what *cert_type* permits.

    Returns (kept, dropped).

    ``allow_sensitive_ekus`` marks the admin Sign-CSR path — an operator with
    full CA control deliberately signing a CSR (e.g. a delegated OCSP responder
    or TSA). That is explicit human intent, so no ceiling is applied and the
    path behaves exactly as before. Every protocol path (ACME finalize, EST,
    SCEP, auto-renewal) leaves it False and gets the full cap: an enrollee that
    only proved domain control cannot widen its own leaf's key purposes.

    ``renewal_of`` is the certificate this signing renews. EKUs it already
    carries stay allowed (renewal at par): silently stripping them — e.g.
    ipsecIKE on a VPN device renewing over EST — breaks the service downstream
    with no error anywhere, which is the same reason SCEP preserves them
    (scep_service). The block-list above still applies, so OCSPSigning,
    timeStamping, anyExtendedKeyUsage and Smartcard Logon are never
    resurrected from a prior certificate.

    When every requested EKU is refused, the certificate type's own profile is
    issued instead: omitting the ExtendedKeyUsage extension entirely would
    make the leaf unrestricted for every purpose (RFC 5280 §4.2.1.12) —
    strictly weaker than the cap, and weaker than the same CSR with no EKU at
    all. A type with no profile to fall back to refuses outright.
    """
    if allow_sensitive_ekus:
        return list(eku_oids), []

    allowed = _CERT_TYPE_ALLOWED_EKUS.get(cert_type)
    if allowed is not None and renewal_of is not None:
        try:
            prior = set(renewal_of.extensions.get_extension_for_oid(
                ExtensionOID.EXTENDED_KEY_USAGE
            ).value)
        except x509.ExtensionNotFound:
            prior = set()
        extra = {
            oid for oid in prior - allowed
            if oid not in _LEAF_FORBIDDEN_EKU_OIDS
            and oid not in (_ANY_EKU_OID, _SMARTCARD_LOGON_OID)
        }
        if extra:
            logger.info(
                "sign_csr: renewal at par — keeping prior EKU(s) %s beyond "
                "the %r profile",
                sorted(o.dotted_string for o in extra), cert_type,
            )
            allowed = allowed | extra

    kept, dropped = [], []
    for oid in eku_oids:
        if oid in _LEAF_FORBIDDEN_EKU_OIDS or oid in (_ANY_EKU_OID, _SMARTCARD_LOGON_OID):
            dropped.append(oid)
            continue
        # Unknown/custom certificate types keep their historical behaviour:
        # no per-type ceiling, only the block-list above applies.
        if allowed is not None and oid not in allowed:
            dropped.append(oid)
            continue
        kept.append(oid)

    if not kept:
        # Every requested EKU was refused. Emitting no ExtendedKeyUsage
        # extension would hand back an unrestricted certificate — and create
        # the perverse incentive that a CSR requesting a forbidden EKU gets
        # MORE than a CSR requesting nothing. Fall back to the type's profile.
        kept = _default_ekus_for_cert_type(cert_type)
        if not kept:
            raise ValueError(
                "CSR requests only Extended Key Usages that are not permitted "
                f"for certificate type {cert_type!r}"
            )
    return kept, dropped


def _capped_basic_constraints(csr_constraints, ca_cert):
    """Clamp a sub-CA's pathLenConstraint to what the parent CA permits.

    RFC 5280 §4.2.1.9: a CA with pathLenConstraint N may be followed by at most
    N further CAs in the chain, so a child issued by it may assert at most N-1;
    a parent with pathLen 0 may not issue a sub-CA at all. The value otherwise
    comes straight from the requester's CSR, so without this clamp a signed
    intermediate could claim a deeper (or unlimited) path than its issuer.
    """
    requested = csr_constraints.path_length

    try:
        parent_bc = ca_cert.extensions.get_extension_for_oid(
            ExtensionOID.BASIC_CONSTRAINTS
        ).value
        parent_limit = parent_bc.path_length
    except x509.ExtensionNotFound:
        parent_limit = None

    if parent_limit is None:
        # Unconstrained parent — the child's own request stands.
        return csr_constraints

    if parent_limit <= 0:
        raise ValueError(
            "Issuing CA has pathLenConstraint 0 and may not issue a subordinate CA"
        )

    max_allowed = parent_limit - 1
    if requested is None or requested > max_allowed:
        if requested is not None:
            logger.warning(
                "clamping requested sub-CA pathLenConstraint %s to %s "
                "(issuing CA permits %s)", requested, max_allowed, parent_limit,
            )
        return x509.BasicConstraints(ca=True, path_length=max_allowed)

    return csr_constraints


def capped_path_length(requested, parent_cert):
    """Clamp a sub-CA pathLenConstraint to what *parent_cert* permits.

    Public entry point for the create-CA path (POST /api/v2/cas), so both
    routes that mint a sub-CA at the same permission level enforce the same
    RFC 5280 §4.2.1.9 rule with the same error string. Returns the clamped
    value; raises ValueError when the parent may not issue a sub-CA at all.
    """
    return _capped_basic_constraints(
        x509.BasicConstraints(ca=True, path_length=requested), parent_cert
    ).path_length


def _key_usage_with_ca_signing(usage, enabled):
    """Return a KeyUsage with CA signing bits forced to the policy value."""
    return x509.KeyUsage(
        digital_signature=usage.digital_signature,
        content_commitment=usage.content_commitment,
        key_encipherment=usage.key_encipherment,
        data_encipherment=usage.data_encipherment,
        key_agreement=usage.key_agreement,
        key_cert_sign=enabled,
        crl_sign=enabled,
        encipher_only=usage.encipher_only if usage.key_agreement else False,
        decipher_only=usage.decipher_only if usage.key_agreement else False,
    )


def _synthesize_san_from_subject(subject):
    """SAN entries implied by a subject's CN/email attributes -- same
    derivation ``sign_csr`` already applied when a CSR carries no SAN
    extension of its own. Factored out so this can be computed once and
    reused both for NameConstraints validation and for actually building the
    certificate's SAN extension, so the two can't drift apart (see
    ``sign_csr``'s ``override_subject`` handling)."""
    san_names = []
    for attr in subject:
        if attr.oid == NameOID.COMMON_NAME:
            cn_val = attr.value
            try:
                ip = ipaddress.ip_address(cn_val)
                san_names.append(x509.IPAddress(ip))
            except ValueError:
                if '@' in cn_val:
                    san_names.append(x509.RFC822Name(cn_val))
                else:
                    san_names.append(x509.DNSName(cn_val))
            break
    for attr in subject:
        if attr.oid == NameOID.EMAIL_ADDRESS:
            email_val = attr.value
            if not any(isinstance(n, x509.RFC822Name) and n.value == email_val for n in san_names):
                san_names.append(x509.RFC822Name(email_val))
    return san_names


class CSROperationsMixin:
    """CSR generation and signing operations mixin"""

    @staticmethod
    def generate_csr(
        subject: x509.Name,
        key_type: str = '2048',
        digest: str = 'sha256',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
        san_email: Optional[List[str]] = None,
        san_uri: Optional[List[str]] = None,
        san_upn: Optional[List[str]] = None,
    ) -> Tuple[bytes, bytes]:
        """Generate a Certificate Signing Request."""
        # Generate private key
        private_key = KeyOperationsMixin.generate_private_key(key_type)

        # Build CSR
        builder = x509.CertificateSigningRequestBuilder()
        builder = builder.subject_name(subject)

        # Add SANs if provided
        san_list = []
        if san_dns:
            san_list.extend([x509.DNSName(dns) for dns in san_dns])
        if san_ip:
            san_list.extend([
                x509.IPAddress(ipaddress.ip_address(ip)) for ip in san_ip
            ])
        if san_email:
            san_list.extend([x509.RFC822Name(email) for email in san_email])
        if san_uri:
            san_list.extend([x509.UniformResourceIdentifier(uri) for uri in san_uri])
        if san_upn:
            from utils.upn_san import build_upn_other_name
            for upn in san_upn:
                if upn and upn.strip():
                    san_list.append(build_upn_other_name(upn.strip()))

        if san_list:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )

        # Sign CSR
        hash_algo = HASH_ALGORITHMS.get(digest, hashes.SHA256())
        csr = builder.sign(private_key, hash_algo, default_backend())

        # Serialize
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key_to_pem(private_key)

        return csr_pem, key_pem

    @staticmethod
    def generate_ca_csr(
        subject: x509.Name,
        private_key,
        digest: str = 'sha256',
        path_length: Optional[int] = None,
        key_usage: Optional[List[str]] = None,
    ) -> bytes:
        """Generate a CA-flavored CSR for external signing (#298).

        The CSR asserts BasicConstraints CA:TRUE (with the requested
        pathLenConstraint, which the external signer may clamp) and a CA
        KeyUsage, both critical. No SKI is included — signers regenerate it
        from the public key, exactly as UCM's own sign_csr does. The key is
        passed in rather than generated here: HSM-backed keys
        (HsmRSAPrivateKey/HsmECPrivateKey are virtual rsa/ec subclasses) sign
        the CSR like any local key.
        """
        from utils.ca_profile import (
            DEFAULT_INTERMEDIATE_KEY_USAGE, build_key_usage_extension,
        )

        builder = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(subject)
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=path_length),
                critical=True,
            )
            .add_extension(
                build_key_usage_extension(key_usage or DEFAULT_INTERMEDIATE_KEY_USAGE),
                critical=True,
            )
        )

        hash_algo = HASH_ALGORITHMS.get(digest, hashes.SHA256())
        csr = builder.sign(private_key, hash_algo, default_backend())
        return csr.public_bytes(serialization.Encoding.PEM)

    @staticmethod
    def sign_csr(
        csr_pem: bytes,
        ca_cert: x509.Certificate,
        ca_private_key,
        validity_days: int = 397,
        digest: str = 'sha256',
        cert_type: str = 'server_cert',
        cdp_url: str = None,
        cdp_urls: Optional[List[str]] = None,
        ocsp_url: str = None,
        ocsp_urls: Optional[List[str]] = None,
        aia_ca_issuers_url: str = None,
        aia_ca_issuers_urls: Optional[List[str]] = None,
        cps_uri: Optional[str] = None,
        cps_oid: Optional[str] = None,
        ocsp_must_staple: bool = False,
        extra_ekus: Optional[List[str]] = None,
        renewal_of=None,
        allow_sensitive_ekus: bool = False,
        require_pop: bool = True,
        ms_certificate_template_oid: Optional[str] = None,
        override_subject: Optional[x509.Name] = None,
        override_san: Optional[List[x509.GeneralName]] = None,
        requester_sid: Optional[str] = None,
        template_ext: Optional[dict] = None,
    ) -> bytes:
        """Sign a CSR with a CA. ``renewal_of``: existing certificate this
        signing renews — its names are graced by NameConstraints validation.
        ``allow_sensitive_ekus``: keep OCSPSigning/timeStamping from the CSR —
        reserved for the admin Sign-CSR path (an operator explicitly signing a
        delegated responder/TSA CSR); protocol enrollees never get them.
        ``require_pop=False`` skips the self-signature (proof-of-possession)
        check — only WSTEP passes this, for CSRs unwrapped from a PKCS#7/CMC
        envelope whose inner CertificationRequest isn't reliably self-signed
        by real Windows clients (see wstep_service._validate_csr, which
        makes the same exception for the same reason).
        ``ms_certificate_template_oid``: see the extension-building block
        below — only WSTEP passes this.
        ``override_subject``: replaces the CSR's own (possibly empty)
        subject before anything else happens with it — only WSTEP's Kerberos
        binding passes this, for the "naked" (no CN, no SAN) CSRs real
        Windows GPO autoenrollment submits for templates configured to build
        the subject from AD, trusting the CA to derive it server-side (see
        services/ad_connector/lookup.py). Computed before NameConstraints
        validation below, not after, so the constraint check sees the name
        that will actually land on the certificate rather than the raw
        CSR's own (empty) one — applying it later would let a CA's
        NameConstraints be silently bypassed by whatever subject was
        derived server-side.
        ``override_san``: replaces the auto-synthesized SAN outright when
        given, instead of deriving it from ``override_subject``'s CN via
        ``_synthesize_san_from_subject``. Needed for AD-derived user
        subjects: a user's directory-path CN (e.g. "Roy Hagland") isn't a
        DNS name or email address, so synthesis would build a nonsensical
        DNSName SAN entry — real ADCS instead puts the user's UPN in SAN as
        a Microsoft OtherName, which the caller (wstep_service) builds and
        passes here directly.
        ``requester_sid``: the authenticated requester's AD SID (
        ``"S-1-5-21-..."`` string form), embedded as the SID security
        extension (KB5014754 strong certificate mapping) — only WSTEP's
        Kerberos binding passes this, independent of ``override_subject``
        (applies to naked and normal CSRs alike, since it identifies who
        authenticated, not what subject was requested)."""
        from utils.eku_validation import normalize_extra_ekus, to_object_identifiers, merge_eku_lists

        # Load CSR
        csr = x509.load_pem_x509_csr(csr_pem, default_backend())
        if require_pop and not csr.is_signature_valid:
            raise ValueError("CSR has invalid signature")

        # Key-strength floor. Enforced here rather than at each caller so every
        # issuance path (admin sign-CSR, ACME finalize, EST/SCEP, renewal)
        # inherits it from the one place that actually applies a CA signature.
        from utils.key_type import validate_enrollment_public_key
        key_err = validate_enrollment_public_key(csr.public_key())
        if key_err:
            raise ValueError(f"CSR public key rejected: {key_err}")

        # Effective subject: an override (if any) wins outright; otherwise
        # fall back to populating CN from the CSR's own first SAN DNS name
        # or IP address if the CSR's subject is empty.
        subject = override_subject if override_subject is not None else csr.subject
        if not list(subject):
            try:
                san_ext = csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                for name in san_ext.value:
                    if isinstance(name, x509.DNSName):
                        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name.value)])
                        break
                    elif isinstance(name, x509.IPAddress):
                        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(name.value))])
                        break
            except x509.ExtensionNotFound:
                pass

        # Effective SAN for constraint-checking: the CSR's own SAN extension
        # if it has one, else whatever will be auto-synthesized from the
        # (possibly overridden) subject below -- NameConstraints must see
        # the name that will actually land on the certificate, not an empty
        # list just because the CSR itself omitted SAN.
        try:
            san_ext = csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            csr_sans = list(san_ext.value)
            has_csr_san = True
        except x509.ExtensionNotFound:
            csr_sans = None
            has_csr_san = False

        if override_san is not None:
            effective_sans = override_san
        elif has_csr_san:
            effective_sans = csr_sans
        else:
            effective_sans = _synthesize_san_from_subject(subject)

        ConstraintsMixin._validate_name_constraints(
            ca_cert, subject, effective_sans if effective_sans else None, renewal_of=renewal_of
        )

        # Build certificate from CSR
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.public_key(csr.public_key())
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(cert_not_before())
        builder = builder.not_valid_after(
            utc_now() + timedelta(days=validity_days)
        )

        # Copy only extensions appropriate for the requested certificate role.
        # CA-only constraints from an enrollee CSR must never reach a leaf.
        issuing_ca = cert_type == 'intermediate_ca'
        try:
            csr_basic_constraints = csr.extensions.get_extension_for_oid(
                ExtensionOID.BASIC_CONSTRAINTS
            )
        except x509.ExtensionNotFound:
            csr_basic_constraints = None

        if (
            issuing_ca
            and csr_basic_constraints is not None
            and not csr_basic_constraints.value.ca
        ):
            raise ValueError(
                "Intermediate CA CSR BasicConstraints must set ca=True"
            )

        # A template bound to the issuance context (an ACME profile): its
        # KU/EKU replace the CSR's, the operator bound that policy to the
        # endpoint explicitly (same rule as SCEP profiles, #228). Leaves only.
        tpl_ku, tpl_ekus = (None, None)
        if not issuing_ca and template_ext:
            tpl_ku, tpl_ekus = _template_key_purposes(template_ext, allow_sensitive_ekus)

        # Never copy SKI/AKI from the CSR — always derive them from the keys.
        skip_from_csr = {
            ExtensionOID.SUBJECT_KEY_IDENTIFIER,
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER,
        }
        for extension in csr.extensions:
            if extension.oid in skip_from_csr:
                continue
            if not issuing_ca and extension.oid not in _LEAF_CSR_COPYABLE_EXTENSION_OIDS:
                logger.info(
                    "sign_csr: ignoring CSR extension %s -- not one a leaf "
                    "request may set (issuer-controlled or unknown)",
                    extension.oid.dotted_string,
                )
                continue
            if extension.oid == ExtensionOID.BASIC_CONSTRAINTS:
                if issuing_ca:
                    constraints = _capped_basic_constraints(
                        extension.value, ca_cert
                    )
                else:
                    constraints = x509.BasicConstraints(ca=False, path_length=None)
                builder = builder.add_extension(constraints, critical=True)
                continue
            if extension.oid == ExtensionOID.KEY_USAGE:
                if tpl_ku is not None:
                    continue  # the bound template governs Key Usage
                usage = _key_usage_with_ca_signing(
                    extension.value, enabled=issuing_ca
                )
                # RFC 5280 §4.2.1.3: conforming CAs mark Key Usage critical;
                # the CSR's own flag is not what decides it on a leaf either.
                builder = builder.add_extension(usage, critical=True)
                continue
            if extension.oid == ExtensionOID.EXTENDED_KEY_USAGE and not issuing_ca:
                if tpl_ekus is not None:
                    continue  # the bound template governs Extended Key Usage
                safe_ekus, dropped_oids = _filter_csr_ekus(
                    extension.value, cert_type, allow_sensitive_ekus,
                    renewal_of=renewal_of,
                )
                if dropped_oids:
                    logger.warning(
                        "sign_csr: dropped EKU(s) %s from CSR — not permitted "
                        "for certificate type %r (the resolved certificate "
                        "type, not the CSR, decides leaf key purposes)",
                        [oid.dotted_string for oid in dropped_oids], cert_type,
                    )
                if safe_ekus:
                    builder = builder.add_extension(
                        x509.ExtendedKeyUsage(safe_ekus), extension.critical
                    )
                    builder = add_ocsp_nocheck_if_responder(builder, safe_ekus)
                continue
            if extension.oid == ExtensionOID.OCSP_NO_CHECK and any(
                e.oid == ExtensionOID.OCSP_NO_CHECK for e in builder._extensions
            ):
                # Already added next to the OCSPSigning EKU above: a request
                # built the right way carries it too (#347 review)
                continue
            if extension.oid == ExtensionOID.TLS_FEATURE:
                # A requested Must-Staple (status_request) joins whatever
                # TLS features the CSR asked for, instead of the CSR's own
                # feature list silently displacing it below.
                features = list(extension.value)
                if ocsp_must_staple and x509.TLSFeatureType.status_request not in features:
                    features.append(x509.TLSFeatureType.status_request)
                builder = builder.add_extension(x509.TLSFeature(features), extension.critical)
                continue
            if extension.oid == ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
                # RFC 5280 §4.2.1.6: SAN MUST be critical when the subject
                # is empty -- the CSR's flag cannot override that.
                builder = builder.add_extension(
                    extension.value, extension.critical or len(subject) == 0
                )
                continue
            builder = builder.add_extension(extension.value, extension.critical)

        # Auto-add SAN from CN if the CSR had no SAN extension -- reuses
        # effective_sans, already computed above for NameConstraints, so
        # what got constraint-checked and what actually lands on the
        # certificate can't drift apart.
        if not has_csr_san and effective_sans:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(effective_sans),
                critical=len(subject) == 0,
            )

        # Add basic extensions if not in CSR
        try:
            csr.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        except x509.ExtensionNotFound:
            if cert_type == 'intermediate_ca':
                # Route the default through the same clamp as a CSR-supplied
                # BasicConstraints: UCM's own generate_csr emits no
                # BasicConstraints at all, so without this the pathLen-0
                # refusal above never fired on the default API path (the
                # clamp itself is a no-op for any parent that may issue a
                # sub-CA, since the requested 0 is always within budget).
                builder = builder.add_extension(
                    _capped_basic_constraints(
                        x509.BasicConstraints(ca=True, path_length=0), ca_cert
                    ),
                    critical=True,
                )
            else:
                builder = builder.add_extension(
                    x509.BasicConstraints(ca=False, path_length=None),
                    critical=True,
                )

        # Add key usage based on cert type, unless the CSR or the bound
        # template supplied one (the template's replaces the CSR's, skipped
        # in the copy loop above)
        if tpl_ku is not None:
            builder = builder.add_extension(tpl_ku, critical=True)
            has_key_usage = True
        else:
            try:
                csr.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
                has_key_usage = True
            except x509.ExtensionNotFound:
                has_key_usage = False
        if not has_key_usage:
            if cert_type == 'intermediate_ca':
                builder = builder.add_extension(
                    x509.KeyUsage(
                        digital_signature=True, key_encipherment=False,
                        content_commitment=False, data_encipherment=False,
                        key_agreement=False, key_cert_sign=True, crl_sign=True,
                        encipher_only=False, decipher_only=False,
                    ),
                    critical=True,
                )
            elif cert_type in ('server_cert', 'device_cert'):
                # device_cert is the EST profile: before it existed, EST signed
                # under server_cert and its no-KeyUsage CSRs (the plain
                # `openssl req -new` shape) got this TLS pair. The profile
                # split must not silently drop the extension — a leaf with no
                # KeyUsage is unrestricted (RFC 5280 §4.2.1.3).
                builder = builder.add_extension(
                    x509.KeyUsage(
                        digital_signature=True, key_encipherment=True,
                        content_commitment=False, data_encipherment=False,
                        key_agreement=False, key_cert_sign=False, crl_sign=False,
                        encipher_only=False, decipher_only=False,
                    ),
                    critical=True,
                )

        # Add Extended Key Usage if not in CSR
        extra_oid_strs, extra_err = normalize_extra_ekus(extra_ekus)
        if extra_err:
            raise ValueError(f'Invalid extra_ekus: {extra_err}')
        extra_oids = to_object_identifiers(extra_oid_strs)

        try:
            existing_eku = csr.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
            csr_has_eku = True
        except x509.ExtensionNotFound:
            existing_eku = None
            csr_has_eku = False

        if tpl_ekus is not None:
            # The bound template governs Extended Key Usage (the CSR's own
            # was skipped in the copy loop); operator extra_ekus still merge
            # on top, as on the issue form. Renewal at par does not apply:
            # the template is the policy, prior EKUs outside it are not
            # resurrected. A template whose every EKU was refused imposes
            # the cert_type default profile, never the CSR's request.
            if not tpl_ekus:
                logger.warning(
                    "sign_csr: every template EKU was refused for certificate "
                    "type %r; issuing its default profile instead", cert_type,
                )
            merged = merge_eku_lists(
                tpl_ekus or _default_ekus_for_cert_type(cert_type), extra_oids
            )
            if merged:
                builder = builder.add_extension(
                    x509.ExtendedKeyUsage(merged), critical=False
                )
                builder = add_ocsp_nocheck_if_responder(builder, merged)
        elif not csr_has_eku:
            base_eku = _default_ekus_for_cert_type(cert_type)
            # Renewal at par applies to a CSR that requests nothing as well:
            # the type's default profile is not necessarily what the
            # certificate being renewed carries (an EST device_cert enrolment
            # gets serverAuth+clientAuth; scheduled auto-renewal re-signs the
            # stored no-EKU CSR under the default server_cert). Without this,
            # renewal silently narrows the leaf — the exact failure
            # renewal_of exists to prevent. The hard block-list still wins:
            # OCSPSigning, timeStamping, anyEKU and Smartcard Logon are never
            # resurrected from a prior certificate. Deliberately NOT routed
            # through _filter_csr_ekus: an all-blocked prior set on an
            # unprofiled type would hit its empty-kept fallback and raise,
            # turning a renewal into a hard failure.
            prior_kept = [
                oid for oid in _prior_ekus(renewal_of)
                if oid not in _LEAF_FORBIDDEN_EKU_OIDS
                and oid not in (_ANY_EKU_OID, _SMARTCARD_LOGON_OID)
            ]
            if prior_kept:
                base_eku = merge_eku_lists(base_eku, prior_kept)
            merged = merge_eku_lists(base_eku, extra_oids)
            if merged:
                builder = builder.add_extension(
                    x509.ExtendedKeyUsage(merged),
                    critical=False,
                )
                builder = add_ocsp_nocheck_if_responder(builder, merged)
        elif extra_oids:
            # Re-merging the CSR's original EKUs must not resurrect the
            # sensitive ones the copy loop above just dropped
            csr_ekus, _dropped = _filter_csr_ekus(
                existing_eku.value, cert_type, allow_sensitive_ekus,
                renewal_of=renewal_of,
            )
            merged = merge_eku_lists(csr_ekus, extra_oids)
            new_builder = x509.CertificateBuilder()
            new_builder = new_builder.subject_name(builder._subject_name)
            new_builder = new_builder.issuer_name(builder._issuer_name)
            new_builder = new_builder.public_key(builder._public_key)
            new_builder = new_builder.serial_number(builder._serial_number)
            new_builder = new_builder.not_valid_before(builder._not_valid_before)
            new_builder = new_builder.not_valid_after(builder._not_valid_after)
            for ext in builder._extensions:
                if ext.oid == ExtensionOID.EXTENDED_KEY_USAGE:
                    continue
                new_builder = new_builder.add_extension(ext.value, ext.critical)
            new_builder = new_builder.add_extension(
                x509.ExtendedKeyUsage(merged), critical=existing_eku.critical
            )
            new_builder = add_ocsp_nocheck_if_responder(new_builder, merged)
            builder = new_builder

        if not issuing_ca:
            # RFC 5480 §3: a non-RSA key cannot honour keyEncipherment /
            # dataEncipherment, whether the CSR asked for them or the
            # cert_type default above did (#327). Applied once the EKU is
            # settled, because an S/MIME leaf on an EC key keeps its
            # encryption intent as keyAgreement instead of losing it.
            builder = constrain_builder_key_usage(builder)

        def _sub_ca_csr_supplied(oid) -> bool:
            # A leaf never gets these from its CSR (dropped by the allow-list
            # above), so the CA's own configuration always applies to it.
            if not issuing_ca:
                return False
            try:
                csr.extensions.get_extension_for_oid(oid)
                return True
            except x509.ExtensionNotFound:
                return False

        # CRL Distribution Points
        all_cdp = cdp_urls or ([cdp_url] if cdp_url else [])
        if all_cdp:
            if not _sub_ca_csr_supplied(ExtensionOID.CRL_DISTRIBUTION_POINTS):
                dist_points = [
                    x509.DistributionPoint(
                        full_name=[x509.UniformResourceIdentifier(url)],
                        relative_name=None, reasons=None, crl_issuer=None
                    )
                    for url in all_cdp
                ]
                builder = builder.add_extension(
                    x509.CRLDistributionPoints(dist_points),
                    critical=False
                )

        # Authority Information Access
        all_ocsp = ocsp_urls or ([ocsp_url] if ocsp_url else [])
        all_aia = aia_ca_issuers_urls or ([aia_ca_issuers_url] if aia_ca_issuers_url else [])
        aia_descriptions = []
        for uri in all_ocsp:
            aia_descriptions.append(
                x509.AccessDescription(
                    x509.oid.AuthorityInformationAccessOID.OCSP,
                    x509.UniformResourceIdentifier(uri)
                )
            )
        for url in all_aia:
            aia_descriptions.append(
                x509.AccessDescription(
                    x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                    x509.UniformResourceIdentifier(url)
                )
            )
        if aia_descriptions:
            if not _sub_ca_csr_supplied(ExtensionOID.AUTHORITY_INFORMATION_ACCESS):
                builder = builder.add_extension(
                    x509.AuthorityInformationAccess(aia_descriptions),
                    critical=False
                )

        # Certificate Policies
        if cps_uri:
            if not _sub_ca_csr_supplied(ExtensionOID.CERTIFICATE_POLICIES):
                policy_oid_obj = x509.ObjectIdentifier(cps_oid or '2.5.29.32.0')
                builder = builder.add_extension(
                    x509.CertificatePolicies([
                        x509.PolicyInformation(
                            policy_identifier=policy_oid_obj,
                            policy_qualifiers=[cps_uri]
                        )
                    ]),
                    critical=False
                )

        # SubjectKeyIdentifier — always from the CSR subject public key
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(csr.public_key()),
            critical=False
        )

        # AuthorityKeyIdentifier — always from the issuing CA's SKI
        builder = builder.add_extension(
            authority_key_identifier_from_issuer(ca_cert),
            critical=False
        )

        # OCSP Must-Staple (a CSR carrying TLSFeature had status_request
        # merged into it in the copy loop above)
        if ocsp_must_staple and not any(
            e.oid == ExtensionOID.TLS_FEATURE for e in builder._extensions
        ):
            builder = builder.add_extension(
                x509.TLSFeature([x509.TLSFeatureType.status_request]),
                critical=False,
            )

        # Microsoft Certificate Template extension (szOID_CERTIFICATE_TEMPLATE,
        # 1.3.6.1.4.1.311.21.7) — only WSTEP passes this. Real Windows clients
        # read this back off the issued cert to confirm it matches the policy
        # they selected via XCEP; a cert with no template property at all was
        # observed failing CX509Enrollment::Enroll with CERTSRV_E_PROPERTY_EMPTY
        # ("the requested property value is empty") during real-client interop
        # testing. `cryptography` has no built-in type for this MS-CRTD
        # extension, so it's hand-built and added as UnrecognizedExtension.
        if ms_certificate_template_oid:
            builder = builder.add_extension(
                _certificate_template_extension(ms_certificate_template_oid),
                critical=False,
            )

        # Microsoft SID security extension (szOID_NTDS_CA_SECURITY_EXT,
        # 1.3.6.1.4.1.311.25.2) for KB5014754 strong certificate mapping —
        # only WSTEP's Kerberos binding passes this, with the requester's
        # own AD SID once resolved via the AD Connector. Non-critical,
        # matching real ADCS's own issuance (confirmed against a captured
        # real cert — see _ad_security_extension's docstring).
        if requester_sid:
            builder = builder.add_extension(
                _ad_security_extension(requester_sid),
                critical=False,
            )

        # Sign
        hash_algo = HASH_ALGORITHMS.get(digest, hashes.SHA256())
        certificate = builder.sign(
            private_key=ca_private_key,
            algorithm=signing_hash_for(ca_private_key, hash_algo),
            backend=default_backend()
        )

        # Apply the Certificate Transparency policy (embed SCTs, enforce
        # ct_required) for leaf certs. This is the shared issuance path for
        # ACME finalize, EST and the API sign-CSR endpoint — previously only
        # the web create-certificate path honored CT, so ct_required silently
        # did nothing for ACME. Never applied to intermediate CAs.
        if not issuing_ca:
            from utils.ct_client import apply_ct_policy
            certificate, _ = apply_ct_policy(certificate, ca_cert, ca_private_key)

        return certificate.public_bytes(serialization.Encoding.PEM)
