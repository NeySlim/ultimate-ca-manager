/** Work queue groups: every kind the server may send has its chip, and the split never hides a critical row. */
import { describe, it, expect } from 'vitest'
import en from '../../i18n/locales/en.json'
import { GROUP_OF, QUEUE_GROUPS, isWatch, queueSplit } from '../overviewQueue'

describe('queue groups', () => {
  it('place every kind of the queue in exactly one group, each with a label and a cause', () => {
    const kinds = Object.keys(en.overview.kind)
    expect(Object.values(QUEUE_GROUPS).flat().sort()).toEqual([...kinds].sort())
    for (const kind of kinds) expect(en.overview.cause[kind], kind).toBeTruthy()
    for (const group of Object.keys(QUEUE_GROUPS)) expect(en.overview.queue.group[group], group).toBeTruthy()
    expect(GROUP_OF.crl_missing).toBe('crl')
  })

  it('watches what needs no action today, never a critical row', () => {
    expect(isWatch({ kind: 'ca_expiring', tier: 'warning' })).toBe(true)
    expect(isWatch({ kind: 'client_renewal_overdue', tier: 'warning' })).toBe(true)
    expect(isWatch({ kind: 'ca_expiring', tier: 'critical' })).toBe(false)
    expect(isWatch({ kind: 'manual_renewal_due', tier: 'warning' })).toBe(false)
  })

  it('splits the whole queue from the totals per kind, critical rows counted as interventions', () => {
    const data = {
      total: 20, counts: { manual_renewal_due: 11, ca_expiring: 2, truststore_expiring: 3, key_recovery_pending: 4 },
      items: [{ kind: 'ca_expiring', tier: 'critical', id: 1 }, { kind: 'ca_expiring', tier: 'warning', id: 2 }],
    }
    expect(queueSplit(data)).toEqual({ total: 20, watch: 4, act: 16 })
  })

  it('has no figure before the queue answered', () => {
    expect(queueSplit(null)).toEqual({ total: null, watch: 0, act: null })
  })
})
