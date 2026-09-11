"""
MS-XCEP policy response construction (GetPoliciesResponse).

Builds the SOAP/XML body Windows clients (MMC "Request New Certificate",
certreq, GPO autoenrollment) expect from a Certificate Enrollment Policy
Web Service's ``GetPolicies`` operation. Pure XML construction: no Flask
or DB writes happen here, only reads of already-loaded ``CA`` /
``CertificateTemplate`` rows, mirroring how ``services/scep/response_builder.py``
keeps wire-format construction separate from protocol orchestration.

Element shapes follow the published MS-XCEP XML Schema (Microsoft Open
Specifications, MS-XCEP section "XML Schema"), including the
``cA``/``cAReferenceID``/``CAURICollection`` indirection, integer
``oIDs/oID/group`` values, and EKU conveyed as a real DER-encoded X.509
extension. ``oIDs/oID/group`` values: 1=hash algorithm, 2=encryption
algorithm, 3=public key, 4=signing algorithm, 5=RDN, 6=certificate
extension/attribute, 7=EKU, 8=certificate policy, 9=enrollment object --
load-bearing for template-by-name resolution in real Windows clients, not
just documentation trivia (wrong values silently break
``CX509CertificateTemplates::get_ItemByName``).

``privateKeyAttributes``'s ``keySpec``/``cryptoProviders``/
``algorithmOIDReference`` values (see the constants below) are verified
against a real Windows Server ADCS deployment's own ``GetPoliciesResponse``
(captured via ``System.ServiceModel.MessageLogging`` on a lab Enterprise
CA), since the published schema only marks these nillable without saying
whether real clients tolerate the nil.
"""
import base64
import json
import struct
import uuid

from asn1crypto import x509 as asn1_x509
from lxml import etree

from services.wstep.soap_envelope import build_envelope

XCEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy'
SOAP_NS = 'http://www.w3.org/2003/05/soap-envelope'
XSI_NS = 'http://www.w3.org/2001/XMLSchema-instance'

NSMAP = {'xcep': XCEP_NS, 'xsi': XSI_NS}

# wsaw:Action for the GetPolicies operation's output message, per the
# published MS-XCEP WSDL. Required: a real client expects the response to
# carry this Action and echo the request's a:MessageID back as
# a:RelatesTo, matching the published GetPolicies message-exchange pattern.
ACTION_GET_POLICIES_RESPONSE = (
    'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy/IPolicy/GetPoliciesResponse'
)

# X509EnrollmentAuthFlags (certcli.h) -- confirmed to share wire values with
# MS-XCEP's CAURI/clientAuthentication per Microsoft documentation.
AUTH_ANONYMOUS = 1
AUTH_KERBEROS = 2
AUTH_USERNAME_PASSWORD = 4
AUTH_CLIENT_CERTIFICATE = 8

# oIDs/oID/group -- real MS-XCEP enum values (see module docstring).
# No group entry for the key algorithm OID: algorithmOIDReference is
# always nil (real-ADCS trace), so there's no reference to mint.
_GROUP_POLICY = 9  # "Enrollment object identifier" (the template's own OID)
_GROUP_EXTENSION = 6  # "Certificate extension or attribute identifier"

# id-ce-extKeyUsage / id-ce-keyUsage (RFC 5280) -- the extension OIDs
# referenced by attributes/extensions/extension/oIDReference. Distinct from
# the EKU *purpose* OIDs (serverAuth etc.), which are no longer individually
# OID-table-referenced now that they're embedded in the DER extension value.
_EXT_KEY_USAGE_OID = '2.5.29.15'
_EXT_EXTENDED_KEY_USAGE_OID = '2.5.29.37'


# UCM's extensions_template.key_usage entries (camelCase, matching X.509
# naming) -> asn1crypto.x509.KeyUsage's NamedBitList set names.
_KEY_USAGE_BITS = {
    'digitalSignature': 'digital_signature',
    'nonRepudiation': 'non_repudiation',
    'keyEncipherment': 'key_encipherment',
    'dataEncipherment': 'data_encipherment',
    'keyAgreement': 'key_agreement',
    'keyCertSign': 'key_cert_sign',
    'cRLSign': 'crl_sign',
    'encipherOnly': 'encipher_only',
    'decipherOnly': 'decipher_only',
}

