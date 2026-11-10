"""The backup container: how it is framed, and what a reader accepts.

Everything here runs on bytes an attacker may have chosen, before the archive
is authenticated, so every step is bounded first and computed second: a small
file must not be able to ask for terabytes of memory, hours of hashing or a
million nested objects.

Four container versions are read. v1 has no framing at all (a bare salt,
nonce and ciphertext). v2 frames the archive but authenticates only the magic,
so its header can be edited without breaking the tag. v3 authenticates the
whole canonical header. v4, written today, keeps the v3 header and follows it
with a sequence of independently authenticated chunks, read and written as a
stream (`ChunkWriter`, `ChunkReader`).
"""
import base64
import gzip
import hashlib
import json
import logging
import re
import struct
import zlib
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAGIC = b'UCMB'
FORMAT_VERSION_V2 = 2
FORMAT_VERSION_V3 = 3
FORMAT_VERSION_V4 = 4
SUPPORTED_FORMAT_VERSIONS = frozenset({FORMAT_VERSION_V2, FORMAT_VERSION_V3,
                                       FORMAT_VERSION_V4})

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
# Each parsed object costs a few hundred bytes of interpreter memory: one per
# this many bytes of accepted archive, about five million at the 512 MB default.
ARCHIVE_BYTES_PER_JSON_CONTAINER = 100
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


