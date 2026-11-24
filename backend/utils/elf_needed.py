"""The DT_NEEDED and DT_SONAME entries of an ELF shared object, read from its program headers.

Only what the dynamic loader reads (PT_LOAD, PT_DYNAMIC, DT_STRTAB): a stripped library
without section headers reads the same. Nothing is loaded or executed.
"""
import struct

_PT_LOAD, _PT_DYNAMIC = 1, 2
_DT_NULL, _DT_NEEDED, _DT_STRTAB, _DT_STRSZ, _DT_SONAME = 0, 1, 5, 10, 14


def needed_libraries(path):
    """The sonames ``path`` names in its dynamic section; ValueError for a file that is no ELF."""
    return dynamic_names(path)[1]


def dynamic_names(path):
    """(its DT_SONAME or None, its DT_NEEDED sonames); ValueError for a file that is no ELF."""
    with open(path, 'rb') as handle:
        data = handle.read()
    try:
        return _parse(path, data)
    except (struct.error, OverflowError):
        # An offset past the file, or past what an index holds (2^63 and more), is a broken file
        raise ValueError(f'{path}: truncated or malformed ELF headers') from None


def _parse(path, data):
    if data[:4] != b'\x7fELF' or len(data) < 64:
        raise ValueError(f'{path} is not an ELF file')
    bits = {1: 32, 2: 64}.get(data[4])
    endian = {1: '<', 2: '>'}.get(data[5])
    if bits is None or endian is None:
        raise ValueError(f'{path}: unknown ELF class or byte order')
    if bits == 64:
        phoff, = struct.unpack_from(endian + 'Q', data, 32)
        phentsize, phnum = struct.unpack_from(endian + 'HH', data, 54)
        header, dyn = endian + 'IIQQQQQQ', endian + 'qQ'
    else:
        phoff, = struct.unpack_from(endian + 'I', data, 28)
        phentsize, phnum = struct.unpack_from(endian + 'HH', data, 42)
        header, dyn = endian + 'IIIIIIII', endian + 'iI'
    loads, dynamic = [], None
    for index in range(phnum):
        fields = struct.unpack_from(header, data, phoff + index * phentsize)
        if bits == 64:
            p_type, _flags, offset, vaddr, _paddr, filesz = fields[:6]
        else:
            p_type, offset, vaddr, _paddr, filesz = fields[:5]
        if p_type == _PT_LOAD:
            loads.append((vaddr, offset, filesz))
        elif p_type == _PT_DYNAMIC:
            dynamic = (offset, filesz)
    if dynamic is None:
        return None, []
    entries, strtab, strsz, soname = [], None, None, None
    size = struct.calcsize(dyn)
    for position in range(dynamic[0], dynamic[0] + dynamic[1] - size + 1, size):
        tag, value = struct.unpack_from(dyn, data, position)
        if tag == _DT_NULL:
            break
        if tag == _DT_NEEDED:
            entries.append(value)
        elif tag == _DT_STRTAB:
            strtab = value
        elif tag == _DT_STRSZ:
            strsz = value
        elif tag == _DT_SONAME:
            soname = value
    if strtab is None:
        raise ValueError(f'{path}: no string table in its dynamic section')
    # DT_STRTAB is an address: the segment that maps it gives its place in the file
    base = next((offset + strtab - vaddr for vaddr, offset, filesz in loads
                 if vaddr <= strtab < vaddr + filesz), None)
    if base is None:
        raise ValueError(f'{path}: its string table is outside every loaded segment')
    end = min(len(data), base + strsz) if strsz else len(data)
    names = []
    for value in entries + ([soname] if soname is not None else []):
        start = base + value
        stop = data.find(b'\0', start, end) if start < end else -1
        if stop < 0:
            raise ValueError(f'{path}: a dynamic entry lies outside its string table')
        names.append(data[start:stop].decode('utf-8', errors='replace'))
    return (names.pop() if soname is not None else None), names
