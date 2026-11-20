/**
 * A certificate on a phone is the mockup record: no icon before its name, the issuer,
 * the source in words and the key note on the line of facts.
 */
import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useCertificateCard } from '../useCertificateColumns'

const t = (key) => key

describe('useCertificateCard', () => {
  it('draws no icon and names the source in words', () => {
    const card = renderHook(() => useCertificateCard(t)).result.current
    const c = card({ id: 1, cn: 'web.example.com', issuer: 'CN=Issuing CA', source: 'manual', has_private_key: false, valid_to: '2027-01-01T00:00:00Z' })
    expect(c.icon).toBeUndefined()
    expect(c.meta.filter(Boolean)).toEqual(['Issuing CA', 'certificates.sourceManual'])
  })
})
