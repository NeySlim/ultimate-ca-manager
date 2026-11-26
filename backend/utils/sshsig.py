"""Verification of OpenSSH signatures (PROTOCOL.sshsig), as `ssh-keygen -Y sign` writes them.

A host proves it holds its host key by signing a challenge with it: no command runs on the
server, the signature is checked here with the key the host certificate certifies.
"""
import base64
import hashlib
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import load_ssh_public_key

MAGIC = b'SSHSIG'
BEGIN = '-----BEGIN SSH SIGNATURE-----'
END = '-----END SSH SIGNATURE-----'
MAX_ARMORED = 16384
_HASHES = {'sha256': hashlib.sha256, 'sha512': hashlib.sha512}
# The signature algorithms accepted for each key, with the hash each signs with; ssh-rsa (SHA-1) is not one
_ECDSA = {'ecdsa-sha2-nistp256': hashes.SHA256(), 'ecdsa-sha2-nistp384': hashes.SHA384(),
          'ecdsa-sha2-nistp521': hashes.SHA512()}
_RSA = {'rsa-sha2-256': hashes.SHA256(), 'rsa-sha2-512': hashes.SHA512()}


class SignatureError(ValueError):
    """The signature is malformed or does not verify."""


def _string(buf, pos):
    if pos + 4 > len(buf):
        raise SignatureError('truncated signature')
    (length,) = struct.unpack('>I', buf[pos:pos + 4])
    pos += 4
    if pos + length > len(buf):
        raise SignatureError('truncated signature')
    return buf[pos:pos + length], pos + length


def _pack(*items):
    return b''.join(struct.pack('>I', len(item)) + item for item in items)


def _mpint(buf, pos):
    raw, pos = _string(buf, pos)
    return int.from_bytes(raw, 'big', signed=True), pos


def key_blob(openssh_public_key):
    """The wire blob of an OpenSSH public key line (``type base64 [comment]``)."""
    parts = (openssh_public_key or '').split()
    if len(parts) < 2:
        raise SignatureError('invalid public key')
    try:
        return base64.b64decode(parts[1], validate=True)
    except ValueError:
        raise SignatureError('invalid public key') from None


def verify(armored, message, namespace, openssh_public_key):
    """Raise SignatureError unless *armored* is a signature of *message* (bytes) under
    *namespace*, made with the key of *openssh_public_key*."""
    if not isinstance(armored, str) or len(armored) > MAX_ARMORED:
        raise SignatureError('invalid signature')
    lines = [line.strip() for line in armored.strip().splitlines()]
    if len(lines) < 3 or lines[0] != BEGIN or lines[-1] != END:
        raise SignatureError('not an SSH signature')
    try:
        blob = base64.b64decode(''.join(lines[1:-1]), validate=True)
    except ValueError:
        raise SignatureError('not an SSH signature') from None
    if blob[:6] != MAGIC or len(blob) < 10 or struct.unpack('>I', blob[6:10])[0] != 1:
        raise SignatureError('unsupported SSH signature version')
    pos = 10
    public, pos = _string(blob, pos)
    signed_namespace, pos = _string(blob, pos)
    reserved, pos = _string(blob, pos)
    hash_name, pos = _string(blob, pos)
    signature, pos = _string(blob, pos)
    if pos != len(blob):
        raise SignatureError('trailing data in signature')
    if public != key_blob(openssh_public_key):
        raise SignatureError('signed with another key')
    if signed_namespace != namespace.encode():
        raise SignatureError('signed for another purpose')
    digest = _HASHES.get(hash_name.decode('ascii', 'replace'))
    if digest is None:
        raise SignatureError('unsupported hash algorithm')
    signed = MAGIC + _pack(signed_namespace, reserved, hash_name, digest(message).digest())

    algorithm, rest = _string(signature, 0)
    raw, end = _string(signature, rest)
    if end != len(signature):
        raise SignatureError('trailing data in signature')
    algorithm = algorithm.decode('ascii', 'replace')
    key_type = openssh_public_key.split()[0]
    key = load_ssh_public_key(f"{key_type} {openssh_public_key.split()[1]}".encode())
    try:
        if isinstance(key, ed25519.Ed25519PublicKey) and algorithm == 'ssh-ed25519':
            key.verify(raw, signed)
        elif isinstance(key, ec.EllipticCurvePublicKey) and algorithm == key_type and algorithm in _ECDSA:
            r, at = _mpint(raw, 0)
            s, at = _mpint(raw, at)
            if at != len(raw):
                raise SignatureError('invalid ECDSA signature')
            key.verify(encode_dss_signature(r, s), signed, ec.ECDSA(_ECDSA[algorithm]))
        elif isinstance(key, rsa.RSAPublicKey) and algorithm in _RSA:
            key.verify(raw, signed, padding.PKCS1v15(), _RSA[algorithm])
        else:
            raise SignatureError(f'signature algorithm {algorithm} does not fit the key')
    except InvalidSignature:
        raise SignatureError('the signature does not verify') from None