# key_type -> (algorithm OID, algorithm name, minimal key length in bits)
_KEY_TYPE_INFO = {
    'RSA-2048': ('1.2.840.113549.1.1.1', 'RSA', 2048),
    'RSA-3072': ('1.2.840.113549.1.1.1', 'RSA', 3072),
    'RSA-4096': ('1.2.840.113549.1.1.1', 'RSA', 4096),
    'EC-P256': ('1.2.840.10045.3.1.7', 'ECDSA_P256', 256),
    'EC-P384': ('1.3.132.0.34', 'ECDSA_P384', 384),
    'EC-P521': ('1.3.132.0.35', 'ECDSA_P521', 521),
}
_DEFAULT_KEY_TYPE_INFO = ('1.2.840.113549.1.1.1', 'RSA', 2048)

# privateKeyAttributes/keySpec + cryptoProviders, by algorithm family.
# Confirmed against a real ADCS server's own WCF trace: every real
# template populates both -- RSA uses keySpec=1 (AT_KEYEXCHANGE, the
# legacy CryptoAPI key spec) with legacy CSP names; leaving
# cryptoProviders nil let a real Windows client silently fall back to a
# legacy provider defaulting to a 1024-bit key regardless of
# minimalKeyLength. ECDSA has no legacy-CSP equivalent (only CNG Key
# Storage Providers support it), so it gets the modern KSP and no keySpec
# (a legacy-CryptoAPI-only concept with no CNG equivalent).
_RSA_KEY_SPEC = '1'
_RSA_CRYPTO_PROVIDERS = ('Microsoft Enhanced RSA and AES Cryptographic Provider',)
_ECDSA_CRYPTO_PROVIDERS = ('Microsoft Software Key Storage Provider',)

# subjectNameFlags: client supplies Subject (0x1) + SubjectAltName (0x10000).
# Matches how EST/SCEP already accept a client-supplied CSR subject/SAN
# rather than deriving it server-side from AD attributes (which UCM, not
# being AD-backed, has no equivalent source for anyway).
_SUBJECT_NAME_FLAGS = 0x00000001 | 0x00010000

# Machine templates get a different subjectNameFlags value: CT_FLAG_SUBJECT_
# REQUIRE_DNS_AS_CN (0x10000000) | CT_FLAG_SUBJECT_ALT_REQUIRE_DNS (0x08000000),
# with none of _SUBJECT_NAME_FLAGS's enrollee-supplies bits. Confirmed against
# the lab's real ADCS Enterprise CA: its built-in "Computer" template's own
# msPKI-Certificate-Name-Flag AD attribute is exactly 0x18000000, with no
# ENROLLEE_SUPPLIES_SUBJECT bit at all. That's not an AD-attribute quirk --
# it's load-bearing for unattended GPO machine autoenrollment: with the
# enrollee-supplies-subject flags, Windows' interactive "Request New
# Certificate" wizard shows a "more information is required" prompt (a human
# must fill in Properties > Subject), which the unattended background
# autoenrollment engine has no way to satisfy -- confirmed against the lab
# that autoenrollment silently declines every other eligible machine template
# with zero errors logged, while a manually-supplied-subject enrollment of the
# same template type succeeds. These auto-derive bits tell Windows to build
# CN/SAN from the computer's own DNS name itself, with no prompt needed --
# unlike the user-template rationale above, this doesn't require UCM to
# derive anything server-side; the machine already knows its own identity.
_MACHINE_SUBJECT_NAME_FLAGS = 0x10000000 | 0x08000000

