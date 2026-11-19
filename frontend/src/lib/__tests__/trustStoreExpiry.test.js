import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { trustStoreExpiryStatus } from '../expiry'

const NOW = new Date('2026-06-01T12:00:00Z')
const at = (ms) => new Date(NOW.getTime() + ms).toISOString()
const HOUR = 3600 * 1000
const DAY = 24 * HOUR

describe('trustStoreExpiryStatus follows days_remaining', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => vi.useRealTimers())

  it('reads half a day left as expiring, not expired', () => {
    expect(trustStoreExpiryStatus(at(12 * HOUR))).toBe('expiring')
  })
  it('reads a second past as expired', () => {
    expect(trustStoreExpiryStatus(at(-1000))).toBe('expired')
  })
  it('keeps the 90-day window on whole days left', () => {
    expect(trustStoreExpiryStatus(at(90 * DAY - 5 * 60000))).toBe('expiring')
    expect(trustStoreExpiryStatus(at(90 * DAY + 5 * 60000))).toBe('valid')
  })
  it('lists an entry with no date as valid', () => {
    expect(trustStoreExpiryStatus(null)).toBe('valid')
  })
})
