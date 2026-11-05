"""The backup container: how it is framed, and what a reader accepts.

Everything here runs on bytes an attacker may have chosen, before the archive
is authenticated, so every step is bounded first and computed second: a small
file must not be able to ask for terabytes of memory, hours of hashing or a
million nested objects.

Three container versions are read. v1 has no framing at all (a bare salt,
nonce and ciphertext). v2 frames the archive but authenticates only the magic,
so its header can be edited without breaking the tag. v3 authenticates the
whole canonical header, which is what is written today.
"""
import base64
import json
import logging
import struct
import zlib
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

MAGIC = b'UCMB'
FORMAT_VERSION_V2 = 2
FORMAT_VERSION_V3 = 3
SUPPORTED_FORMAT_VERSIONS = frozenset({FORMAT_VERSION_V2, FORMAT_VERSION_V3})

HEADER_PREFIX_SIZE = 10  # magic + version + flags + kdf id + reserved + length

FLAG_GZIP = 0x01
KNOWN_FLAGS = FLAG_GZIP

KDF_PBKDF2 = 1
KDF_ARGON2ID = 2

KEY_SIZE = 32
NONCE_SIZE = 12
GCM_TAG_SIZE = 16

# Resource ceilings. They bound what a container can ask of this process
# before anything it contains has been authenticated.
MAX_HEADER_METADATA_BYTES = 4096
# The decompressed payload may be this many times the accepted archive size.
PLAINTEXT_PER_ARCHIVE_BYTE = 4
MAX_COMPRESSION_RATIO = 100
MAX_JSON_DEPTH = 64
# Each parsed object costs a few hundred bytes of interpreter memory, so this
# is a memory ceiling, not a size one: five million objects is roughly a
# gigabyte of parsed structures, and well above the largest real archive
# (an instance exporting its audit log is the case that grows here).
MAX_JSON_CONTAINERS = 5_000_000
_INFLATE_CHUNK = 1024 * 1024

# KDF profiles this reader accepts, with the exact shapes each version emits
# and the range a neighbouring version may legitimately have used. A profile
# outside these bounds is refused without deriving anything.
KDF_PROFILES = {
    KDF_PBKDF2: {
        'type': 'pbkdf2-sha256',
        'salt_size': 32,
        'bounds': {
            'iterations': (100_000, 2_000_000),
            'hash_len': (KEY_SIZE, KEY_SIZE),
        },
        'emitted': {'iterations': 600_000, 'hash_len': KEY_SIZE},
    },
    KDF_ARGON2ID: {
        'type': 'argon2id',
        'salt_size': 16,
        'bounds': {
            'time_cost': (1, 10),
            'memory_cost': (8 * 1024, 256 * 1024),   # KiB
            'parallelism': (1, 8),
            'hash_len': (KEY_SIZE, KEY_SIZE),
        },
        'emitted': {
            'time_cost': 3, 'memory_cost': 64 * 1024,
            'parallelism': 4, 'hash_len': KEY_SIZE,
        },
    },
}


class ContainerError(ValueError):
    """The container is not one this reader accepts.

    Its message describes the framing, never the archive's contents, and is
    safe to return to the caller.
    """


def build_header(*, format_version: int, flags: int, kdf_id: int,
                 metadata: Dict[str, Any]) -> bytes:
    """Return the canonical header bytes for a container being written."""
    metadata_bytes = json.dumps(metadata, separators=(',', ':'),
                                sort_keys=True).encode()
    if len(metadata_bytes) > MAX_HEADER_METADATA_BYTES:
        raise ContainerError("Backup header metadata is too large")
    return (
        MAGIC
        + bytes([format_version, flags, kdf_id, 0])
        + struct.pack('>H', len(metadata_bytes))
        + metadata_bytes
    )


_MIB = 1024 * 1024


def max_container_bytes() -> int:
    """The largest archive read: what the restore routes accept (`BACKUP_MAX_UPLOAD_MB`)."""
    from .storage import restore_upload_limit
    return restore_upload_limit()


def max_plaintext_bytes() -> int:
    return PLAINTEXT_PER_ARCHIVE_BYTE * max_container_bytes()


