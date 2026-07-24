"""
MS-XCEP policy response construction (GetPoliciesResponse).

Builds the SOAP/XML body Windows clients (MMC "Request New Certificate",
certreq, GPO autoenrollment) expect from a Certificate Enrollment Policy
Web Service's ``GetPolicies`` operation. Pure XML construction: no Flask
or DB writes happen here, only reads of already-loaded ``CA`` /
``CertificateTemplate`` rows, mirroring how ``services/scep/response_builder.py``
keeps wire-format construction separate from protocol orchestration.

Phase 1 scope: a structurally sound, testable subset of the real MS-XCEP
schema (https://docs.microsoft.com/openspecs/windows_protocols/ms-xcep/).
It has not yet been validated against a real Windows client or the
published XSD end-to-end — that interop pass is Phase 3/4 work once
MS-WSTEP issuance exists to test alongside it.
"""
import base64
import json
import uuid

from lxml import etree

XCEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy'
SOAP_NS = 'http://www.w3.org/2003/05/soap-envelope'

NSMAP = {'xcep': XCEP_NS, 's': SOAP_NS}

# RFC 5280 / PKIX extended key usage OIDs for the EKU names UCM's
# CertificateTemplate.extensions_template already stores.
_EKU_OIDS = {
    'serverAuth': '1.3.6.1.5.5.7.3.1',
    'clientAuth': '1.3.6.1.5.5.7.3.2',
    'codeSigning': '1.3.6.1.5.5.7.3.3',
    'emailProtection': '1.3.6.1.5.5.7.3.4',
    'timeStamping': '1.3.6.1.5.5.7.3.8',
    'ocspSigning': '1.3.6.1.5.5.7.3.9',
    'ipsecEndSystem': '1.3.6.1.5.5.7.3.5',
    'ipsecTunnel': '1.3.6.1.5.5.7.3.6',
    'ipsecUser': '1.3.6.1.5.5.7.3.7',
    'smartcardLogon': '1.3.6.1.4.1.311.20.2.2',
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


def build_get_policies_response(ca, templates):
    """Build an MS-XCEP ``GetPoliciesResponse`` SOAP envelope.

    Args:
        ca: the configured ``CA`` row (must have ``crt``/``refid``/``descr``).
        templates: iterable of active ``CertificateTemplate`` rows to expose
            when none are pinned to ``ca`` (the pinned set wins otherwise).

    Returns:
        bytes: UTF-8 encoded, well-formed SOAP XML.
    """
    oids = _OidTable()
    resolved_templates = _resolve_templates_for_ca(ca, templates)

    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=NSMAP)
    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    response_root = etree.SubElement(body, '{%s}GetPoliciesResponse' % XCEP_NS)

    response = etree.SubElement(response_root, '{%s}response' % XCEP_NS)
    etree.SubElement(response, '{%s}policyID' % XCEP_NS).text = str(uuid.uuid4())
    etree.SubElement(response, '{%s}policyFriendlyName' % XCEP_NS).text = (
        f'Ultimate CA Manager - {ca.descr or ca.refid}'
    )
    # Hint to the client how long it may cache this policy before polling
    # again. 8 hours matches the default GPO autoenrollment poll interval.
    etree.SubElement(response, '{%s}nextUpdateHours' % XCEP_NS).text = '8'
    etree.SubElement(response, '{%s}policiesNotChanged' % XCEP_NS).text = 'false'

    policies = etree.SubElement(response, '{%s}policies' % XCEP_NS)

    for template in resolved_templates:
        extensions = {}
        if template.extensions_template:
            try:
                extensions = json.loads(template.extensions_template)
            except (TypeError, ValueError):
                extensions = {}

        algo_oid, algo_name, min_key_length = _key_type_info(template.key_type)
        algo_ref = oids.ref(algo_oid, group='publicKeyAlgorithm', default_name=algo_name)

        policy = etree.SubElement(policies, '{%s}policy' % XCEP_NS)
        etree.SubElement(policy, '{%s}policyOIDReference' % XCEP_NS).text = str(algo_ref)
        cas_el = etree.SubElement(policy, '{%s}cAs' % XCEP_NS)
        etree.SubElement(cas_el, '{%s}cAReference' % XCEP_NS).text = ca.refid

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

        permission = etree.SubElement(attributes, '{%s}permission' % XCEP_NS)
        etree.SubElement(permission, '{%s}enroll' % XCEP_NS).text = 'true'
        etree.SubElement(permission, '{%s}autoEnroll' % XCEP_NS).text = 'true'

        pk_attrs = etree.SubElement(attributes, '{%s}privateKeyAttributes' % XCEP_NS)
        etree.SubElement(pk_attrs, '{%s}minimalKeyLength' % XCEP_NS).text = str(min_key_length)
        etree.SubElement(pk_attrs, '{%s}algorithmOIDReference' % XCEP_NS).text = str(algo_ref)

        eku_list = extensions.get('extended_key_usage') or []
        if eku_list:
            eku_refs = etree.SubElement(attributes, '{%s}enrollmentCriteria' % XCEP_NS)
            for eku_name in eku_list:
                eku_oid = _EKU_OIDS.get(eku_name)
                if not eku_oid:
                    continue
                eku_ref = oids.ref(eku_oid, group='enhancedKeyUsage', default_name=eku_name)
                etree.SubElement(eku_refs, '{%s}extendedKeyUsageOIDReference' % XCEP_NS).text = str(eku_ref)

        revision = etree.SubElement(attributes, '{%s}revision' % XCEP_NS)
        etree.SubElement(revision, '{%s}majorRevision' % XCEP_NS).text = '1'
        etree.SubElement(revision, '{%s}minorRevision' % XCEP_NS).text = '0'

    oids_el = etree.SubElement(response_root, '{%s}oIDs' % XCEP_NS)
    for oid_value, meta in oids.entries():
        oid_el = etree.SubElement(oids_el, '{%s}oID' % XCEP_NS)
        etree.SubElement(oid_el, '{%s}value' % XCEP_NS).text = oid_value
        etree.SubElement(oid_el, '{%s}group' % XCEP_NS).text = meta['group']
        etree.SubElement(oid_el, '{%s}oIDReferenceID' % XCEP_NS).text = str(meta['id'])
        etree.SubElement(oid_el, '{%s}defaultName' % XCEP_NS).text = meta['default_name']

    cas_section = etree.SubElement(response_root, '{%s}cAs' % XCEP_NS)
    ca_el = etree.SubElement(cas_section, '{%s}CAReference' % XCEP_NS)
    etree.SubElement(ca_el, '{%s}authority' % XCEP_NS).text = ca.refid
    if ca.crt:
        cert_der_b64 = _cert_pem_to_der_b64(ca.crt)
        if cert_der_b64:
            etree.SubElement(ca_el, '{%s}certificate' % XCEP_NS).text = cert_der_b64

    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def _cert_pem_to_der_b64(pem_text):
    """Best-effort PEM -> base64 DER for the ``cAs/CAReference/certificate``
    element. Returns None rather than raising: a malformed CA cert should
    not take down policy discovery for every other template."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding
        cert = x509.load_pem_x509_certificate(
            pem_text.encode() if isinstance(pem_text, str) else pem_text
        )
        return base64.b64encode(cert.public_bytes(Encoding.DER)).decode('ascii')
    except Exception:
        return None
