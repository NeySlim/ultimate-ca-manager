"""
SSH Certificate Authority Service

Manages SSH CA key pairs, certificate signing, and serial tracking.
Uses the `cryptography` library's native SSH certificate support (v46+).
"""

import base64
import hashlib
import json
import logging
import time
import uuid

from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)
from cryptography.hazmat.primitives.serialization import ssh as ssh_serialization

from models import db
from models.ssh import SSHCertificateAuthority
from utils.datetime_utils import utc_now

# Import key encryption (optional — fallback if not available)
try:
    from security.encryption import decrypt_private_key, encrypt_private_key
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False
    def decrypt_private_key(data):
        return data
    def encrypt_private_key(data):
        return data

logger = logging.getLogger(__name__)

# Mapping of key type names to generation parameters
KEY_TYPE_MAP = {
    'ed25519': ('ed25519', None),
    'rsa': ('rsa', 4096),
    'ecdsa-p256': ('ec', ec.SECP256R1()),
    'ecdsa-p384': ('ec', ec.SECP384R1()),
    'ecdsa-p521': ('ec', ec.SECP521R1()),
}

# Default TTLs (seconds)
DEFAULT_USER_TTL = 86400       # 24 hours
DEFAULT_HOST_TTL = 31536000    # 365 days


class SSHCAService:
    """Service for managing SSH Certificate Authorities"""

    @staticmethod
    def _generate_key(key_type):
        """Generate a private key of the given type.

        Returns:
            Private key object
        """
        if key_type not in KEY_TYPE_MAP:
            raise ValueError(f"Unsupported key type: {key_type}. "
                             f"Valid types: {', '.join(KEY_TYPE_MAP.keys())}")

        algo, param = KEY_TYPE_MAP[key_type]
        if algo == 'ed25519':
            return ed25519.Ed25519PrivateKey.generate()
        elif algo == 'rsa':
            return rsa.generate_private_key(public_exponent=65537, key_size=param)
        elif algo == 'ec':
            return ec.generate_private_key(param)

        raise ValueError(f"Unknown algorithm: {algo}")

    @staticmethod
    def _compute_fingerprint(public_key):
        """Compute SHA256 fingerprint of an SSH public key.

        Returns:
            String in format "SHA256:base64_encoded"
        """
        pub_bytes = ssh_serialization.serialize_ssh_public_key(public_key)
        # pub_bytes is "ssh-ed25519 AAAA..." — extract raw key data
        parts = pub_bytes.split(b' ')
        key_data = base64.b64decode(parts[1])
        digest = hashlib.sha256(key_data).digest()
        return "SHA256:" + base64.b64encode(digest).decode('utf-8').rstrip('=')

    @staticmethod
    def _serialize_private_key(private_key):
        """Serialize private key to OpenSSH PEM format, base64-encode,
        and optionally encrypt."""
        pem = private_key.private_bytes(
            Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()
        )
        encoded = base64.b64encode(pem).decode('utf-8')
        return encrypt_private_key(encoded)

    @staticmethod
    def _load_private_key(stored_key):
        """Load a private key from stored (base64 + optionally encrypted) form."""
        decrypted = decrypt_private_key(stored_key)
        pem = base64.b64decode(decrypted)
        from cryptography.hazmat.primitives.serialization import load_ssh_private_key
        return load_ssh_private_key(pem, password=None)

    @staticmethod
    def _detect_key_type(private_key):
        """Detect the key type string from a private key object."""
        if isinstance(private_key, ed25519.Ed25519PrivateKey):
            return 'ed25519'
        elif isinstance(private_key, rsa.RSAPrivateKey):
            return 'rsa'
        elif isinstance(private_key, ec.EllipticCurvePrivateKey):
            curve = private_key.curve
            if isinstance(curve, ec.SECP256R1):
                return 'ecdsa-p256'
            elif isinstance(curve, ec.SECP384R1):
                return 'ecdsa-p384'
            elif isinstance(curve, ec.SECP521R1):
                return 'ecdsa-p521'
        return 'unknown'

    @staticmethod
    def create_ca(descr, ca_type, key_type='ed25519', username=None,
                  default_ttl=None, max_ttl=0, default_extensions=None,
                  allowed_principals=None, comment=None, owner_group_id=None):
        """Create a new SSH Certificate Authority.

        Args:
            descr: Human-readable description
            ca_type: 'user' or 'host'
            key_type: Key algorithm (ed25519, rsa, ecdsa-p256/p384/p521)
            username: Who created it
            default_ttl: Default certificate validity in seconds
            max_ttl: Maximum allowed TTL (0 = unlimited)
            default_extensions: List of default extensions for user certs
            allowed_principals: List of allowed principal patterns
            comment: Optional notes
            owner_group_id: Optional group ownership

        Returns:
            SSHCertificateAuthority instance
        """
        if ca_type not in SSHCertificateAuthority.VALID_CA_TYPES:
            raise ValueError(f"Invalid CA type: {ca_type}. Must be 'user' or 'host'.")

        if key_type not in KEY_TYPE_MAP:
            raise ValueError(f"Invalid key type: {key_type}. "
                             f"Valid: {', '.join(KEY_TYPE_MAP.keys())}")

        # Generate key pair
        private_key = SSHCAService._generate_key(key_type)
        public_key = private_key.public_key()

        # Serialize
        pub_openssh = ssh_serialization.serialize_ssh_public_key(public_key).decode('utf-8')
        prv_stored = SSHCAService._serialize_private_key(private_key)
        fingerprint = SSHCAService._compute_fingerprint(public_key)

        # Set default TTL based on type
        if default_ttl is None:
            default_ttl = DEFAULT_USER_TTL if ca_type == 'user' else DEFAULT_HOST_TTL

        # Default extensions for user CAs
        if default_extensions is None and ca_type == 'user':
            default_extensions = list(SSHCertificateAuthority.STANDARD_EXTENSIONS)

        ca = SSHCertificateAuthority(
            refid=str(uuid.uuid4()),
            descr=descr,
            ca_type=ca_type,
            public_key=pub_openssh,
            private_key=prv_stored,
            key_type=key_type,
            fingerprint=fingerprint,
            serial_counter=0,
            default_ttl=default_ttl,
            max_ttl=max_ttl,
            comment=comment,
            created_by=username,
            owner_group_id=owner_group_id,
        )
        ca.set_default_extensions(default_extensions)
        ca.set_allowed_principals(allowed_principals)

        try:
            db.session.add(ca)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create SSH CA: {e}")
            raise

        logger.info(f"Created SSH CA '{descr}' ({ca_type}, {key_type}, {fingerprint})")
        return ca

    @staticmethod
    def import_ca(descr, ca_type, private_key_pem, username=None,
                  default_ttl=None, max_ttl=0, comment=None, owner_group_id=None):
        """Import an existing SSH CA from a private key.

        Args:
            descr: Human-readable description
            ca_type: 'user' or 'host'
            private_key_pem: Private key in OpenSSH PEM format (bytes or str)
            username: Who imported it
            default_ttl: Default TTL in seconds
            max_ttl: Max TTL (0 = unlimited)
            comment: Optional notes
            owner_group_id: Optional group ownership

        Returns:
            SSHCertificateAuthority instance
        """
        if ca_type not in SSHCertificateAuthority.VALID_CA_TYPES:
            raise ValueError(f"Invalid CA type: {ca_type}")

        if isinstance(private_key_pem, str):
            private_key_pem = private_key_pem.encode('utf-8')

        # Load and validate the key
        from cryptography.hazmat.primitives.serialization import load_ssh_private_key
        try:
            private_key = load_ssh_private_key(private_key_pem, password=None)
        except Exception as e:
            raise ValueError(f"Failed to load SSH private key: {e}")

        public_key = private_key.public_key()
        key_type = SSHCAService._detect_key_type(private_key)
        fingerprint = SSHCAService._compute_fingerprint(public_key)

        # Check for duplicate fingerprint
        existing = SSHCertificateAuthority.query.filter_by(fingerprint=fingerprint).first()
        if existing:
            raise ValueError(f"An SSH CA with this fingerprint already exists: {existing.descr}")

        pub_openssh = ssh_serialization.serialize_ssh_public_key(public_key).decode('utf-8')
        prv_stored = SSHCAService._serialize_private_key(private_key)

        if default_ttl is None:
            default_ttl = DEFAULT_USER_TTL if ca_type == 'user' else DEFAULT_HOST_TTL

        default_extensions = list(SSHCertificateAuthority.STANDARD_EXTENSIONS) if ca_type == 'user' else None

        ca = SSHCertificateAuthority(
            refid=str(uuid.uuid4()),
            descr=descr,
            ca_type=ca_type,
            public_key=pub_openssh,
            private_key=prv_stored,
            key_type=key_type,
            fingerprint=fingerprint,
            serial_counter=0,
            default_ttl=default_ttl,
            max_ttl=max_ttl,
            comment=comment,
            created_by=username,
            owner_group_id=owner_group_id,
        )
        ca.set_default_extensions(default_extensions)

        try:
            db.session.add(ca)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to import SSH CA: {e}")
            raise

        logger.info(f"Imported SSH CA '{descr}' ({ca_type}, {key_type}, {fingerprint})")
        return ca

    @staticmethod
    def update_ca(ca_id, **kwargs):
        """Update SSH CA metadata (description, TTL, extensions, etc.).

        Does NOT allow changing key material.
        """
        ca = SSHCertificateAuthority.query.get(ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")

        allowed_fields = {'descr', 'default_ttl', 'max_ttl', 'comment', 'owner_group_id'}
        for field, value in kwargs.items():
            if field in allowed_fields:
                setattr(ca, field, value)

        if 'default_extensions' in kwargs:
            ca.set_default_extensions(kwargs['default_extensions'])
        if 'allowed_principals' in kwargs:
            ca.set_allowed_principals(kwargs['allowed_principals'])

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update SSH CA {ca_id}: {e}")
            raise

        return ca

    @staticmethod
    def delete_ca(ca_id):
        """Delete an SSH CA.

        Blocks if certificates exist (user must delete them first).
        """
        ca = SSHCertificateAuthority.query.get(ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")

        cert_count = ca.certificates.count()
        if cert_count > 0:
            raise ValueError(
                f"Cannot delete SSH CA: {cert_count} certificate(s) were issued by it. "
                f"Delete them first."
            )

        ca_name = ca.descr
        try:
            db.session.delete(ca)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete SSH CA {ca_id}: {e}")
            raise

        logger.info(f"Deleted SSH CA '{ca_name}'")
        return ca_name

    @staticmethod
    def get_next_serial(ca_id):
        """Atomically increment and return next serial number for a CA."""
        ca = SSHCertificateAuthority.query.get(ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")

        ca.serial_counter += 1
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise

        return ca.serial_counter

    @staticmethod
    def get_public_key(ca_id):
        """Get the CA's public key in OpenSSH format.

        This is what goes in sshd_config TrustedUserCAKeys or
        /etc/ssh/ssh_known_hosts for host CAs.
        """
        ca = SSHCertificateAuthority.query.get(ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")

        return ca.public_key

    @staticmethod
    def get_private_key_object(ca_id):
        """Load and return the CA's private key object for signing.

        Internal use only — never expose the private key to API consumers.
        """
        ca = SSHCertificateAuthority.query.get(ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")

        return SSHCAService._load_private_key(ca.private_key)
