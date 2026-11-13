"""v3 archives for tests that forge a payload: only v4 is written, v3 is still read.

The v3 header keeps the KDF profile and salt of the archive it is derived
from, so the master key, and every private key sealed under it, is unchanged.
"""
import base64
import io
import os

from services.backup import container


def v3_header(blob: bytes) -> bytes:
    """A v3 header for the archive `blob` (v3 or v4): same KDF and salt, a nonce of its own."""
    if container.format_version_of(blob) == container.FORMAT_VERSION_V3:
        return container.parse_header(blob)[1]
    metadata, _header = container.read_header(io.BytesIO(blob))
    kept = {name: metadata[name] for name in ('ucm_version', 'created_at', 'backup_type',
                                              'kdf', 'salt_b64') if name in metadata}
    kept.update(format_version=3,
                nonce_b64=base64.b64encode(os.urandom(container.NONCE_SIZE)).decode())
    return container.build_header(format_version=3, flags=metadata['flags'],
                                  kdf_id=metadata['kdf_id'], metadata=kept)


def as_v3(blob: bytes, password: str, edit=None) -> bytes:
    """The archive `blob` rewritten as v3, the way v3 was written: same payload, same key.
    ``edit(payload)`` changes the payload first, to forge what an older version wrote."""
    import gzip
    import hashlib
    import json

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from services.backup_service import BackupService

    service = BackupService()
    key, payload = service._decrypt_framed(blob, password)
    if edit is not None:
        edit(payload)
    payload.pop('checksum', None)
    payload['checksum'] = {'algorithm': 'SHA256', 'value': hashlib.sha256(
        json.dumps(payload, indent=2, sort_keys=True).encode()).hexdigest()}
    header = v3_header(blob)
    nonce = base64.b64decode(json.loads(header[10:].decode())['nonce_b64'])
    plaintext = gzip.compress(json.dumps(payload, indent=2, sort_keys=True).encode())
    return header + AESGCM(key).encrypt(nonce, plaintext, header)
