import { describe, it, expect } from 'vitest'
import { chooseTiles, coverParts, daysSince } from '../overviewTiles'

const NOW = Date.parse('2026-11-22T12:00:00Z')
const DAY = 86400000
const at = (days) => new Date(NOW + days * DAY).toISOString()
const ca = (id, over = {}) => ({ id, refid: `ca-${id}`, descr: `CA ${id}`, status: 'active', valid_from: at(-100), valid_to: at(900),
  cdp_enabled: true, ocsp_enabled: false, has_private_key: true, key_type: 'EC P-256', ...over })
const crl = (caId, nextDays, over = {}) => ({ ca_id: caId, next_update: at(nextDays), is_stale: false, is_delta: false, ...over })

describe('chooseTiles', () => {
  it('says the worst state of an authority: revoked, expired, CRL overdue or missing, then a near end', () => {
    const { tiles } = chooseTiles({
      cas: [ca(1), ca(2, { status: 'revoked' }), ca(3, { valid_to: at(-1) }), ca(4), ca(5), ca(6, { valid_to: at(40) })],
      crls: [crl(1, 3), crl(4, -2), crl(6, 3), crl(2, 3), crl(3, 3)], providers: [], now: NOW,
    })
    const by = Object.fromEntries(tiles.map((x) => [x.id, [x.tone, x.key]]))
    expect(by).toMatchObject({ 1: ['good', 'inService'], 2: ['bad', 'revoked'], 3: ['bad', 'expired'], 4: ['bad', 'crlStale'],
      5: ['bad', 'crlMissing'], 6: ['warn', 'expiresIn'] })
    expect(tiles.find((x) => x.id === 6).count).toBe(40)
  })

  it('puts the authorities in alert first, then the most active over 7 days, then by name', () => {
    const issuance = { by_ca: [
      { caref: 'ca-2', periods: Array.from({ length: 30 }, (_, i) => ({ issued: i >= 23 ? 1 : 9, renewed: 0 })) },
      { caref: 'ca-3', periods: [{ issued: 1, renewed: 1 }] },
    ] }
    const { tiles } = chooseTiles({ cas: [ca(1), ca(2), ca(3), ca(4, { cdp_enabled: false, valid_to: at(10) })], crls: [crl(1, 3), crl(2, 3), crl(3, 3)], issuance, now: NOW })
    expect(tiles.map((x) => x.id)).toEqual([4, 2, 3, 1])
    expect(tiles[1].activity).toEqual([1, 1, 1, 1, 1, 1, 1])
    expect(tiles[2].issued).toBe(2)
  })

  it('turns the validity gauge amber in its last third and names the key guard', () => {
    const { tiles } = chooseTiles({ cas: [ca(1, { valid_from: at(-70), valid_to: at(30), uses_hsm: true, hsm_provider_name: 'Luna' }), ca(2)], crls: [crl(1, 3), crl(2, 3)], now: NOW })
    expect(tiles[0]).toMatchObject({ id: 1, elapsed: 70, late: true, guard: { hsm: 'Luna' } })
    expect(tiles[1]).toMatchObject({ late: false, guard: { software: true } })
  })

  it('keeps six tiles: two for the HSM modules (more when there are fewer authorities), the modules in error first', () => {
    const cas = Array.from({ length: 8 }, (_, i) => ca(i + 1, { hsm_provider_id: i < 3 ? 7 : null }))
    const providers = [{ id: 7, name: 'Luna', status: 'connected', key_count: 6 }, { id: 8, name: 'Bao', status: 'error' }, { id: 9, name: 'Soft', status: 'unknown' }]
    const many = chooseTiles({ cas, crls: cas.map((c) => crl(c.id, 3)), providers, now: NOW })
    expect(many.tiles).toHaveLength(6)
    expect(many.tiles.filter((x) => x.kind === 'hsm').map((x) => [x.id, x.key])).toEqual([[8, 'hsmError'], [7, 'reachable']])
    expect(many.tiles.find((x) => x.id === 7 && x.kind === 'hsm').cas).toBe(3)
    const few = chooseTiles({ cas: [ca(1)], crls: [crl(1, 3)], providers, now: NOW })
    expect(few.tiles.map((x) => x.kind)).toEqual(['ca', 'hsm', 'hsm', 'hsm'])
    expect(few).toMatchObject({ authorities: 1, modules: 3 })
  })

  it('tells a module never tested from one whose state is unknown since its last test', () => {
    const { tiles } = chooseTiles({ cas: [], providers: [{ id: 1, status: 'unknown' }, { id: 2, status: 'unknown', last_tested_at: at(-30) }], now: NOW })
    expect(tiles.map((x) => x.key)).toEqual(['untested', 'unknown'])
  })

  it('reads no CRL state when the CRL list did not load', () => {
    const { tiles } = chooseTiles({ cas: [ca(1)], crls: undefined, now: NOW })
    expect(tiles[0]).toMatchObject({ tone: 'good', crl: { state: 'unknown' } })
  })
})

describe('coverParts and daysSince', () => {
  it('splits the active authorities in current, to publish (overdue or missing) and without distribution point', () => {
    expect(coverParts({ current: 126, stale: 2, missing: 1, no_cdp: 7 }).map((x) => [x.key, x.value]))
      .toEqual([['current', 126], ['toPublish', 3], ['noCdp', 7]])
  })
  it('counts whole days since a past date, one at least', () => {
    expect(daysSince(at(-192.5), NOW)).toBe(192)
    expect(daysSince(at(-0.1), NOW)).toBe(1)
  })
})
