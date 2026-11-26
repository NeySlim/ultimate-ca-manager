"""An Ed25519 SSH signature (PROTOCOL.sshsig) made in Python, as `ssh-keygen -Y sign` makes it:
tests that need no ssh-keygen sign enrollments with it (test_sshsig checks the verifier against
ssh-keygen itself)."""
import base64
import hashlib
import struct

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import ssh as ssh_ser


def _string(data):
    return struct.pack('>I', len(data)) + data


def new_key():
    """(private key, 'ssh-ed25519 base64' public line)."""
    key = ed25519.Ed25519PrivateKey.generate()
    return key, ssh_ser.serialize_ssh_public_key(key.public_key()).decode()


def sign(private_key, message, namespace):
    """The armored signature of *message* (bytes or text) for *namespace*."""
    if isinstance(message, str):
        message = message.encode()
    public = ssh_ser.serialize_ssh_public_key(private_key.public_key()).decode()
    blob = base64.b64decode(public.split()[1])
    ns, hashalg = namespace.encode(), b'sha512'
    signed = b'SSHSIG' + _string(ns) + _string(b'') + _string(hashalg) + _string(hashlib.sha512(message).digest())
    signature = _string(b'ssh-ed25519') + _string(private_key.sign(signed))
    body = (b'SSHSIG' + struct.pack('>I', 1) + _string(blob) + _string(ns) + _string(b'') + _string(hashalg)
            + _string(signature))
    text = base64.b64encode(body).decode()
    lines = [text[i:i + 70] for i in range(0, len(text), 70)]
    return '-----BEGIN SSH SIGNATURE-----\n' + '\n'.join(lines) + '\n-----END SSH SIGNATURE-----\n'
