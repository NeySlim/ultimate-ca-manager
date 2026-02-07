import labels from './encoding.labels.js'

let labelsMap

export const E_ENCODING = 'Unknown encoding'

// Warning: unlike whatwg-encoding, returns lowercased labels
// Those are case-insensitive and that's how TextDecoder encoding getter normalizes them
// https://encoding.spec.whatwg.org/#names-and-labels
export function normalizeEncoding(label) {
  // fast path
  if (label === 'utf-8' || label === 'utf8' || label === 'UTF-8' || label === 'UTF8') return 'utf-8'
  if (label === 'windows-1252' || label === 'ascii' || label === 'latin1') return 'windows-1252'
  // full map
  if (/[^\w\t\n\f\r .:-]/i.test(label)) return null // must be ASCII (with ASCII whitespace)
  const low = `${label}`.trim().toLowerCase()
  if (Object.hasOwn(labels, low)) return low
  if (!labelsMap) {
    labelsMap = new Map()
    for (const [label, aliases] of Object.entries(labels)) {
      for (const alias of aliases) labelsMap.set(alias, label)
    }
  }

  const mapped = labelsMap.get(low)
  if (mapped) return mapped
  return null
}

// TODO: make this more strict against Symbol.toStringTag
// Is not very significant though, anything faking Symbol.toStringTag could as well override
// prototypes, which is not something we protect against

function isAnyArrayBuffer(x) {
  if (x instanceof ArrayBuffer) return true
  if (globalThis.SharedArrayBuffer && x instanceof SharedArrayBuffer) return true
  if (!x || typeof x.byteLength !== 'number') return false
  const s = Object.prototype.toString.call(x)
  return s === '[object ArrayBuffer]' || s === '[object SharedArrayBuffer]'
}

export function fromSource(x) {
  if (x instanceof Uint8Array) return x
  if (ArrayBuffer.isView(x)) return new Uint8Array(x.buffer, x.byteOffset, x.byteLength)
  if (isAnyArrayBuffer(x)) {
    if ('detached' in x) return x.detached === true ? new Uint8Array() : new Uint8Array(x)
    // Old engines without .detached, try-catch
    try {
      return new Uint8Array(x)
    } catch {
      return new Uint8Array()
    }
  }

  throw new TypeError('Argument must be a SharedArrayBuffer, ArrayBuffer or ArrayBufferView')
}

// Warning: unlike whatwg-encoding, returns lowercased labels
// Those are case-insensitive and that's how TextDecoder encoding getter normalizes them
export function getBOMEncoding(input) {
  const u8 = fromSource(input) // asserts
  if (u8.length >= 3 && u8[0] === 0xef && u8[1] === 0xbb && u8[2] === 0xbf) return 'utf-8'
  if (u8.length < 2) return null
  if (u8[0] === 0xff && u8[1] === 0xfe) return 'utf-16le'
  if (u8[0] === 0xfe && u8[1] === 0xff) return 'utf-16be'
  return null
}

const uppercasePrefixes = new Set(['utf', 'iso', 'koi', 'euc', 'ibm', 'gbk'])

// Unlike normalizeEncoding, case-sensitive
// https://encoding.spec.whatwg.org/#names-and-labels
export function labelToName(label) {
  const enc = normalizeEncoding(label)
  if (enc === 'utf-8') return 'UTF-8' // fast path
  if (!enc) return enc
  if (uppercasePrefixes.has(enc.slice(0, 3))) return enc.toUpperCase()
  if (enc === 'big5') return 'Big5'
  if (enc === 'shift_jis') return 'Shift_JIS'
  return enc
}
