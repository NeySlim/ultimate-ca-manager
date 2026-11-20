// OpenType `name` records (Windows, en-US) of a WOFF2 file: W3C WOFF2 header, table
// directory, then one brotli stream holding the tables in directory order.
import zlib from 'zlib'

const KNOWN = ['cmap', 'head', 'hhea', 'hmtx', 'maxp', 'name', 'OS/2', 'post', 'cvt ', 'fpgm', 'glyf', 'loca',
  'prep', 'CFF ', 'VORG', 'EBDT', 'EBLC', 'gasp', 'hdmx', 'kern', 'LTSH', 'PCLT', 'VDMX', 'vhea', 'vmtx', 'BASE',
  'GDEF', 'GPOS', 'GSUB', 'EBSC', 'JSTF', 'MATH', 'CBDT', 'CBLC', 'COLR', 'CPAL', 'SVG ', 'sbix', 'acnt', 'avar',
  'bdat', 'bloc', 'bsln', 'cvar', 'fdsc', 'feat', 'fmtx', 'fvar', 'gvar', 'hsty', 'just', 'lcar', 'mort', 'morx',
  'opbd', 'prop', 'trak', 'Zapf', 'Silf', 'Glat', 'Gloc', 'Feat', 'Sill']

function base128(buf, pos) {
  let value = 0
  for (let i = 0; i < 5; i++) {
    const byte = buf[pos.p++]
    value = value * 128 + (byte & 0x7f)
    if (!(byte & 0x80)) return value
  }
  throw new Error('bad UIntBase128')
}

// Windows en-US records of a raw `name` table
function nameRecords(name) {
  const count = name.readUInt16BE(2)
  const strings = name.readUInt16BE(4)
  const out = {}
  for (let i = 0; i < count; i++) {
    const r = 6 + i * 12
    if (name.readUInt16BE(r) !== 3 || name.readUInt16BE(r + 4) !== 0x409) continue
    const len = name.readUInt16BE(r + 8)
    const at = strings + name.readUInt16BE(r + 10)
    let s = ''
    for (let k = 0; k < len; k += 2) s += String.fromCharCode(name.readUInt16BE(at + k))
    out[name.readUInt16BE(r + 6)] = s
  }
  return out
}

/** Name records of an uncompressed TrueType or OpenType file (sfnt table directory). */
export function sfntNames(buf) {
  const magic = buf.readUInt32BE(0)
  if (magic !== 0x00010000 && buf.toString('latin1', 0, 4) !== 'OTTO' && buf.toString('latin1', 0, 4) !== 'true') throw new Error('not an sfnt file')
  const numTables = buf.readUInt16BE(4)
  for (let i = 0; i < numTables; i++) {
    const r = 12 + i * 16
    if (buf.toString('latin1', r, r + 4) !== 'name') continue
    const offset = buf.readUInt32BE(r + 8)
    return nameRecords(buf.subarray(offset, offset + buf.readUInt32BE(r + 12)))
  }
  throw new Error('no name table')
}

/** Name records of a shipped font, whatever its container. */
export function fontNames(buf) {
  return buf.toString('latin1', 0, 4) === 'wOF2' ? woff2Names(buf) : sfntNames(buf)
}

export function woff2Names(buf) {
  if (buf.toString('latin1', 0, 4) !== 'wOF2') throw new Error('not a WOFF2 file')
  const numTables = buf.readUInt16BE(12)
  const compressed = buf.readUInt32BE(20)
  const pos = { p: 48 }
  const tables = []
  for (let i = 0; i < numTables; i++) {
    const flags = buf[pos.p++]
    let tag = KNOWN[flags & 0x3f]
    if ((flags & 0x3f) === 63) { tag = buf.toString('latin1', pos.p, pos.p + 4); pos.p += 4 }
    const version = (flags >> 6) & 3
    let length = base128(buf, pos)
    // glyf and loca are transformed unless version 3; every other table only with a non-zero version
    const transformed = tag === 'glyf' || tag === 'loca' ? version !== 3 : version !== 0
    if (transformed) length = base128(buf, pos)
    tables.push({ tag, length })
  }
  const data = zlib.brotliDecompressSync(buf.subarray(pos.p, pos.p + compressed))
  let offset = 0
  let name
  for (const t of tables) {
    if (t.tag === 'name') name = data.subarray(offset, offset + t.length)
    offset += t.length
  }
  if (!name) throw new Error('no name table')
  return nameRecords(name)
}
