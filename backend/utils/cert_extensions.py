"""
Shared X.509 certificate extension parser.
Used by certificate detail, CA detail, and discovery detail endpoints.
"""
import base64
import hashlib
import logging

from cryptography import x509
from cryptography.x509.oid import ExtensionOID
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448, dsa

logger = logging.getLogger(__name__)

# Common EKU OID → human-readable name
EKU_NAMES = {
    '1.3.6.1.5.5.7.3.1': 'serverAuth',
    '1.3.6.1.5.5.7.3.2': 'clientAuth',
    '1.3.6.1.5.5.7.3.3': 'codeSigning',
    '1.3.6.1.5.5.7.3.4': 'emailProtection',
    '1.3.6.1.5.5.7.3.5': 'ipsecEndSystem',
    '1.3.6.1.5.5.7.3.6': 'ipsecTunnel',
    '1.3.6.1.5.5.7.3.7': 'ipsecUser',
    '1.3.6.1.5.5.7.3.8': 'timeStamping',
    '1.3.6.1.5.5.7.3.9': 'OCSPSigning',
    '1.3.6.1.5.5.8.2.2': 'iKEIntermediate',
    '1.3.6.1.5.2.3.4': 'id-pkinit-KPClientAuth',
    '1.3.6.1.5.2.3.5': 'id-pkinit-KPkdc',
    '1.3.6.1.4.1.311.10.3.1': 'msCTLSign',
    '1.3.6.1.4.1.311.10.3.3': 'msCodeSGC',
    '1.3.6.1.4.1.311.10.3.4': 'msEFS',
    '1.3.6.1.4.1.311.10.3.12': 'msDocumentSigning',
    '1.3.6.1.4.1.311.20.2.2': 'msSmartcardLogin',
    '2.16.840.1.113730.4.1': 'nsSGC',
    '1.3.6.1.4.1.311.54.1.2': 'msRemoteDesktop',
    '2.23.140.1.31': 'evSSLServer',
    # Code-signing key purposes (Authenticode / kernel-mode / macOS) — combine
    # with the base codeSigning (1.3.6.1.5.5.7.3.3) EKU as "Extra EKUs".
    '1.3.6.1.4.1.311.2.1.21': 'msIndividualCodeSigning',
    '1.3.6.1.4.1.311.2.1.22': 'msCommercialCodeSigning',
    '1.3.6.1.4.1.311.10.3.13': 'msLifetimeSigning',
    '1.3.6.1.4.1.311.61.1.1': 'msKernelModeCodeSigning',
    '1.2.840.113635.100.4.1': 'appleCodeSigning',
    '1.2.840.113635.100.4.13': 'appleDeveloperIDApplication',
}


def _load_certificate(pem_data):
    """Load an X.509 certificate from PEM or base64-encoded PEM data."""
    if not pem_data:
        return None
    try:
        if isinstance(pem_data, str):
            pem_data = pem_data.encode('utf-8')
        if not pem_data.startswith(b'-----BEGIN'):
            pem_data = base64.b64decode(pem_data)
        return x509.load_pem_x509_certificate(pem_data, default_backend())
    except Exception:
        return None