def refuse_oversized(container: bytes) -> None:
    limit = max_container_bytes()
    if len(container) > limit:
        raise ContainerError(
            f"Backup file is too large to read ({len(container) / _MIB:.1f} MB, more than "
            f"the {limit / _MIB:.0f} MB BACKUP_MAX_UPLOAD_MB allows)")


def parse_header(container: bytes) -> Tuple[Dict[str, Any], bytes, bytes]:
    """Validate the framing of a v2/v3 container.

    Returns (metadata, header_bytes, ciphertext). Nothing is derived, decrypted
    or decompressed here: this only decides whether the framing is one this
    reader knows, and whether its lengths are consistent with the file.
    """
    refuse_oversized(container)
    if len(container) < HEADER_PREFIX_SIZE:
        raise ContainerError("Invalid backup file: truncated header")
    if container[:4] != MAGIC:
        raise ContainerError("Invalid backup file: bad magic bytes")

    version, flags, kdf_id, reserved = container[4], container[5], container[6], container[7]

    if version not in SUPPORTED_FORMAT_VERSIONS:
        raise ContainerError(
            f"Unsupported backup format version: {version}. This archive was "
            "written by a different version of UCM."
        )
    if flags & ~KNOWN_FLAGS:
        raise ContainerError("Invalid backup file: unknown container flags")
    if kdf_id not in KDF_PROFILES:
        raise ContainerError(f"Unknown KDF id: {kdf_id}")
    if reserved != 0:
        raise ContainerError("Invalid backup file: reserved byte is set")

    metadata_len = struct.unpack('>H', container[8:HEADER_PREFIX_SIZE])[0]
    if metadata_len == 0:
        raise ContainerError("Invalid backup file: empty header metadata")
    if version == FORMAT_VERSION_V3 and metadata_len > MAX_HEADER_METADATA_BYTES:
        raise ContainerError("Invalid backup file: header metadata is too large")

    header_end = HEADER_PREFIX_SIZE + metadata_len
    # The ciphertext must have room for at least the GCM tag.
    if len(container) < header_end + GCM_TAG_SIZE:
        raise ContainerError("Invalid backup file: truncated")

    # The header's own JSON is parsed with the same bounds as the payload:
    # a v2 header may be 64 KiB, and json.loads recurses, so nested brackets
    # in a header reached the interpreter's recursion limit before any of
    # this was authenticated.
    try:
        metadata = json_loads_bounded(container[HEADER_PREFIX_SIZE:header_end])
    except ContainerError:
        raise ContainerError("Invalid backup metadata")
    if not isinstance(metadata, dict):
        raise ContainerError("Invalid backup metadata")

    # B: the version the header announces in JSON must be the one in its
    # framing byte; a reader that trusts one and reports the other lets an
    # archive describe itself as something it is not.
    announced = metadata.get('format_version')
    if announced is not None and announced != version:
        raise ContainerError(
            f"Invalid backup file: header announces format version {announced} "
            f"but the container says {version}"
        )

    for name, framed in (('flags', flags), ('kdf_id', kdf_id)):
        announced = metadata.get(name)
        if announced is not None and announced != framed:
            raise ContainerError(
                f"Invalid backup file: header announces {name} {announced} but "
                f"the container says {framed}"
            )

    metadata['format_version'] = version
    metadata['flags'] = flags
    metadata['kdf_id'] = kdf_id
    return metadata, container[:header_end], container[header_end:]


def validate_kdf(kdf_id: int, metadata: Dict[str, Any]) -> Tuple[bytes, bytes, Dict[str, int]]:
    """Check the KDF profile, salt and nonce before any key is derived.

    A container chooses these numbers, and both KDFs will happily spend the
    memory or the iterations they are given: an eight-hundred-byte file used
    to be able to ask for terabytes of RAM, on an unauthenticated header, in a
    request that had not proven anything yet.
    """
    profile = KDF_PROFILES.get(kdf_id)
    if profile is None:
        raise ContainerError(f"Unknown KDF id: {kdf_id}")

    params = metadata.get('kdf')
    if not isinstance(params, dict):
        raise ContainerError("Invalid backup metadata: missing KDF parameters")
    if params.get('type') != profile['type']:
        raise ContainerError(
            f"Invalid backup metadata: KDF type {params.get('type')!r} does not "
            f"match container KDF id {kdf_id}"
        )

    checked = {}
    for name, (low, high) in profile['bounds'].items():
        value = params.get(name, profile['emitted'][name])
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContainerError(f"Invalid backup metadata: {name} is not an integer")
        if not low <= value <= high:
            raise ContainerError(
                f"Refusing backup: KDF parameter {name}={value} is outside the "
                f"accepted range [{low}, {high}]"
            )
        checked[name] = value

    salt = _decode_b64(metadata.get('salt_b64'), 'salt')
    if len(salt) != profile['salt_size']:
        raise ContainerError(
            f"Refusing backup: salt is {len(salt)} bytes, expected "
            f"{profile['salt_size']}"
        )
    nonce = _decode_b64(metadata.get('nonce_b64'), 'nonce')
    if len(nonce) != NONCE_SIZE:
        raise ContainerError(
            f"Refusing backup: nonce is {len(nonce)} bytes, expected {NONCE_SIZE}"
        )
    return salt, nonce, checked


