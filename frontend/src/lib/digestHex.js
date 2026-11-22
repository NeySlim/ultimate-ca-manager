/** A digest (plain or colon hexadecimal) as upper-case octets joined by colons; anything else as it is. */
export function digestHex(value) {
  const raw = String(value ?? '').trim()
  const hex = raw.replace(/[:\s]/g, '')
  if (!hex || hex.length % 2 || !/^[0-9a-f]+$/i.test(hex)) return raw
  return hex.toUpperCase().match(/../g).join(':')
}
