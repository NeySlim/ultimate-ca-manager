/**
 * Hybrid pair (RFC 9763) calls: revoke_related travels only when the dialog
 * asked about it, bulk requests keep a pair together, and the bundle goes
 * through the export route.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.hoisted(() => vi.fn().mockResolvedValue({ data: {} }))
vi.mock('../apiClient', async () => {
  const actual = await vi.importActual('../apiClient')
  return { ...actual, apiClient: { post } }
})

import { certificatesService } from '../certificates.service'

describe('certificatesService and hybrid pairs', () => {
  beforeEach(() => post.mockClear())

  it.each([true, false])('sends revoke_related=%s when asked', async (value) => {
    await certificatesService.revoke(11, 'keyCompromise', { revokeRelated: value })
    expect(post).toHaveBeenCalledWith('/certificates/11/revoke', { reason: 'keyCompromise', revoke_related: value })
  })

  it('leaves the default to the server for a single certificate', async () => {
    await certificatesService.revoke(5, 'superseded')
    expect(post).toHaveBeenCalledWith('/certificates/5/revoke', { reason: 'superseded' })
  })

  it.each([true, false])('sends revoke_related=%s on a bulk revoke', async (value) => {
    await certificatesService.bulkRevoke([1, 2], 'superseded', { revokeRelated: value })
    expect(post).toHaveBeenCalledWith('/certificates/bulk/revoke', { ids: [1, 2], reason: 'superseded', revoke_related: value })
  })

  // 150 ids: 1 and 150 form a pair, which a plain split at 100 would separate
  const selection = Array.from({ length: 150 }, (_, i) => i + 1)
  const relatedOf = (id) => ({ 1: 150, 150: 1 })[id]
  const batches = () => post.mock.calls.map(([, body]) => body.ids)

  it.each([
    ['revoke', () => certificatesService.bulkRevoke(selection, 'superseded', { relatedOf })],
    ['renew', () => certificatesService.bulkRenew(selection, { relatedOf })],
  ])('keeps both members of a pair in one bulk %s request', async (_name, run) => {
    await run()
    expect(batches().length).toBe(2)
    expect(batches().every((ids) => ids.length <= 100)).toBe(true)
    expect(batches().flat().sort((a, b) => a - b)).toEqual(selection)
    const withFirst = batches().find((ids) => ids.includes(1))
    expect(withFirst).toContain(150)
  })

  // 1 names 50 one way (a second request against 50) and comes first; 50 and 150 name each other
  it('keeps a mutual pair together when a one-way link to a member comes first', async () => {
    const oneWay = (id) => ({ 1: 50, 50: 150, 150: 50 })[id]
    await certificatesService.bulkRevoke(selection, 'superseded', { relatedOf: oneWay })
    const withB = batches().find((ids) => ids.includes(150))
    expect(withB).toContain(50)
    expect(batches().every((ids) => ids.length <= 100)).toBe(true)
    expect(batches().flat().sort((a, b) => a - b)).toEqual(selection)
  })

  it('creates a pair with the hybrid member as given', async () => {
    const data = { ca_id: '3', cn: 'pair.example.com', hybrid: { classical: 'EC-P256', pq: 'ML-DSA-65' } }
    await certificatesService.create(data)
    expect(post).toHaveBeenCalledWith('/certificates', data)
  })
})