# Per-template opt-in (CertificateTemplate.ad_derived_subject) gets its own
# subjectNameFlags: CT_FLAG_SUBJECT_REQUIRE_DIRECTORY_PATH (0x80000000) |
# CT_FLAG_SUBJECT_ALT_REQUIRE_UPN (0x02000000) -- real ADCS's built-in
# "User" template is 0xA6000000, which also sets CT_FLAG_SUBJECT_REQUIRE_EMAIL
# (0x20000000) and CT_FLAG_SUBJECT_ALT_REQUIRE_EMAIL (0x04000000). Those two
# are deliberately NOT advertised here: UCM's AD-derived subject only ever
# produces a directory-path Subject + UPN SAN (see
# services/wstep/wstep_service.py's lookup_user_ad_identity handling), never
# an email attribute. Advertising REQUIRE_EMAIL would make Windows decline
# autoenrollment outright for any AD user with no `mail` attribute set (a
# real, common case, not an edge case), and would claim an email address the
# CA never actually emits into the issued certificate. Email support is a
# separate, later decision -- not a corner this cuts silently.
_USER_AD_DERIVED_SUBJECT_NAME_FLAGS = 0x80000000 | 0x02000000

# enrollmentFlags: none of the AD-attribute-writeback / S/MIME bits apply.
_ENROLLMENT_FLAGS = 0

# generalFlags bit 0x00000040 = GeneralMachineType: "this template is for
# an end entity that represents a machine." Load-bearing: leaving it nil
# made a real client default a server-type template like "Web Server" to
# user-type, which then refused to enroll from a Computer-context request
# ("This type of certificate can be issued only to a user").
# UCM's CertificateTemplate.template_type has no explicit machine/user
# axis, so this is a judgment call per type: service/device templates get
# the machine bit, personal-identity ones don't. vpn_client is included
# since device-tunnel VPN certs bound to a computer identity are the
# common GPO computer-autoenrollment pattern this targets.
_GENERAL_MACHINE_TYPE = 0x00000040
_MACHINE_TEMPLATE_TYPES = {'web_server', 'vpn_server', 'vpn_client', 'ocsp_signing'}

# Stable namespace for deriving per-CA policy OIDs and policyIDs via uuid5,
# which keeps derived values stable across requests -- matters both for a
# client's policiesNotChanged caching and for the OID shape built in
# _policy_oid_for_template below.
_POLICY_OID_NAMESPACE = uuid.UUID('a12b3c4d-5e6f-4789-9abc-def012345678')


class _OidTable:
    """Accumulates the distinct OIDs referenced by policies and assigns
    each a stable per-response integer reference ID, as MS-XCEP's
    ``oIDs``/``*OIDReference`` indirection requires."""

    def __init__(self):
        self._by_oid = {}
        self._next_id = 1

    def ref(self, oid, group, default_name=None):
        if oid not in self._by_oid:
            self._by_oid[oid] = {
                'id': self._next_id,
                'group': group,
                'default_name': default_name or oid,
            }
            self._next_id += 1
        return self._by_oid[oid]['id']

    def entries(self):
        return sorted(self._by_oid.items(), key=lambda kv: kv[1]['id'])


def _nil_element(parent, local_name):
    """Add ``<local_name xsi:nil="true"/>`` to ``parent``.

    Several MS-XCEP elements are declared ``nillable="true"`` **without**
    ``minOccurs="0"`` -- nillable is not the same as optional. Such an
    element still MUST be present in the sequence, just with
    ``xsi:nil="true"`` instead of real content. Omitting it outright makes
    a strict XML deserializer reject the whole response
    (WS_E_INVALID_FORMAT).
    """
    el = etree.SubElement(parent, '{%s}%s' % (XCEP_NS, local_name))
    el.set('{%s}nil' % XSI_NS, 'true')
    return el


def _resolve_templates_for_ca(ca, all_active_templates):
    """Templates pinned to this CA, or every active template when none are
    pinned — mirrors the fallback the Templates UI already uses so XCEP
    doesn't expose an empty policy set to a CA nobody has curated yet."""
    pinned = [pin.template for pin in (ca.template_pins or []) if pin.template and pin.template.is_active]
    if pinned:
        return pinned
    return list(all_active_templates)


