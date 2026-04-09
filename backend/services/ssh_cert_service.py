"""
SSH Certificate Service

Signs SSH certificates using the cryptography library's SSHCertificateBuilder.
Handles user and host certificates, revocation, and export.
"""

import base64
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import ssh as ssh_serialization

from models import db
from models.ssh import SSHCertificateAuthority, SSHCertificate
from services.ssh_ca_service import SSHCAService
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# Standard user certificate extensions
USER_EXTENSIONS = {
    'permit-pty': b'',
    'permit-user-rc': b'',
    'permit-agent-forwarding': b'',
    'permit-port-forwarding': b'',
    'permit-X11-forwarding': b'',
}


class SSHCertificateService:
    """Service for issuing, revoking, and managing SSH certificates"""

    @staticmethod
    def _parse_public_key(pub_key_data):
        """Parse an SSH public key from OpenSSH format string.

        Accepts "ssh-ed25519 AAAA..." or just the base64 blob.

        Returns:
            Public key object
        """
        if isinstance(pub_key_data, str):
            pub_key_data = pub_key_data.strip().encode('utf-8')

        try:
            return ssh_serialization.load_ssh_public_identity(pub_key_data)
        except Exception:
            pass

        # Try wrapping with a type prefix
        for prefix in [b'ssh-ed25519', b'ssh-rsa', b'ecdsa-sha2-nistp256',
                       b'ecdsa-sha2-nistp384', b'ecdsa-sha2-nistp521']:
            try:
                full = prefix + b' ' + pub_key_data
                return ssh_serialization.load_ssh_public_identity(full)
            except Exception:
                continue

        raise ValueError("Invalid SSH public key format")

    @staticmethod
    def _compute_fingerprint(public_key):
        """Compute SHA256 fingerprint of an SSH public key."""
        pub_bytes = ssh_serialization.serialize_ssh_public_key(public_key)
        parts = pub_bytes.split(b' ')
        key_data = base64.b64decode(parts[1])
        digest = hashlib.sha256(key_data).digest()
        return "SHA256:" + base64.b64encode(digest).decode('utf-8').rstrip('=')

    @staticmethod
    def _detect_key_type(public_key):
        """Detect key type from a public key object."""
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
        if isinstance(public_key, ed25519.Ed25519PublicKey):
            return 'ed25519'
        elif isinstance(public_key, rsa.RSAPublicKey):
            return 'rsa'
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            curve = public_key.curve
            if isinstance(curve, ec.SECP256R1):
                return 'ecdsa-p256'
            elif isinstance(curve, ec.SECP384R1):
                return 'ecdsa-p384'
            elif isinstance(curve, ec.SECP521R1):
                return 'ecdsa-p521'
        return 'unknown'

    @staticmethod
    def sign_certificate(ca_id, public_key_data, cert_type, principals,
                         validity_seconds=None, key_id=None,
                         extensions=None, critical_options=None,
                         descr=None, source='web', username=None,
                         owner_group_id=None):
        """Sign a public key and issue an SSH certificate.

        Args:
            ca_id: SSH CA ID to sign with
            public_key_data: Subject's public key (OpenSSH format string)
            cert_type: 'user' or 'host'
            principals: List of principal strings (usernames or hostnames)
            validity_seconds: How long the cert is valid (default: CA's default_ttl)
            key_id: Certificate identifier (default: auto-generated from principals)
            extensions: Dict of extensions {name: value} (default: CA defaults for user certs)
            critical_options: Dict of critical options {name: value}
            descr: Human-readable description
            source: 'web', 'api', or 'auto'
            username: Who issued the cert
            owner_group_id: Optional group ownership

        Returns:
            SSHCertificate instance
        """
        # Validate CA
        ca = SSHCertificateAuthority.query.get(ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")

        if cert_type not in SSHCertificate.VALID_CERT_TYPES:
            raise ValueError(f"Invalid certificate type: {cert_type}")

        # Validate principals
        if not principals or not isinstance(principals, list):
            raise ValueError("At least one principal is required")

        principals = [p.strip() for p in principals if p and p.strip()]
        if not principals:
            raise ValueError("At least one non-empty principal is required")

        # Check allowed principals if configured on the CA
        allowed = ca.get_allowed_principals()
        if allowed:
            for p in principals:
                if p not in allowed:
                    raise ValueError(
                        f"Principal '{p}' is not in the CA's allowed principals list"
                    )

        # Parse the subject's public key
        public_key = SSHCertificateService._parse_public_key(public_key_data)
        subject_key_type = SSHCertificateService._detect_key_type(public_key)
        subject_fingerprint = SSHCertificateService._compute_fingerprint(public_key)

        # Determine validity
        if validity_seconds is None:
            validity_seconds = ca.default_ttl or 86400

        # Enforce max TTL
        if ca.max_ttl and ca.max_ttl > 0:
            if validity_seconds > ca.max_ttl:
                validity_seconds = ca.max_ttl

        now_ts = int(time.time())
        valid_after = now_ts
        valid_before = now_ts + validity_seconds

        # Get next serial
        serial = SSHCAService.get_next_serial(ca_id)

        # Auto-generate key_id if not provided
        if not key_id:
            key_id = f"{','.join(principals)}@{ca.descr}"

        # Build the certificate
        ca_private_key = SSHCAService.get_private_key_object(ca_id)

        ssh_cert_type = (ssh_serialization.SSHCertificateType.USER
                         if cert_type == 'user'
                         else ssh_serialization.SSHCertificateType.HOST)

        builder = (ssh_serialization.SSHCertificateBuilder()
                   .public_key(public_key)
                   .serial(serial)
                   .type(ssh_cert_type)
                   .key_id(key_id.encode('utf-8'))
                   .valid_principals([p.encode('utf-8') for p in principals])
                   .valid_after(valid_after)
                   .valid_before(valid_before))

        # Add extensions (user certs only)
        if cert_type == 'user':
            if extensions is not None:
                # Handle both list and dict formats
                if isinstance(extensions, list):
                    ext_dict = {e: '' for e in extensions}
                else:
                    ext_dict = extensions
            else:
                ext_dict = {e: '' for e in ca.get_default_extensions()}
            for ext_name, ext_value in sorted(ext_dict.items()):
                val = ext_value if isinstance(ext_value, str) else ''
                builder = builder.add_extension(
                    ext_name.encode('utf-8'),
                    val.encode('utf-8')
                )

        # Add critical options
        if critical_options:
            for opt_name, opt_value in sorted(critical_options.items()):
                val = opt_value if isinstance(opt_value, str) else ''
                builder = builder.add_critical_option(
                    opt_name.encode('utf-8'),
                    val.encode('utf-8')
                )

        # Sign
        cert = builder.sign(ca_private_key)
        cert_bytes = cert.public_bytes().decode('utf-8')

        # Store public key in OpenSSH format
        pub_openssh = ssh_serialization.serialize_ssh_public_key(public_key).decode('utf-8')

        # Convert timestamps to datetime for DB storage
        valid_from_dt = datetime.fromtimestamp(valid_after, tz=timezone.utc)
        valid_to_dt = datetime.fromtimestamp(valid_before, tz=timezone.utc)

        # Build description if not provided
        if not descr:
            descr = f"{cert_type.capitalize()} cert for {', '.join(principals)}"

        # Store extensions and critical options as JSON
        if extensions is not None:
            if isinstance(extensions, list):
                stored_extensions = {e: '' for e in extensions}
            else:
                stored_extensions = extensions
        elif cert_type == 'user':
            stored_extensions = {e: '' for e in ca.get_default_extensions()}
        else:
            stored_extensions = {}

        ssh_cert = SSHCertificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            ssh_ca_id=ca_id,
            cert_type=cert_type,
            key_id=key_id,
            public_key=pub_openssh,
            certificate=cert_bytes,
            principals=json.dumps(principals),
            serial=serial,
            valid_from=valid_from_dt,
            valid_to=valid_to_dt,
            key_type=subject_key_type,
            fingerprint=subject_fingerprint,
            extensions=json.dumps(stored_extensions) if stored_extensions else None,
            critical_options=json.dumps(critical_options) if critical_options else None,
            source=source,
            created_by=username,
            owner_group_id=owner_group_id,
        )

        try:
            db.session.add(ssh_cert)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to store SSH certificate: {e}")
            raise

        logger.info(f"Issued SSH {cert_type} certificate #{serial} for "
                     f"{', '.join(principals)} (CA: {ca.descr})")
        return ssh_cert

    @staticmethod
    def generate_and_sign(ca_id, cert_type, principals, key_type='ed25519',
                          validity_seconds=None, key_id=None,
                          extensions=None, critical_options=None,
                          descr=None, source='web', username=None,
                          owner_group_id=None):
        """Generate a new key pair AND sign it — returns cert + private key.

        Used when the client doesn't have a key pair yet.

        Returns:
            dict with 'certificate': SSHCertificate, 'private_key': str (PEM)
        """
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat,
        )

        private_key = SSHCAService._generate_key(key_type)
        public_key = private_key.public_key()
        pub_openssh = ssh_serialization.serialize_ssh_public_key(public_key).decode('utf-8')

        # Sign the public key
        ssh_cert = SSHCertificateService.sign_certificate(
            ca_id=ca_id,
            public_key_data=pub_openssh,
            cert_type=cert_type,
            principals=principals,
            validity_seconds=validity_seconds,
            key_id=key_id,
            extensions=extensions,
            critical_options=critical_options,
            descr=descr,
            source=source,
            username=username,
            owner_group_id=owner_group_id,
        )

        # Serialize private key
        prv_pem = private_key.private_bytes(
            Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()
        ).decode('utf-8')

        return {
            'certificate': ssh_cert,
            'private_key': prv_pem,
        }

    @staticmethod
    def revoke_certificate(cert_id, reason='unspecified', username=None):
        """Revoke an SSH certificate."""
        cert = SSHCertificate.query.get(cert_id)
        if not cert:
            raise ValueError(f"SSH certificate not found: {cert_id}")

        if cert.revoked:
            raise ValueError("Certificate is already revoked")

        cert.revoked = True
        cert.revoked_at = utc_now()
        cert.revoke_reason = reason

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to revoke SSH certificate {cert_id}: {e}")
            raise

        logger.info(f"Revoked SSH certificate #{cert.serial} ({cert.key_id}): {reason}")
        return cert

    @staticmethod
    def delete_certificate(cert_id):
        """Delete an SSH certificate record."""
        cert = SSHCertificate.query.get(cert_id)
        if not cert:
            raise ValueError(f"SSH certificate not found: {cert_id}")

        cert_name = cert.key_id
        try:
            db.session.delete(cert)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete SSH certificate {cert_id}: {e}")
            raise

        logger.info(f"Deleted SSH certificate '{cert_name}'")
        return cert_name

    @staticmethod
    def decode_certificate(cert_data):
        """Decode an SSH certificate and return its fields.

        Args:
            cert_data: Certificate in OpenSSH format (string)

        Returns:
            Dict with parsed certificate fields
        """
        if isinstance(cert_data, str):
            cert_data = cert_data.strip().encode('utf-8')

        try:
            cert = ssh_serialization.load_ssh_public_identity(cert_data)
        except Exception as e:
            raise ValueError(f"Failed to parse SSH certificate: {e}")

        # Verify it's actually a certificate, not just a public key
        if not hasattr(cert, 'serial'):
            raise ValueError("The provided data is a public key, not a certificate")

        # Get cert type
        cert_type = 'user' if cert.type == ssh_serialization.SSHCertificateType.USER else 'host'

        # Get key type from the public key
        public_key = cert.public_key()
        key_type = SSHCertificateService._detect_key_type(public_key)
        fingerprint = SSHCertificateService._compute_fingerprint(public_key)

        # Get CA fingerprint
        ca_key = cert.signature_key()
        ca_fingerprint = SSHCertificateService._compute_fingerprint(ca_key)

        # Decode extensions and critical options
        extensions = {k.decode('utf-8'): v.decode('utf-8')
                      for k, v in cert.extensions.items()}
        critical_options = {k.decode('utf-8'): v.decode('utf-8')
                           for k, v in cert.critical_options.items()}

        # Verify signature
        try:
            cert.verify_cert_signature()
            signature_valid = True
        except Exception:
            signature_valid = False

        return {
            'serial': cert.serial,
            'type': cert_type,
            'key_id': cert.key_id.decode('utf-8'),
            'principals': [p.decode('utf-8') for p in cert.valid_principals],
            'valid_after': cert.valid_after,
            'valid_before': cert.valid_before,
            'valid_from': datetime.fromtimestamp(cert.valid_after, tz=timezone.utc).isoformat(),
            'valid_to': datetime.fromtimestamp(cert.valid_before, tz=timezone.utc).isoformat(),
            'key_type': key_type,
            'fingerprint': fingerprint,
            'ca_fingerprint': ca_fingerprint,
            'extensions': extensions,
            'critical_options': critical_options,
            'signature_valid': signature_valid,
            'nonce': cert.nonce.hex(),
        }

    @staticmethod
    def export_certificate(cert_id):
        """Export an SSH certificate in OpenSSH format.

        Returns:
            Dict with 'certificate', 'public_key', 'ca_public_key'
        """
        cert = SSHCertificate.query.get(cert_id)
        if not cert:
            raise ValueError(f"SSH certificate not found: {cert_id}")

        ca = SSHCertificateAuthority.query.get(cert.ssh_ca_id)
        ca_pub = ca.public_key if ca else None

        return {
            'certificate': cert.certificate,
            'public_key': cert.public_key,
            'ca_public_key': ca_pub,
            'key_id': cert.key_id,
            'cert_type': cert.cert_type,
        }
