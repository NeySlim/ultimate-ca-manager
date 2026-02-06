import {
  fromSource,
  getBOMEncoding,
  normalizeEncoding,
  E_ENCODING,
} from './fallback/encoding.api.js'
import labels from './fallback/encoding.labels.js'

// Lite-weight version which re-exports existing implementations on browsers,
// while still being aliased to the full impl in RN and Node.js

// WARNING: Note that browsers have bugs (which hopefully will get fixed soon)

const { TextDecoder, TextEncoder, TextDecoderStream, TextEncoderStream } = globalThis

export { normalizeEncoding, getBOMEncoding, labelToName } from './fallback/encoding.api.js'
export { TextDecoder, TextEncoder, TextDecoderStream, TextEncoderStream }

// https://encoding.spec.whatwg.org/#decode
export function legacyHookDecode(input, fallbackEncoding = 'utf-8') {
  let u8 = fromSource(input)
  const bomEncoding = getBOMEncoding(u8)
  if (bomEncoding) u8 = u8.subarray(bomEncoding === 'utf-8' ? 3 : 2)
  const enc = bomEncoding ?? normalizeEncoding(fallbackEncoding) // "the byte order mark is more authoritative than anything else"
  if (enc === 'utf-8') return new TextDecoder('utf-8', { ignoreBOM: true }).decode(u8) // fast path
  if (enc === 'replacement') return u8.byteLength > 0 ? '\uFFFD' : ''
  if (!Object.hasOwn(labels, enc)) throw new RangeError(E_ENCODING)
  return new TextDecoder(enc, { ignoreBOM: true }).decode(u8)
}
