import { describe, expect, it } from 'vitest'
import { expiryCheckOutcome } from '../expiryCheck'

describe('manual expiry check answer', () => {
  it('a run held by another node is not reported as zero alerts sent', () => {
    expect(expiryCheckOutcome({ status: 'skipped', reason: 'another node is running the expiry checks' }))
      .toEqual({ skipped: true })
  })
  it('counts the certificate and CRL alerts of a run, taken over or not', () => {
    const counts = { cert_expiring: { notified: 2 }, crl_expiring: { notified: 1 } }
    expect(expiryCheckOutcome(counts)).toEqual({ skipped: false, count: 3 })
    expect(expiryCheckOutcome({ ...counts, status: 'warning' })).toEqual({ skipped: false, count: 3 })
  })
})
