import { describe, it, expect } from 'vitest'
import { listHref, parseOverviewFilters, toListParams, withoutFilter } from '../overviewFilters'
import { normalizeLayout, presetLayout, visibleCards, CARD_IDS } from '../overviewLayout'

describe('overview filters in the URL', () => {
  it('round-trips a hint into the params the list receives', () => {
    const href = listHref({ live: 'true', sig_hash: ['sha1', 'md5'], key_bits_below: '3072' })
    const pairs = parseOverviewFilters(href.slice(href.indexOf('?')))
    expect(toListParams(pairs)).toEqual({ live: 'true', sig_hash: ['sha1', 'md5'], key_bits_below: '3072' })
  })
  it('ignores unknown parameters', () => {
    expect(parseOverviewFilters('?status=valid&bogus=1&renewal=renewal_declined')).toEqual([['renewal', 'renewal_declined']])
  })
  it('removes one value of a repeated filter, or a whole filter', () => {
    expect(withoutFilter('?sig_hash=sha1&sig_hash=md5&live=true', 'sig_hash', 'sha1')).toBe('?live=true&sig_hash=md5')
    expect(withoutFilter('?live=true&no_key=true', 'live')).toBe('?no_key=true')
    expect(withoutFilter('?live=true', 'live')).toBe('')
  })
  it('has no list without a hint', () => {
    expect(listHref(null)).toBeNull()
  })
})

describe('overview layout', () => {
  it('drops unknown ids and duplicates, keeps every card', () => {
    const layout = normalizeLayout({ order: ['health', 'health', 'zzz'], hidden: ['zzz', 'queue'] })
    expect(layout.order[0]).toBe('health')
    expect([...layout.order].sort()).toEqual([...CARD_IDS].sort())
    expect(layout.hidden).toEqual(['queue'])
  })
  it('a preset shows its cards only', () => {
    expect(visibleCards(presetLayout('manager', null)).sort()).toEqual(['authorities', 'compliance', 'expiry', 'issuance'])
  })
})