def parse_certificate_extensions(pem_data):
    """Parse X.509 extensions from PEM or base64-encoded certificate data."""
    cert = _load_certificate(pem_data)
    if not cert:
        return {}

    extensions = {}

    def _get_ext(oid):
        try:
            return cert.extensions.get_extension_for_oid(oid)
        except x509.ExtensionNotFound:
            return None

    # Basic Constraints
    ext = _get_ext(ExtensionOID.BASIC_CONSTRAINTS)
    if ext:
        bc = ext.value
        extensions['basic_constraints'] = {
            'ca': bc.ca,
            'path_length': bc.path_length,
            'critical': ext.critical
        }

    # Key Usage
    ext = _get_ext(ExtensionOID.KEY_USAGE)
    if ext:
        ku = ext.value
        usages = []
        for attr, label in [
            ('digital_signature', 'digitalSignature'),
            ('key_encipherment', 'keyEncipherment'),
            ('content_commitment', 'nonRepudiation'),
            ('data_encipherment', 'dataEncipherment'),
            ('key_agreement', 'keyAgreement'),
            ('key_cert_sign', 'keyCertSign'),
            ('crl_sign', 'cRLSign'),
        ]:
            try:
                if getattr(ku, attr):
                    usages.append(label)
            except ValueError:
                pass
        try:
            if ku.key_agreement:
                if ku.encipher_only:
                    usages.append('encipherOnly')
                if ku.decipher_only:
                    usages.append('decipherOnly')
        except ValueError:
            pass
        extensions['key_usage'] = {'usages': usages, 'critical': ext.critical}

    # Extended Key Usage
    ext = _get_ext(ExtensionOID.EXTENDED_KEY_USAGE)
    if ext:
        eku_list = []
        for oid in ext.value:
            name = EKU_NAMES.get(oid.dotted_string, oid._name)
            if name == 'Unknown OID':
                name = oid.dotted_string
            eku_list.append({'name': name, 'oid': oid.dotted_string})
        extensions['extended_key_usage'] = {'usages': eku_list, 'critical': ext.critical}

    # Subject Alternative Names
    ext = _get_ext(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    if ext:
        san_entries = _parse_san(ext.value)
        extensions['subject_alt_names'] = {'entries': san_entries, 'critical': ext.critical}

    # Subject Key Identifier
    ext = _get_ext(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
    if ext:
        extensions['subject_key_identifier'] = {
            'value': ext.value.key_identifier.hex(':').upper(),
            'critical': ext.critical
        }

    # Authority Key Identifier
    ext = _get_ext(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
    if ext:
        aki_data = {'critical': ext.critical}
        if ext.value.key_identifier:
            aki_data['key_id'] = ext.value.key_identifier.hex(':').upper()
        if ext.value.authority_cert_serial_number:
            aki_data['serial'] = format(ext.value.authority_cert_serial_number, 'X')
        extensions['authority_key_identifier'] = aki_data

    # CRL Distribution Points
    ext = _get_ext(ExtensionOID.CRL_DISTRIBUTION_POINTS)
    if ext:
        cdps = []
        for dp in ext.value:
            if dp.full_name:
                for name in dp.full_name:
                    cdps.append(str(name.value) if hasattr(name, 'value') else str(name))
        extensions['crl_distribution_points'] = {'urls': cdps, 'critical': ext.critical}

    # Authority Information Access
    ext = _get_ext(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
    if ext:
        ocsp_urls = []
        ca_issuers = []
        for desc in ext.value:
            if desc.access_method == x509.oid.AuthorityInformationAccessOID.OCSP:
                ocsp_urls.append(str(desc.access_location.value))
            elif desc.access_method == x509.oid.AuthorityInformationAccessOID.CA_ISSUERS:
                ca_issuers.append(str(desc.access_location.value))
        extensions['authority_info_access'] = {
            'ocsp': ocsp_urls,
            'ca_issuers': ca_issuers,
            'critical': ext.critical
        }

    # Certificate Policies
    ext = _get_ext(ExtensionOID.CERTIFICATE_POLICIES)
    if ext:
        policies = []
        for policy in ext.value:
            policy_data = {'oid': policy.policy_identifier.dotted_string}
            if policy.policy_identifier._name != 'Unknown OID':
                policy_data['name'] = policy.policy_identifier._name
            if policy.policy_qualifiers:
                qualifiers = []
                for q in policy.policy_qualifiers:
                    if isinstance(q, str):
                        qualifiers.append({'type': 'CPS', 'value': q})
                    elif hasattr(q, 'notice_reference') or hasattr(q, 'explicit_text'):
                        if hasattr(q, 'explicit_text') and q.explicit_text:
                            qualifiers.append({'type': 'UserNotice', 'value': q.explicit_text})
                policy_data['qualifiers'] = qualifiers
            policies.append(policy_data)
        extensions['certificate_policies'] = {'policies': policies, 'critical': ext.critical}

    # Name Constraints
    ext = _get_ext(ExtensionOID.NAME_CONSTRAINTS)
    if ext:
        nc = ext.value
        nc_data = {'critical': ext.critical}
        if nc.permitted_subtrees:
            nc_data['permitted'] = [str(s.value) if hasattr(s, 'value') else str(s) for s in nc.permitted_subtrees]
        if nc.excluded_subtrees:
            nc_data['excluded'] = [str(s.value) if hasattr(s, 'value') else str(s) for s in nc.excluded_subtrees]
        extensions['name_constraints'] = nc_data

    # Signed Certificate Timestamps (SCT) — RFC 6962
    SCT_OID = x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.4.2")
    try:
        sct_ext = cert.extensions.get_extension_for_oid(SCT_OID)
        if sct_ext:
            extensions['signed_certificate_timestamps'] = {
                'present': True,
                'critical': sct_ext.critical,
            }
    except x509.ExtensionNotFound:
        pass

    return extensions


def parse_certificate_info(pem_data):
    """Parse key info, signature algorithm, and fingerprints from PEM data.
    Returns dict with key_algorithm, key_size, signature_algorithm, fingerprints."""
    cert = _load_certificate(pem_data)
    if not cert:
        return {}

    info = {}

    # Key algorithm and size
    pub_key = cert.public_key()
    if isinstance(pub_key, rsa.RSAPublicKey):
        info['key_algorithm'] = 'RSA'
        info['key_size'] = pub_key.key_size
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        info['key_algorithm'] = 'EC'
        info['key_size'] = pub_key.key_size
        info['curve'] = pub_key.curve.name
    elif isinstance(pub_key, ed25519.Ed25519PublicKey):
        info['key_algorithm'] = 'Ed25519'
        info['key_size'] = 256
    elif isinstance(pub_key, ed448.Ed448PublicKey):
        info['key_algorithm'] = 'Ed448'
        info['key_size'] = 448
    elif isinstance(pub_key, dsa.DSAPublicKey):
        info['key_algorithm'] = 'DSA'
        info['key_size'] = pub_key.key_size
    else:
        info['key_algorithm'] = type(pub_key).__name__

    # Signature algorithm
    sig_oid = cert.signature_algorithm_oid
    sig_name = sig_oid._name
    if sig_name == 'Unknown OID':
        sig_name = sig_oid.dotted_string
    info['signature_algorithm'] = sig_name

    # Fingerprints
    der_data = cert.public_bytes(serialization.Encoding.DER)
    info['fingerprint_sha256'] = hashlib.sha256(der_data).hexdigest()
    info['fingerprint_sha1'] = hashlib.sha1(der_data).hexdigest()

    return info


def _parse_san(san_value):
    """Parse SAN extension value into typed entries."""
    entries = []
    for name in san_value:
        if isinstance(name, x509.DNSName):
            entries.append({'type': 'DNS', 'value': name.value})
        elif isinstance(name, x509.IPAddress):
            entries.append({'type': 'IP', 'value': str(name.value)})
        elif isinstance(name, x509.RFC822Name):
            entries.append({'type': 'Email', 'value': name.value})
        elif isinstance(name, x509.UniformResourceIdentifier):
            entries.append({'type': 'URI', 'value': name.value})
        elif isinstance(name, x509.DirectoryName):
            dn_parts = [f"{attr.oid._name}={attr.value}" for attr in name.value]
            entries.append({'type': 'DirName', 'value': ', '.join(dn_parts)})
        elif isinstance(name, x509.OtherName):
            oid_str = name.type_id.dotted_string
            try:
                from asn1crypto.core import UTF8String
                upn_value = UTF8String.load(name.value).native
                if oid_str == '1.3.6.1.4.1.311.20.2.3':
                    entries.append({'type': 'UPN', 'value': upn_value})
                else:
                    entries.append({'type': f'OtherName({oid_str})', 'value': upn_value})
            except Exception:
                entries.append({'type': f'OtherName({oid_str})', 'value': name.value.hex()})
        elif isinstance(name, x509.RegisteredID):
            entries.append({'type': 'RegisteredID', 'value': name.value.dotted_string})
        else:
            entries.append({'type': 'Unknown', 'value': str(name)})
    return entries
