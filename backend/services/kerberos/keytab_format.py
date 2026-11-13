"""MIT keytab files (formats 0x0501 and 0x0502): entries read, files composed by concatenation.

Pure functions over bytes, so the migration, the restore and the acceptor read keytabs alike.
"""
import struct
from dataclasses import dataclass
from typing import List, Optional

KRB5_NT_UNKNOWN = 0


@dataclass(frozen=True)
class Entry:
    realm: str
    components: tuple
    kvno: int
    enctype: int
    # The entry as format 0x0502 stores it, without its size
    raw: bytes

    @property
    def principal(self):
        return '/'.join(self.components) + '@' + self.realm


class _Reader:
    def __init__(self, data, order):
        self.data, self.order, self.pos = data, order, 0

    def take(self, fmt):
        (value,) = struct.unpack_from(self.order + fmt, self.data, self.pos)
        self.pos += struct.calcsize(fmt)
        return value

    def counted(self):
        length = self.take('H')
        if self.pos + length > len(self.data):
            raise struct.error('counted string past the end of the entry')
        value = self.data[self.pos:self.pos + length]
        self.pos += length
        return value


def _entry(raw, version):
    """One entry; version 1 is in host order and counts the realm among the components."""
    r = _Reader(raw, '>' if version == 2 else '=')
    count = r.take('H') - (1 if version == 1 else 0)
    if count < 1:
        raise ValueError('an entry without a name component')
    realm = r.counted()
    components = tuple(r.counted() for _ in range(count))
    name_type = r.take('I') if version == 2 else KRB5_NT_UNKNOWN
    timestamp = r.take('I')
    kvno = r.take('B')
    enctype = r.take('H')
    key = r.counted()
    # MIT: four bytes left hold the 32-bit kvno, which wins when it is not zero
    if len(raw) - r.pos >= 4:
        kvno = r.take('I') or kvno
    text = tuple(c.decode('utf-8') for c in components)
    if version == 2:
        encoded = raw
    else:
        def counted(value):
            return struct.pack('>H', len(value)) + value
        encoded = (struct.pack('>H', count) + counted(realm) + b''.join(counted(c) for c in components)
                   + struct.pack('>IIBH', name_type, timestamp, kvno & 0xff, enctype) + counted(key)
                   + struct.pack('>I', kvno))
    return Entry(realm.decode('utf-8'), text, kvno, enctype, encoded)


def read_entries(data) -> Optional[List[Entry]]:
    """The entries of an MIT keytab, holes skipped; None when it is not one. Like MIT, reading
    stops at a zero size or at an entry the file cuts short."""
    if not data or len(data) < 2 or data[0] != 5 or data[1] not in (1, 2):
        return None
    version, order = data[1], '>' if data[1] == 2 else '='
    entries, pos = [], 2
    try:
        while pos + 4 <= len(data):
            (size,) = struct.unpack_from(f'{order}i', data, pos)
            pos += 4
            if size < 0:   # a hole left by a deleted entry
                pos += -size
                continue
            if size == 0 or pos + size > len(data):
                break
            entries.append(_entry(data[pos:pos + size], version))
            pos += size
    except (struct.error, UnicodeDecodeError, ValueError):
        return None
    return entries


def compose(entries) -> bytes:
    """A format 0x0502 keytab holding *entries*, in order."""
    return b'\x05\x02' + b''.join(struct.pack('>i', len(e.raw)) + e.raw for e in entries)
