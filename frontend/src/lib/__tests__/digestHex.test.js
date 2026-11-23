import { describe, it, expect } from 'vitest'
import { digestHex } from '../digestHex'

describe('digestHex', () => {
  it('writes a digest as octets in upper-case hexadecimal, as a certificate shows its own', () => {
    expect(digestHex('ab01cd02')).toBe('AB:01:CD:02')
    expect(digestHex('ab:01:CD:02')).toBe('AB:01:CD:02')
    expect(digestHex(' AB 01 ')).toBe('AB:01')
  })

  it('leaves what is not a digest as it is, and nothing as nothing', () => {
    expect(digestHex('abc')).toBe('abc')
    expect(digestHex('not-hex')).toBe('not-hex')
    expect(digestHex('')).toBe('')
    expect(digestHex(null)).toBe('')
    expect(digestHex(undefined)).toBe('')
  })
})
