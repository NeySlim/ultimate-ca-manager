import base64
import hashlib
import logging

from cryptography.hazmat.primitives.serialization import ssh as ssh_serialization

logger = logging.getLogger(__name__)


class SSHCertificateUtilsMixin:

    @staticmethod
    def _parse_public_key(pub_key_data):
        if isinstance(pub_key_data, str):
            pub_key_data = pub_key_data.strip().encode('utf-8')

        try:
            return ssh_serialization.load_ssh_public_identity(pub_key_data)
        except Exception:
            pass

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
        pub_bytes = ssh_serialization.serialize_ssh_public_key(public_key)
        parts = pub_bytes.split(b' ')
        key_data = base64.b64decode(parts[1])
        digest = hashlib.sha256(key_data).digest()
        return "SHA256:" + base64.b64encode(digest).decode('utf-8').rstrip('=')

    @staticmethod
    def _detect_key_type(public_key):
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
