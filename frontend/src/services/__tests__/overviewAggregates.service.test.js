/**
 * The overview's second aggregates: expirations per day, revocation coverage, and the certificate list query of a
 * day or a week of the expiry calendar.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.hoisted(() => vi.fn())
vi.mock('../apiClient', async () => {
  const actual = await vi.importActual('../apiClient')
  return { ...actual, apiClient: { get } }
})

import { overviewService } from '../overview.service'
import { buildQueryString } from '../apiClient'

describe('overviewService, second aggregates', () => {
  beforeEach(() => get.mockReset().mockResolvedValue({ data: {} }))

  it('asks the expirations of a window, 90 days by default', async () => {
    await overviewService.getExpirations()
    expect(get).toHaveBeenLastCalledWith('/dashboard/expirations?days=90')
    await overviewService.getExpirations(365)
    expect(get).toHaveBeenLastCalledWith('/dashboard/expirations?days=365')
  })

  it('asks the revocation coverage with a bounded list', async () => {
    await overviewService.getRevocation()
    expect(get).toHaveBeenLastCalledWith('/dashboard/revocation?limit=10')
    await overviewService.getRevocation(6)
    expect(get).toHaveBeenLastCalledWith('/dashboard/revocation?limit=6')
  })

  it('opens one day of the calendar as a half-open UTC interval on the population', () => {
    const query = overviewService.expirationQuery({ status: ['valid', 'expiring'], expires_to: '2027-02-20' }, '2026-12-14')
    expect(query).toEqual({ status: ['valid', 'expiring'], expires_from: '2026-12-14', expires_to: '2026-12-15' })
    expect(buildQueryString(query)).toBe('?status=valid&status=expiring&expires_from=2026-12-14&expires_to=2026-12-15')
  })

  it('opens a week across a month and a year end', () => {
    expect(overviewService.expirationQuery({ status: ['valid', 'expiring'] }, '2026-12-28', '2027-01-03')).toEqual({
      status: ['valid', 'expiring'], expires_from: '2026-12-28', expires_to: '2027-01-04',
    })
    expect(overviewService.expirationQuery(null, '2028-02-28', '2028-02-29').expires_to).toBe('2028-03-01')
  })
})
