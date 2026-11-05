/** #437: shape checks and payload of the custom extension editor rows. */
import { describe, it, expect } from 'vitest'
import { customExtensionsPayload, isDottedOid, isEvenHex, rowsFromStored, truncateHex } from '../customExtensions'

describe('customExtensions', () => {
  it('accepts dotted OIDs only', () => {
    for (const ok of ['1.2', '2.999.1', '1.3.6.1.4.1.99999.1', ' 1.2.3 ']) expect(isDottedOid(ok)).toBe(true)
    for (const bad of ['', '1', '3.1', '1.40', '1.2.03', '1..2', 'a.b', '1.2.']) expect(isDottedOid(bad)).toBe(false)
  })

  it('wants an even number of hex digits, separators allowed', () => {
    expect(isEvenHex('0C:05 68')).toBe(true)
    expect(isEvenHex('abc')).toBe(false)
    expect(isEvenHex('zz')).toBe(false)
    expect(isEvenHex('')).toBe(false)
  })

  it('builds the payload and drops blank rows', () => {
    const { entries, errors, valid } = customExtensionsPayload([
      { oid: ' 1.3.6.1.4.1.99999.1 ', critical: true, value: '0C:05:68:65:6C:6C:6F' },
      { oid: '', critical: false, value: '' },
    ])
    expect(valid).toBe(true)
    expect(errors).toEqual([null, null])
    expect(entries).toEqual([{ oid: '1.3.6.1.4.1.99999.1', critical: true, value: '0c0568656c6c6f' }])
  })

  it('names the problem of each row', () => {
    const { errors, valid, entries } = customExtensionsPayload([
      { oid: '1.2.3', value: '0500' },
      { oid: 'nope', value: '0500' },
      { oid: '1.2.4', value: '' },
      { oid: '1.2.5', value: 'abc' },
      { oid: '1.2.3', value: '0101' },
    ])
    expect(valid).toBe(false)
    expect(errors).toEqual([null, 'customExtensions.invalidOid', 'customExtensions.emptyValue',
      'customExtensions.invalidHex', 'customExtensions.duplicateOid'])
    expect(entries.map(e => e.oid)).toEqual(['1.2.3'])
  })

  it('reads a stored list and truncates long values', () => {
    expect(rowsFromStored([{ oid: '1.2.3', critical: true, value: '0500' }, null]))
      .toEqual([{ oid: '1.2.3', critical: true, value: '0500' }, { oid: '', critical: false, value: '' }])
    expect(rowsFromStored(undefined)).toEqual([])
    expect(truncateHex('ab'.repeat(30), 8)).toBe('abababab…')
    expect(truncateHex('abcd', 8)).toBe('abcd')
  })
})