def _key_type_info(key_type):
    return _KEY_TYPE_INFO.get((key_type or '').upper(), _DEFAULT_KEY_TYPE_INFO)


def _policy_oid_for_template(ca, template):
    """A stable per-(CA, template) policy OID.

    Must not be a single arc holding a full 128-bit value (e.g. the
    ITU-T X.667 ``2.25.<uuid-as-decimal>`` form) -- valid ASN.1, but a
    real Windows client's ``CX509EnrollmentPolicyWebService.GetTemplates()``
    silently aborts building the rest of the collection when a non-first
    policy's OID has an arc that large (a certenroll.dll limitation,
    confirmed by enumerating the COM collection directly and watching
    Count stay at 1 regardless of which/how many templates were pinned).
    Real ADCS's own template OIDs avoid this by using Microsoft's private
    arc with several smaller components, each within uint32
    (e.g. ``1.3.6.1.4.1.311.21.8.12100116.9312244.4475799.14553909.6134364.73.1.7``).
    This mirrors that shape: a per-CA stable prefix (four uint32 chunks
    derived from the CA's refid) plus the template's own integer id.
    """
    seed = uuid.uuid5(_POLICY_OID_NAMESPACE, f'ucm-ca-{ca.refid}')
    chunks = struct.unpack('>4I', seed.bytes)
    return '1.3.6.1.4.1.311.21.8.{}.{}.{}.{}.1.{}'.format(*chunks, template.id)


def _policy_id_for_ca(ca):
    """A stable ``response/policyID`` for this CA -- must be deterministic,
    not a fresh random UUID per response.

    Real ADCS uses a stable ID (Windows caches a policy server's
    ``PolicyID`` in the registry at enrollment-policy-registration time).
    A randomized policyID broke real-client template resolution outright
    (Windows appears to key its per-response template collection off
    policyID), independent of the OID-arc-size issue fixed in
    ``_policy_oid_for_template``.
    """
    derived = uuid.uuid5(_POLICY_OID_NAMESPACE, f'ucm-ca-policy-{ca.refid}')
    return str(derived)


def _build_extensions_element(attributes, extensions, oids):
    """attributes/extensions -- real X.509 extensions (KeyUsage,
    ExtendedKeyUsage) DER-encoded and referenced by OID, per the MS-XCEP
    schema."""
    entries = []  # list of (oid, critical, der_bytes)

    eku_list = extensions.get('extended_key_usage')
    if not isinstance(eku_list, list):
        eku_list = []
    # Same resolver as issuance, so the policy advertises exactly what the
    # template will issue whatever spelling the template uses
    from utils.eku_validation import normalize_extra_ekus
    eku_oids = []
    for name in eku_list:
        if not isinstance(name, str):
            continue
        resolved, err = normalize_extra_ekus([name])
        if err or not resolved:
            continue  # an unknown name is ignored, the others still apply
        if resolved[0] not in eku_oids:
            eku_oids.append(resolved[0])
    if eku_oids:
        der = asn1_x509.ExtKeyUsageSyntax(eku_oids).dump()
        entries.append((_EXT_EXTENDED_KEY_USAGE_OID, False, der))

    ku_list = extensions.get('key_usage')
    if not isinstance(ku_list, list):
        ku_list = []
    ku_bits = {
        _KEY_USAGE_BITS[name] for name in ku_list
        if isinstance(name, str) and name in _KEY_USAGE_BITS
    }
    if ku_bits:
        der = asn1_x509.KeyUsage(ku_bits).dump()
        entries.append((_EXT_KEY_USAGE_OID, True, der))

    if not entries:
        _nil_element(attributes, 'extensions')
        return

    extensions_el = etree.SubElement(attributes, '{%s}extensions' % XCEP_NS)
    for oid, critical, der in entries:
        ext_ref = oids.ref(oid, group=_GROUP_EXTENSION)
        ext_el = etree.SubElement(extensions_el, '{%s}extension' % XCEP_NS)
        etree.SubElement(ext_el, '{%s}oIDReference' % XCEP_NS).text = str(ext_ref)
        etree.SubElement(ext_el, '{%s}critical' % XCEP_NS).text = (
            'true' if critical else 'false'
        )
        etree.SubElement(ext_el, '{%s}value' % XCEP_NS).text = (
            base64.b64encode(der).decode('ascii')
        )