def max_json_containers() -> int:
    return max(1, max_container_bytes() // ARCHIVE_BYTES_PER_JSON_CONTAINER)


def count_containers(value: Any) -> int:
    """Objects and arrays in a payload, as `json_loads_bounded` counts them."""
    count, pending = 0, [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            count += 1
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            count += 1
            pending.extend(item)
    return count


def refuse_oversized(container: bytes) -> None:
    limit = max_container_bytes()
    if len(container) > limit:
        raise ContainerError(
            f"Backup file is too large to read ({len(container) / _MIB:.1f} MB, more than "
            f"the {limit / _MIB:.0f} MB BACKUP_MAX_UPLOAD_MB allows)")


def _parse_prefix(prefix: bytes) -> Tuple[int, int, int, int]:
    """Check the ten framing bytes; return (version, flags, kdf_id, metadata_len)."""
    if len(prefix) < HEADER_PREFIX_SIZE:
        raise ContainerError("Invalid backup file: truncated header")
    if prefix[:4] != MAGIC:
        raise ContainerError("Invalid backup file: bad magic bytes")

    version, flags, kdf_id, reserved = prefix[4], prefix[5], prefix[6], prefix[7]

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

    metadata_len = struct.unpack('>H', prefix[8:HEADER_PREFIX_SIZE])[0]
    if metadata_len == 0:
        raise ContainerError("Invalid backup file: empty header metadata")
    if version >= FORMAT_VERSION_V3 and metadata_len > MAX_HEADER_METADATA_BYTES:
        raise ContainerError("Invalid backup file: header metadata is too large")
    return version, flags, kdf_id, metadata_len


def _parse_metadata(raw: bytes, version: int, flags: int, kdf_id: int) -> Dict[str, Any]:
    # The header's own JSON is parsed with the same bounds as the payload:
    # a v2 header may be 64 KiB, and json.loads recurses, so nested brackets
    # in a header reached the interpreter's recursion limit before any of
    # this was authenticated.
    try:
        metadata = json_loads_bounded(raw)
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
    return metadata


def format_version_of(head: bytes) -> Optional[int]:
    """The framing version byte of a UCMB container, or None (v1, or not an archive)."""
    if len(head) >= 5 and head[:4] == MAGIC:
        return head[4]
    return None


def parse_header(container: bytes) -> Tuple[Dict[str, Any], bytes, bytes]:
    """Validate the framing of a v2/v3 container.

    Returns (metadata, header_bytes, ciphertext). Nothing is derived, decrypted
    or decompressed here: this only decides whether the framing is one this
    reader knows, and whether its lengths are consistent with the file.
    """
    refuse_oversized(container)
    version, flags, kdf_id, metadata_len = _parse_prefix(container[:HEADER_PREFIX_SIZE])
    if version == FORMAT_VERSION_V4:
        raise ContainerError("Invalid backup file: a v4 archive is read as a stream")

    header_end = HEADER_PREFIX_SIZE + metadata_len
    # The ciphertext must have room for at least the GCM tag.
    if len(container) < header_end + GCM_TAG_SIZE:
        raise ContainerError("Invalid backup file: truncated")

    metadata = _parse_metadata(container[HEADER_PREFIX_SIZE:header_end],
                               version, flags, kdf_id)
    return metadata, container[:header_end], container[header_end:]


def read_header(stream) -> Tuple[Dict[str, Any], bytes]:
    """Read and validate a v4 header from the start of `stream`: (metadata, header bytes)."""
    prefix = _read_exactly(stream, HEADER_PREFIX_SIZE)
    if prefix is None or len(prefix) < HEADER_PREFIX_SIZE:
        raise ContainerError("Invalid backup file: truncated header")
    version, flags, kdf_id, metadata_len = _parse_prefix(prefix)
    if version != FORMAT_VERSION_V4:
        raise ContainerError(
            f"Invalid backup file: format version {version} is not read as a stream")
    raw = _read_exactly(stream, metadata_len)
    if raw is None or len(raw) < metadata_len:
        raise ContainerError("Invalid backup file: truncated header")
    metadata = _parse_metadata(raw, version, flags, kdf_id)
    return metadata, prefix + raw


def _read_exactly(stream, size: int) -> Optional[bytes]:
    """Up to `size` bytes, fewer only at the end of the stream; None at its very end."""
    parts, missing = [], size
    while missing:
        part = stream.read(missing)
        if not part:
            break
        parts.append(part)
        missing -= len(part)
    if not parts and size:
        return None
    return b''.join(parts)


def validate_kdf(kdf_id: int, metadata: Dict[str, Any], *, nonce_field: str = 'nonce_b64',
                 nonce_size: int = NONCE_SIZE) -> Tuple[bytes, bytes, Dict[str, int]]:
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
    nonce = _decode_b64(metadata.get(nonce_field), 'nonce')
    if len(nonce) != nonce_size:
        raise ContainerError(
            f"Refusing backup: nonce is {len(nonce)} bytes, expected {nonce_size}"
        )
    return salt, nonce, checked


def _decode_b64(value: Any, what: str) -> bytes:
    if not isinstance(value, str):
        raise ContainerError(f"Invalid backup metadata: missing {what}")
    try:
        return base64.b64decode(value, validate=True)
    except Exception:
        raise ContainerError(f"Invalid backup metadata: {what} is not valid base64")


def decompress_bounded(plaintext: bytes, chunk_ceiling: Optional[int] = None) -> bytes:
    """Inflate a gzip payload with a ceiling on what it may produce.

    `gzip.decompress` materialises whatever the payload expands to, so a
    hundred-kilobyte archive that decompresses to tens of gigabytes took the
    worker down with it. This inflates in chunks and stops at the ceiling.

    Concatenated members are read as `gzip.decompress` reads them: UCM has
    only ever written one, but a reader that stopped after the first would
    return a truncated payload rather than refuse it.
    """
    if chunk_ceiling is not None:
        # A v4 chunk is bounded by its own announced size, not by a ratio
        ceiling = limit = chunk_ceiling
    else:
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
                    if chunk_ceiling is not None:
                        raise ContainerError(
                            "Refusing backup: a chunk expands beyond the "
                            f"{chunk_ceiling} bytes its header allows")
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


def json_loads_bounded(payload: bytes, max_containers: Optional[int] = None) -> Any:
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

    if max_containers is not None and text.count('{') + text.count('[') <= max_containers:
        # A v4 chunk whose brackets, strings included, are within its bound:
        # parsed at C speed, then its depth measured on the parsed value.
        return _loads_then_check_depth(text)

    depth = 0
    containers = 0
    limit = max_json_containers() if max_containers is None else max_containers
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
            if containers > limit:
                if max_containers is not None:
                    raise ContainerError(
                        f"Refusing backup: a chunk holds more than {limit} objects")
                raise ContainerError(
                    f"Refusing backup: its JSON holds more than {limit} objects, one per "
                    f"{ARCHIVE_BYTES_PER_JSON_CONTAINER} bytes of BACKUP_MAX_UPLOAD_MB")
        elif char in '}]':
            depth -= 1

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ContainerError("Invalid backup format: not valid JSON")


def _loads_then_check_depth(text: str) -> Any:
    try:
        value = json.loads(text)
    except RecursionError:
        raise ContainerError(
            f"Refusing backup: its JSON nests deeper than {MAX_JSON_DEPTH} levels")
    except json.JSONDecodeError:
        raise ContainerError("Invalid backup format: not valid JSON")
    pending = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        children = (item.values() if isinstance(item, dict)
                    else item if isinstance(item, list) else None)
        if children is None:
            continue
        if depth > MAX_JSON_DEPTH:
            raise ContainerError(
                f"Refusing backup: its JSON nests deeper than {MAX_JSON_DEPTH} levels")
        pending.extend((child, depth + 1) for child in children
                       if isinstance(child, (dict, list)))
    return value


# ---------------------------------------------------------------------------
# Format v4: the v3 header, then chunks `len(uint32) || AES-256-GCM(gzip(JSON))`
# ---------------------------------------------------------------------------

NONCE_BASE_SIZE = 8
CHUNK_COUNTER_LIMIT = 2 ** 32
CHUNK_MAX_DEFAULT = 8 * _MIB
CHUNK_MAX_RANGE = (64 * 1024, 64 * _MIB)
# Objects a chunk may hold: one per this many bytes of its announced size
CHUNK_BYTES_PER_CONTAINER = 32
MAX_SECTIONS = 256
_SECTION_NAME = re.compile(r'[a-z][a-z0-9_]{0,63}\Z')
_PART_KEYS = frozenset({'section', 'part', 'rows'})
_END_KEYS = frozenset({'end', 'sections', 'metadata'})


class ChunkAuthError(ContainerError):
    """A chunk failed its tag: wrong password on the first, damage on any later one."""

    def __init__(self, counter: int):
        self.counter = counter
        super().__init__(
            f"Corrupted backup: chunk {counter} does not authenticate (the archive was "
            "truncated, reordered or edited). Nothing has been changed.")


def chunk_nonce(nonce_base: bytes, counter: int) -> bytes:
    """A per-archive random prefix and the chunk's position: unique for 2^32 chunks."""
    return nonce_base + struct.pack('>I', counter)


def chunk_aad(header: bytes, counter: int, last: bool) -> bytes:
    """The whole header, the position and the end marker: a chunk is valid only there."""
    return header + struct.pack('>IB', counter, 1 if last else 0)


def chunk_ciphertext_ceiling(chunk_max: int) -> int:
    # gzip of incompressible input: stored blocks cost 5 bytes per 64 KiB, plus its framing
    return chunk_max + chunk_max // 1000 + 1024 + GCM_TAG_SIZE


def chunk_container_limit(chunk_max: int) -> int:
    return max(1, chunk_max // CHUNK_BYTES_PER_CONTAINER)


def validate_v4_metadata(metadata: Dict[str, Any]) -> Tuple[int, List[str]]:
    """The chunk size and section list a v4 header announces, bounded before use."""
    chunk_max = metadata.get('chunk_max')
    low, high = CHUNK_MAX_RANGE
    if isinstance(chunk_max, bool) or not isinstance(chunk_max, int) or not low <= chunk_max <= high:
        raise ContainerError(
            f"Refusing backup: chunk size {chunk_max!r} is outside [{low}, {high}]")
    sections = metadata.get('sections')
    if (not isinstance(sections, list) or not sections or len(sections) > MAX_SECTIONS
            or not all(isinstance(name, str) and _SECTION_NAME.match(name) for name in sections)
            or len(set(sections)) != len(sections)):
        raise ContainerError("Invalid backup metadata: the section list is not valid")
    return chunk_max, sections


class _SectionTally:
    __slots__ = ('digest', 'parts', 'rows', 'mapping')

    def __init__(self):
        self.digest = hashlib.sha256()
        self.parts = 0
        self.rows = 0
        self.mapping = False

    def record(self) -> Dict[str, Any]:
        return {'sha256': self.digest.hexdigest(), 'parts': self.parts, 'rows': self.rows}


class ChunkWriter:
    """Frames sections into authenticated chunks, in the order the header lists them.

    A section is one chunk when its JSON fits `chunk_max`, else parts of whole
    rows; the last chunk is the end record, the only one marked last.
    """

    def __init__(self, key: bytes, header: bytes, nonce_base: bytes, sections: List[str],
                 chunk_max: int = CHUNK_MAX_DEFAULT, gzip_level: int = 6):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        self._aead = AESGCM(key)
        self._header = header
        self._nonce_base = nonce_base
        self._sections = list(sections)
        self._next = 0
        self._chunk_max = chunk_max
        self._containers = chunk_container_limit(chunk_max)
        self._gzip_level = gzip_level
        self._counter = 0
        self._tallies: Dict[str, _SectionTally] = {}
        self.payload_bytes = 0

    def _frame(self, plaintext: bytes, last: bool = False) -> bytes:
        if self._counter >= CHUNK_COUNTER_LIMIT:
            raise ContainerError("Backup too large: more than 2^32 chunks")
        self.payload_bytes += len(plaintext)
        packed = gzip.compress(plaintext, compresslevel=self._gzip_level, mtime=0)
        sealed = self._aead.encrypt(chunk_nonce(self._nonce_base, self._counter), packed,
                                    chunk_aad(self._header, self._counter, last))
        self._counter += 1
        return struct.pack('>I', len(sealed)) + sealed

    def _part(self, tally: _SectionTally, body: bytes) -> bytes:
        tally.digest.update(body)
        tally.parts += 1
        return self._frame(body)

    def section(self, name: str, value: Any) -> Iterator[bytes]:
        """Yield the chunks of one section: a dict whole, rows of a list in parts."""
        if self._next >= len(self._sections) or self._sections[self._next] != name:
            raise ContainerError(f"Section '{name}' is written out of the announced order")
        self._next += 1
        tally = self._tallies[name] = _SectionTally()

        if isinstance(value, dict):
            tally.mapping = True
            tally.rows = len(value)
            body = _dumps({'section': name, 'part': 0, 'rows': value})
            if len(body) > self._chunk_max or count_containers(value) + 1 > self._containers:
                raise ContainerError(f"Section '{name}' does not fit one chunk")
            yield self._part(tally, body)
            return

        pending: List[bytes] = []
        size = containers = 0
        overhead = len(_part_body(name, tally.parts, []))
        for row in value:
            encoded = _dumps(row)
            weight = count_containers(row)
            if pending and (overhead + size + len(pending) + len(encoded) > self._chunk_max
                            or containers + weight + 2 > self._containers):
                yield self._part(tally, _part_body(name, tally.parts, pending))
                pending, size, containers = [], 0, 0
                overhead = len(_part_body(name, tally.parts, []))
            if overhead + len(encoded) > self._chunk_max or weight + 2 > self._containers:
                raise ContainerError(f"A row of section '{name}' does not fit one chunk")
            pending.append(encoded)
            size += len(encoded)
            containers += weight
            tally.rows += 1
        if pending or tally.parts == 0:
            yield self._part(tally, _part_body(name, tally.parts, pending))

    def finish(self, metadata: Optional[Dict[str, Any]] = None) -> bytes:
        """The end record: every section's digest, parts and rows, marked last."""
        if self._next != len(self._sections):
            missing = self._sections[self._next]
            raise ContainerError(f"Section '{missing}' was announced but not written")
        record = {'end': True,
                  'sections': {name: tally.record() for name, tally in self._tallies.items()},
                  'metadata': metadata or {}}
        body = _dumps(record)
        if len(body) > self._chunk_max:
            raise ContainerError("The end record does not fit one chunk")
        return self._frame(body, last=True)


def _dumps(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _part_body(name: str, part: int, rows: List[bytes]) -> bytes:
    return (b'{"part":%d,"rows":[' % part + b','.join(rows) + b'],"section":'
            + json.dumps(name).encode() + b'}')


class ChunkReader:
    """Reads a v4 chunk sequence after its header, refusing any gap, reordering or tail.

    `parts()` yields (section, part, rows) in order; `end` holds the end record's
    metadata once the iteration finished.
    """

    def __init__(self, stream, key: bytes, header: bytes, metadata: Dict[str, Any],
                 nonce_base: bytes):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        self._stream = stream
        self._aead = AESGCM(key)
        self._header = header
        self._nonce_base = nonce_base
        self._gzip = bool(metadata['flags'] & FLAG_GZIP)
        self._chunk_max, self._sections = validate_v4_metadata(metadata)
        self._ceiling = chunk_ciphertext_ceiling(self._chunk_max)
        self._containers = chunk_container_limit(self._chunk_max)
        self._pending = b''
        self.end: Optional[Dict[str, Any]] = None

    def _next_frame(self, counter: int) -> Optional[Tuple[bytes, bool]]:
        length_bytes = self._pending + (_read_exactly(self._stream, 4 - len(self._pending)) or b'')
        self._pending = b''
        if not length_bytes:
            return None
        if len(length_bytes) < 4:
            raise ContainerError(f"Invalid backup: chunk {counter} is truncated")
        length = struct.unpack('>I', length_bytes)[0]
        if not GCM_TAG_SIZE < length <= self._ceiling:
            raise ContainerError(
                f"Invalid backup: chunk {counter} announces {length} bytes, outside what "
                "its header allows")
        sealed = _read_exactly(self._stream, length) or b''
        if len(sealed) < length:
            raise ContainerError(f"Invalid backup: chunk {counter} is truncated")
        self._pending = self._stream.read(1) or b''
        return sealed, not self._pending

    def _open(self, counter: int, sealed: bytes, last: bool) -> bytes:
        nonce = chunk_nonce(self._nonce_base, counter)
        try:
            return self._aead.decrypt(nonce, sealed, chunk_aad(self._header, counter, last))
        except Exception:
            pass
        if last:
            # The stream ends on a chunk written as not last: its end was cut off
            try:
                self._aead.decrypt(nonce, sealed, chunk_aad(self._header, counter, False))
            except Exception:
                raise ChunkAuthError(counter)
            raise ContainerError(
                "Invalid backup: the archive is truncated, its final chunk is missing. "
                "Nothing has been changed.")
        raise ChunkAuthError(counter)

    def parts(self) -> Iterator[Tuple[str, int, Any]]:
        tallies: Dict[str, _SectionTally] = {}
        position = -1          # index in self._sections of the section being read
        counter = 0
        while True:
            if counter >= CHUNK_COUNTER_LIMIT:
                raise ContainerError("Invalid backup: more than 2^32 chunks")
            frame = self._next_frame(counter)
            if frame is None:
                raise ContainerError(
                    "Invalid backup: the archive is truncated, its final chunk is missing. "
                    "Nothing has been changed.")
            sealed, last = frame
            plaintext = self._open(counter, sealed, last)
            if self._gzip:
                plaintext = decompress_bounded(plaintext, chunk_ceiling=self._chunk_max)
            elif len(plaintext) > self._chunk_max:
                raise ContainerError(f"Invalid backup: chunk {counter} exceeds its announced size")
            record = json_loads_bounded(plaintext, max_containers=self._containers)
            counter += 1

            if last:
                self._check_end(record, tallies, position)
                return
            if not isinstance(record, dict) or set(record) != _PART_KEYS:
                raise ContainerError(f"Invalid backup: chunk {counter - 1} is not a section part")
            name, part, rows = record['section'], record['part'], record['rows']
            current = self._sections[position] if position >= 0 else None
            if name != current:
                if (position + 1 >= len(self._sections) or self._sections[position + 1] != name):
                    raise ContainerError(
                        f"Invalid backup: section {name!r} is out of the announced order")
                position += 1
                tallies[name] = _SectionTally()
            tally = tallies[name]
            if type(part) is not int or part != tally.parts:
                raise ContainerError(
                    f"Invalid backup: section '{name}' part {part!r} is out of order")
            if isinstance(rows, dict):
                if part != 0:
                    raise ContainerError(f"Invalid backup: section '{name}' is split")
                tally.mapping = True
            elif not isinstance(rows, list) or tally.mapping:
                raise ContainerError(f"Invalid backup: section '{name}' has malformed rows")
            tally.digest.update(plaintext)
            tally.parts += 1
            tally.rows += len(rows)
            yield name, part, rows

    def _check_end(self, record: Any, tallies: Dict[str, _SectionTally], position: int) -> None:
        if (not isinstance(record, dict) or set(record) != _END_KEYS or record['end'] is not True
                or not isinstance(record['sections'], dict)
                or not isinstance(record['metadata'], dict)):
            raise ContainerError("Invalid backup: the final chunk is not an end record")
        if position + 1 != len(self._sections):
            raise ContainerError(
                f"Incomplete backup: section '{self._sections[position + 1]}' is announced "
                "but missing. Nothing has been changed.")
        announced = record['sections']
        if set(announced) != set(self._sections):
            raise ContainerError("Invalid backup: the end record lists other sections")
        for name, tally in tallies.items():
            if announced[name] != tally.record():
                raise ContainerError(
                    f"Corrupted backup: section '{name}' does not match the digest recorded "
                    "when it was written. Nothing has been changed.")
        self.end = record['metadata']
