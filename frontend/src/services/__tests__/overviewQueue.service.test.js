/**
 * The overview's queue past the server's limit: the interventions fill the rows it returns, so the rows only to watch
 * its counts name are asked apart (kind=…) and added after them, each once.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.hoisted(() => vi.fn())
vi.mock('../apiClient', async () => {
  const actual = await vi.importActual('../apiClient')
  return { ...actual, apiClient: { get } }
})

import { overviewService } from '../overview.service'

const crl = (id) => ({ kind: 'crl_missing', tier: 'critical', id, label: `CA ${id}` })
const expiring = (id, tier = 'warning') => ({ kind: 'ca_expiring', tier, id, label: `CA ${id}` })

describe('overviewService.getQueue', () => {
  beforeEach(() => get.mockReset())

  it('a whole queue is one request', async () => {
    get.mockResolvedValueOnce({ data: { items: [crl(1), expiring(2)], total: 2, counts: { crl_missing: 1, ca_expiring: 1 } } })
    const res = await overviewService.getQueue()
    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('/dashboard/queue?limit=100')
    expect(res.data.items.map((i) => i.id)).toEqual([1, 2])
  })

  it('a queue cut at its limit by interventions asks the rows to watch apart and adds them after', async () => {
    const act = Array.from({ length: 3 }, (_, i) => crl(i + 1))
    get.mockResolvedValueOnce({ data: { items: act, total: 5, counts: { crl_missing: 3, ca_expiring: 2 } } })
    get.mockResolvedValueOnce({ data: { items: [expiring(9), expiring(8)], total: 5, counts: {} } })
    const res = await overviewService.getQueue(3)
    expect(get).toHaveBeenLastCalledWith('/dashboard/queue?limit=3&kind=client_renewal_overdue&kind=ca_expiring&kind=truststore_expiring')
    expect(res.data.items.map((i) => `${i.kind}-${i.id}`)).toEqual(['crl_missing-1', 'crl_missing-2', 'crl_missing-3', 'ca_expiring-9', 'ca_expiring-8'])
    expect(res.data.total).toBe(5)
  })

  it('a row already listed is not added twice; a cut queue whose rows to watch are all there asks nothing more', async () => {
    get.mockResolvedValueOnce({ data: { items: [crl(1), expiring(7, 'critical')], total: 4, counts: { crl_missing: 2, ca_expiring: 2 } } })
    get.mockResolvedValueOnce({ data: { items: [expiring(7, 'critical'), expiring(8)] } })
    const res = await overviewService.getQueue(2)
    expect(res.data.items.map((i) => i.id)).toEqual([1, 7, 8])
    get.mockReset()
    get.mockResolvedValueOnce({ data: { items: [crl(1), expiring(7)], total: 3, counts: { crl_missing: 2, ca_expiring: 1 } } })
    await overviewService.getQueue(2)
    expect(get).toHaveBeenCalledTimes(1)
  })
})