def build_get_policies_response(ca, templates, enrollment_uris=(), message_id=None):
    """Build an MS-XCEP ``GetPoliciesResponse`` SOAP envelope.

    Args:
        ca: the configured ``CA`` row (must have ``crt``/``refid``/``descr``).
        templates: iterable of active ``CertificateTemplate`` rows to expose
            when none are pinned to ``ca`` (the pinned set wins otherwise).
        enrollment_uris: iterable of ``(client_authentication, uri,
            renewal_only)`` tuples advertising the WSTEP CES endpoint(s) a
            client should use to actually enroll -- without this a client
            can discover policy but has nowhere to send the RST.
        message_id: the incoming request's ``a:MessageID``, echoed back as
            ``a:RelatesTo`` in the response header (see
            ``ACTION_GET_POLICIES_RESPONSE``'s comment for why this
            matters to a real client).

    Returns:
        bytes: UTF-8 encoded, well-formed SOAP XML.
    """
    oids = _OidTable()
    resolved_templates = _resolve_templates_for_ca(ca, templates)

    response_root = etree.Element('{%s}GetPoliciesResponse' % XCEP_NS, nsmap=NSMAP)

    response = etree.SubElement(response_root, '{%s}response' % XCEP_NS)
    etree.SubElement(response, '{%s}policyID' % XCEP_NS).text = _policy_id_for_ca(ca)
    etree.SubElement(response, '{%s}policyFriendlyName' % XCEP_NS).text = (
        f'Ultimate CA Manager - {ca.descr or ca.refid}'
    )
    # Hint to the client how long it may cache this policy before polling
    # again. 8 hours matches the default GPO autoenrollment poll interval.
    etree.SubElement(response, '{%s}nextUpdateHours' % XCEP_NS).text = '8'
    etree.SubElement(response, '{%s}policiesNotChanged' % XCEP_NS).text = 'false'

    policies = etree.SubElement(response, '{%s}policies' % XCEP_NS)

    # Single CA in this response -> single cAReferenceID, minted once and
    # reused by every policy's cAs/cAReference (int indirection, not the
    # CA's string refid).
    ca_ref_id = 1

    for template in resolved_templates:
        extensions = {}
        if template.extensions_template:
            try:
                parsed = json.loads(template.extensions_template)
                if isinstance(parsed, dict):
                    extensions = parsed
            except (TypeError, ValueError):
                pass

        _algo_oid, algo_name, min_key_length = _key_type_info(template.key_type)
        policy_oid = _policy_oid_for_template(ca, template)
        policy_ref = oids.ref(policy_oid, group=_GROUP_POLICY, default_name=template.name)

        policy = etree.SubElement(policies, '{%s}policy' % XCEP_NS)
        etree.SubElement(policy, '{%s}policyOIDReference' % XCEP_NS).text = str(policy_ref)
        cas_el = etree.SubElement(policy, '{%s}cAs' % XCEP_NS)
        etree.SubElement(cas_el, '{%s}cAReference' % XCEP_NS).text = str(ca_ref_id)

        attributes = etree.SubElement(policy, '{%s}attributes' % XCEP_NS)
        etree.SubElement(attributes, '{%s}commonName' % XCEP_NS).text = template.name
        etree.SubElement(attributes, '{%s}policySchema' % XCEP_NS).text = '2'

        validity = etree.SubElement(attributes, '{%s}certificateValidity' % XCEP_NS)
        validity_seconds = int(template.validity_days or 397) * 86400
        etree.SubElement(validity, '{%s}validityPeriodSeconds' % XCEP_NS).text = str(validity_seconds)
        # Offer renewal starting at 80% of validity elapsed — matches the
        # rule of thumb ADCS templates use and UCM's own auto-renewal window.
        etree.SubElement(validity, '{%s}renewalPeriodSeconds' % XCEP_NS).text = str(
            int(validity_seconds * 0.2)
        )

        # enroll vs autoEnroll mirrors real ADCS's two separate ACL
        # permission bits: Enroll lets a principal manually request a
        # certificate; Autoenroll is required on top of that before
        # unattended background autoenrollment will pick the template up
        # at all. UCM previously sent autoEnroll=true unconditionally,
        # meaning every active template got offered to every
        # Kerberos-authenticated principal at logon, not just the ones an
        # admin actually meant for unattended enrollment.
        permission = etree.SubElement(attributes, '{%s}permission' % XCEP_NS)
        etree.SubElement(permission, '{%s}enroll' % XCEP_NS).text = 'true'
        etree.SubElement(permission, '{%s}autoEnroll' % XCEP_NS).text = (
            'true' if getattr(template, 'autoenroll_enabled', False) else 'false'
        )

        # privateKeyAttributes' sequence: minimalKeyLength, keySpec,
        # keyUsageProperty, permissions, algorithmOIDReference,
        # cryptoProviders. keyUsageProperty/permissions/algorithmOIDReference
        # are required-but-nillable (see _nil_element's docstring), so they
        # must appear even when nil. keySpec and cryptoProviders are
        # populated (not nil) per the real-ADCS trace referenced in the
        # module docstring; algorithmOIDReference stays nil (same trace).
        is_ecdsa = algo_name.startswith('ECDSA')
        pk_attrs = etree.SubElement(attributes, '{%s}privateKeyAttributes' % XCEP_NS)
        etree.SubElement(pk_attrs, '{%s}minimalKeyLength' % XCEP_NS).text = str(min_key_length)
        if is_ecdsa:
            _nil_element(pk_attrs, 'keySpec')
        else:
            etree.SubElement(pk_attrs, '{%s}keySpec' % XCEP_NS).text = _RSA_KEY_SPEC
        _nil_element(pk_attrs, 'keyUsageProperty')
        _nil_element(pk_attrs, 'permissions')
        _nil_element(pk_attrs, 'algorithmOIDReference')
        crypto_providers = etree.SubElement(pk_attrs, '{%s}cryptoProviders' % XCEP_NS)
        provider_names = _ECDSA_CRYPTO_PROVIDERS if is_ecdsa else _RSA_CRYPTO_PROVIDERS
        for provider_name in provider_names:
            etree.SubElement(crypto_providers, '{%s}provider' % XCEP_NS).text = provider_name

        # attributes' sequence: commonName, policySchema, certificateValidity,
        # permission, privateKeyAttributes, revision, supersededPolicies,
        # privateKeyFlags, subjectNameFlags, enrollmentFlags, generalFlags,
        # hashAlgorithmOIDReference, rARequirements, keyArchivalAttributes,
        # extensions -- order matters (xs:sequence) and the nillable-but-
        # required tail elements must all be present, real value or nil.
        revision = etree.SubElement(attributes, '{%s}revision' % XCEP_NS)
        etree.SubElement(revision, '{%s}majorRevision' % XCEP_NS).text = '1'
        etree.SubElement(revision, '{%s}minorRevision' % XCEP_NS).text = '0'

        _nil_element(attributes, 'supersededPolicies')
        _nil_element(attributes, 'privateKeyFlags')
        is_machine_template = template.template_type in _MACHINE_TEMPLATE_TYPES
        if is_machine_template:
            subject_name_flags = _MACHINE_SUBJECT_NAME_FLAGS
        elif getattr(template, 'ad_derived_subject', False):
            subject_name_flags = _USER_AD_DERIVED_SUBJECT_NAME_FLAGS
        else:
            subject_name_flags = _SUBJECT_NAME_FLAGS
        etree.SubElement(attributes, '{%s}subjectNameFlags' % XCEP_NS).text = str(subject_name_flags)
        etree.SubElement(attributes, '{%s}enrollmentFlags' % XCEP_NS).text = str(_ENROLLMENT_FLAGS)
        if is_machine_template:
            etree.SubElement(attributes, '{%s}generalFlags' % XCEP_NS).text = str(_GENERAL_MACHINE_TYPE)
        else:
            _nil_element(attributes, 'generalFlags')
        _nil_element(attributes, 'hashAlgorithmOIDReference')
        _nil_element(attributes, 'rARequirements')
        _nil_element(attributes, 'keyArchivalAttributes')

        _build_extensions_element(attributes, extensions, oids)

    # GetPoliciesResponse's own sequence is response, cAs, oIDs (in that
    # order) -- an xs:sequence violation here produces WS_E_INVALID_FORMAT
    # on a real client even though every individual element is well-formed.
    cas_section = etree.SubElement(response_root, '{%s}cAs' % XCEP_NS)
    ca_el = etree.SubElement(cas_section, '{%s}cA' % XCEP_NS)

    uris_el = etree.SubElement(ca_el, '{%s}uris' % XCEP_NS)
    for client_authentication, uri, renewal_only in enrollment_uris:
        cauri_el = etree.SubElement(uris_el, '{%s}cAURI' % XCEP_NS)
        etree.SubElement(cauri_el, '{%s}clientAuthentication' % XCEP_NS).text = str(client_authentication)
        etree.SubElement(cauri_el, '{%s}uri' % XCEP_NS).text = uri
        etree.SubElement(cauri_el, '{%s}priority' % XCEP_NS).text = '1'
        etree.SubElement(cauri_el, '{%s}renewalOnly' % XCEP_NS).text = (
            'true' if renewal_only else 'false'
        )

    # certificate is required (not nillable) per the CA complex type, so
    # it must be present even in the (should-never-happen) case where the
    # configured CA's own cert fails to parse -- empty content rather
    # than omitting the element outright, to keep the sequence valid.
    cert_der_b64 = _cert_pem_to_der_b64(ca.crt) if ca.crt else None
    etree.SubElement(ca_el, '{%s}certificate' % XCEP_NS).text = cert_der_b64 or ''
    etree.SubElement(ca_el, '{%s}enrollPermission' % XCEP_NS).text = 'true'
    etree.SubElement(ca_el, '{%s}cAReferenceID' % XCEP_NS).text = str(ca_ref_id)

    # oIDs comes after cAs in GetPoliciesResponse's sequence (see note
    # above) -- built last since the oIDs table is only fully populated
    # once every policy in the loop above has registered its references.
    oids_el = etree.SubElement(response_root, '{%s}oIDs' % XCEP_NS)
    for oid_value, meta in oids.entries():
        oid_el = etree.SubElement(oids_el, '{%s}oID' % XCEP_NS)
        etree.SubElement(oid_el, '{%s}value' % XCEP_NS).text = oid_value
        etree.SubElement(oid_el, '{%s}group' % XCEP_NS).text = str(meta['group'])
        etree.SubElement(oid_el, '{%s}oIDReferenceID' % XCEP_NS).text = str(meta['id'])
        etree.SubElement(oid_el, '{%s}defaultName' % XCEP_NS).text = meta['default_name']

    return build_envelope(response_root, action=ACTION_GET_POLICIES_RESPONSE, relates_to=message_id)


def _cert_pem_to_der_b64(ca_crt):
    """``CA.crt`` -> base64 DER for the ``cAs/cA/certificate`` element.

    ``CA.crt`` is stored base64-encoded PEM in the database (confirmed via
    ``models/ca.py``'s own ``base64.b64decode(self.crt)`` calls), not raw
    PEM text. Getting this wrong produces an empty ``<certificate>``
    element, which real Windows clients reject as CERTSRV_E_PROPERTY_EMPTY
    ("The requested property value is empty") since the element isn't
    nillable.

    Returns None rather than raising: a malformed CA cert should not take
    down policy discovery for every other template.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding
        cert_pem = base64.b64decode(ca_crt).decode('utf-8')
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        return base64.b64encode(cert.public_bytes(Encoding.DER)).decode('ascii')
    except Exception:
        return None
