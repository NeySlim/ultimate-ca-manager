"""
Certificate Tools API endpoints
SSL checker, decoders, converters, key matcher
"""
import os
import socket
import ipaddress
from datetime import datetime, timezone

from flask import Blueprint
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID, ExtensionOID

import logging

from utils.datetime_utils import utc_isoformat

logger = logging.getLogger(__name__)

tools_bp = Blueprint('tools', __name__, url_prefix='/api/v2/tools')


def get_extension_value(cert, oid):
    """Get extension value safely"""
    try:
        ext = cert.extensions.get_extension_for_oid(oid)
        return ext.value
    except x509.ExtensionNotFound:
        return None


def format_name(name):
    """Format X.509 Name to dict"""
    result = {}
    for attr in name:
        oid_name = attr.oid._name
        result[oid_name] = attr.value
    return result


def cert_to_dict(cert):
    """Convert certificate to detailed dict"""
    # Basic info
    result = {
        'subject': format_name(cert.subject),
        'issuer': format_name(cert.issuer),
        'serial_number': format(cert.serial_number, 'X'),
        'version': cert.version.name,
        'not_valid_before': utc_isoformat(cert.not_valid_before_utc),
        'not_valid_after': utc_isoformat(cert.not_valid_after_utc),
        'signature_algorithm': cert.signature_algorithm_oid._name,
    }

    # Validity status
    now = datetime.now(timezone.utc)
    if now < cert.not_valid_before_utc:
        result['status'] = 'not_yet_valid'
    elif now > cert.not_valid_after_utc:
        result['status'] = 'expired'
    else:
        result['status'] = 'valid'

    # Days until expiry
    days_left = (cert.not_valid_after_utc - now).days
    result['days_until_expiry'] = days_left

    # Public key info
    pub_key = cert.public_key()
    if isinstance(pub_key, rsa.RSAPublicKey):
        result['public_key'] = {
            'type': 'RSA',
            'size': pub_key.key_size,
            'exponent': pub_key.public_numbers().e
        }
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        result['public_key'] = {
            'type': 'ECDSA',
            'curve': pub_key.curve.name,
            'size': pub_key.key_size
        }
    else:
        result['public_key'] = {'type': type(pub_key).__name__}

    # Fingerprints
    result['fingerprints'] = {
        'sha1': cert.fingerprint(hashes.SHA1()).hex(':').upper(),
        'sha256': cert.fingerprint(hashes.SHA256()).hex(':').upper()
    }

    # Extensions
    result['extensions'] = {}

    # SANs
    san = get_extension_value(cert, ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    if san:
        result['extensions']['subject_alt_names'] = [str(name) for name in san]

    # Key Usage
    ku = get_extension_value(cert, ExtensionOID.KEY_USAGE)
    if ku:
        usages = []
        if ku.digital_signature: usages.append('digitalSignature')
        if ku.key_encipherment: usages.append('keyEncipherment')
        if ku.content_commitment: usages.append('nonRepudiation')
        if ku.data_encipherment: usages.append('dataEncipherment')
        if ku.key_agreement: usages.append('keyAgreement')
        if ku.key_cert_sign: usages.append('keyCertSign')
        if ku.crl_sign: usages.append('cRLSign')
        result['extensions']['key_usage'] = usages

    # Extended Key Usage
    eku = get_extension_value(cert, ExtensionOID.EXTENDED_KEY_USAGE)
    if eku:
        result['extensions']['extended_key_usage'] = [oid._name for oid in eku]

    # Basic Constraints
    bc = get_extension_value(cert, ExtensionOID.BASIC_CONSTRAINTS)
    if bc:
        result['extensions']['basic_constraints'] = {
            'ca': bc.ca,
            'path_length': bc.path_length
        }
        result['is_ca'] = bc.ca
    else:
        result['is_ca'] = False

    # Authority Key Identifier
    aki = get_extension_value(cert, ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
    if aki and aki.key_identifier:
        result['extensions']['authority_key_identifier'] = aki.key_identifier.hex(':').upper()

    # Subject Key Identifier
    ski = get_extension_value(cert, ExtensionOID.SUBJECT_KEY_IDENTIFIER)
    if ski:
        result['extensions']['subject_key_identifier'] = ski.key_identifier.hex(':').upper()

    return result


def csr_to_dict(csr):
    """Convert CSR to detailed dict"""
    result = {
        'subject': format_name(csr.subject),
        'signature_algorithm': csr.signature_algorithm_oid._name,
        'is_signature_valid': csr.is_signature_valid
    }

    # Public key info
    pub_key = csr.public_key()
    if isinstance(pub_key, rsa.RSAPublicKey):
        result['public_key'] = {
            'type': 'RSA',
            'size': pub_key.key_size,
            'exponent': pub_key.public_numbers().e
        }
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        result['public_key'] = {
            'type': 'ECDSA',
            'curve': pub_key.curve.name,
            'size': pub_key.key_size
        }
    else:
        result['public_key'] = {'type': type(pub_key).__name__}

    # Extensions from CSR attributes
    result['extensions'] = {}
    try:
        for attr in csr.attributes:
            if attr.oid == x509.oid.AttributeOID.EXTENSION_REQUEST:
                for ext in attr.value:
                    if ext.oid == ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
                        san = ext.value
                        result['extensions']['subject_alt_names'] = [str(name) for name in san]
    except Exception:
        pass

    return result


def get_public_key_bytes(obj):
    """Get public key bytes for comparison"""
    if hasattr(obj, 'public_key'):
        pub_key = obj.public_key()
    else:
        pub_key = obj
    return pub_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )


def is_safe_host(hostname):
    """
    Check if hostname is safe to connect to (SSRF protection)
    UCM is a self-hosted PKI tool — private/local network access is allowed
    since users need to check certificates on their own infrastructure.
    Only link-local and multicast addresses are blocked.
    """
    ALLOWED_DOMAINS = os.getenv('SSRF_ALLOWED_DOMAINS', '').split(',')
    if hostname in ALLOWED_DOMAINS:
        return True

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_link_local or ip.is_multicast:
            return False
        return True
    except ValueError:
        # It's a hostname - resolve it (supports both IPv4 and IPv6)
        try:
            results = socket.getaddrinfo(hostname, None)
            for family, _, _, _, sockaddr in results:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_link_local or ip.is_multicast:
                    return False
            return True
        except (socket.gaierror, ValueError):
            return False


from . import ssl_checker, decoder, key_matcher, converter  # noqa: F401, E402