def _decode_b64(value: Any, what: str) -> bytes:
    if not isinstance(value, str):
        raise ContainerError(f"Invalid backup metadata: missing {what}")
    try:
        return base64.b64decode(value, validate=True)
    except Exception:
        raise ContainerError(f"Invalid backup metadata: {what} is not valid base64")


def decompress_bounded(plaintext: bytes) -> bytes:
    """Inflate a gzip payload with a ceiling on what it may produce.

    `gzip.decompress` materialises whatever the payload expands to, so a
    hundred-kilobyte archive that decompresses to tens of gigabytes took the
    worker down with it. This inflates in chunks and stops at the ceiling.

    Concatenated members are read as `gzip.decompress` reads them: UCM has
    only ever written one, but a reader that stopped after the first would
    return a truncated payload rather than refuse it.
    """
    ceiling = max_plaintext_bytes()
    limit = min(ceiling, max(len(plaintext), 1) * MAX_COMPRESSION_RATIO)
    chunks = []
    produced = 0
    remaining = plaintext

    while remaining:
        decompressor = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        try:
            while True:
                chunk = decompressor.decompress(remaining, _INFLATE_CHUNK)
                produced += len(chunk)
                if produced > limit:
                    raise ContainerError(
                        "Refusing backup: its compressed payload expands beyond "
                        + (f"{ceiling / _MIB:.0f} MB, {PLAINTEXT_PER_ARCHIVE_BYTE} times "
                           "BACKUP_MAX_UPLOAD_MB" if limit == ceiling
                           else "the accepted size"))
                if chunk:
                    chunks.append(chunk)
                consumed = len(remaining) - len(decompressor.unconsumed_tail)
                remaining = decompressor.unconsumed_tail
                if decompressor.eof:
                    break
                if not chunk and not consumed:
                    # Neither output nor input consumed: the member ends before
                    # its stream does, or the stream cannot progress at all.
                    raise ContainerError("Invalid backup: truncated compressed payload")
        except ContainerError:
            raise
        except zlib.error:
            raise ContainerError("Invalid backup: gzip decompression failed")

        if not decompressor.eof:
            raise ContainerError("Invalid backup: truncated compressed payload")
        remaining = decompressor.unused_data

    if not chunks and not plaintext:
        raise ContainerError("Invalid backup: empty compressed payload")
    return b''.join(chunks)


def json_loads_bounded(payload: bytes) -> Any:
    """Parse the archive's JSON after bounding its shape.

    Depth and container count are measured on the text first: the parser
    recurses, so a few kilobytes of nested brackets reach the interpreter's
    recursion limit, and a flat file of millions of objects costs far more in
    parsed objects than it does in bytes.
    """
    try:
        text = payload.decode()
    except UnicodeDecodeError:
        raise ContainerError("Invalid backup format: payload is not UTF-8")

    depth = 0
    containers = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in '{[':
            depth += 1
            containers += 1
            if depth > MAX_JSON_DEPTH:
                raise ContainerError(
                    f"Refusing backup: its JSON nests deeper than {MAX_JSON_DEPTH} levels")
            if containers > MAX_JSON_CONTAINERS:
                raise ContainerError(
                    "Refusing backup: its JSON holds more objects than this "
                    "reader accepts")
        elif char in '}]':
            depth -= 1

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ContainerError("Invalid backup format: not valid JSON")
