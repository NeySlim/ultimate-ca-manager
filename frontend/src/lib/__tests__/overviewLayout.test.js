/** Overview layout: the mockup's cards and presets, a stored preference stays readable, a card moves onto another. */
import { describe, it, expect } from 'vitest'
import {
  CARD_IDS, PRESETS, moveCard, normalizeLayout, presetActive, presetLayout, setCardHidden, visibleCards,
} from '../overviewLayout'

const SIX = ['queue', 'health', 'hierarchy', 'horizon', 'compliance', 'activity']

describe('stored layout', () => {
  it('the six cards of the mockup and the widgets of the study, two per line where they pair; its presets as its dashPresets', () => {
    expect(CARD_IDS).toEqual(['queue', 'health', 'issuance', 'horizon', 'compliance', 'revocation', 'hierarchy', 'activity', 'authorities'])
    for (const id of SIX) expect(CARD_IDS).toContain(id)
    expect(PRESETS.operator).toEqual(['queue', 'health', 'hierarchy', 'horizon'])
    expect(PRESETS.manager).toEqual(['compliance', 'horizon', 'hierarchy', 'activity'])
    expect(PRESETS.all).toEqual(CARD_IDS)
  })

  it('a layout saved before keeps its order and hidden cards; a card that is gone is dropped, a new one comes after', () => {
    const stored = { order: ['activity', 'states', 'queue', 'horizon', 'health', 'hierarchy', 'compliance'], hidden: ['health', 'states'], queueShowAll: true }
    const layout = normalizeLayout(stored)
    expect(layout.order).toEqual(['activity', 'queue', 'horizon', 'health', 'hierarchy', 'compliance', 'issuance', 'revocation', 'authorities'])
    expect(layout.hidden).toEqual(['health'])
    expect(layout.queueShowAll).toBe(true)
    expect(visibleCards(layout)).toEqual(['activity', 'queue', 'horizon', 'hierarchy', 'compliance', 'issuance', 'revocation', 'authorities'])
  })

  it('drops unknown and duplicate ids, and reads garbage as the default', () => {
    expect(normalizeLayout({ order: ['queue', 'nope', 'queue'], hidden: ['nope', 'queue', 'queue'] }))
      .toEqual({ order: ['queue', ...CARD_IDS.filter((c) => c !== 'queue')], hidden: ['queue'], queueShowAll: false })
    expect(normalizeLayout('x').order).toEqual(CARD_IDS)
  })

  it('every card of the six-card overview is still a card, and the presets name known cards only', () => {
    for (const id of SIX) expect(CARD_IDS).toContain(id)
    for (const cards of Object.values(PRESETS)) for (const id of cards) expect(CARD_IDS).toContain(id)
  })

  it('stays within what the server accepts: three keys, at most 20 short ids', () => {
    const layout = presetLayout('manager', normalizeLayout(null))
    expect(Object.keys(layout).sort()).toEqual(['hidden', 'order', 'queueShowAll'])
    expect(layout.order.length).toBeLessThanOrEqual(20)
    for (const id of layout.order) expect(id.length).toBeLessThanOrEqual(30)
  })
})

describe('presets', () => {
  it('a preset shows its cards in its order and is then the active one', () => {
    const layout = presetLayout('operator', normalizeLayout(null))
    expect(visibleCards(layout)).toEqual(PRESETS.operator)
    expect(presetActive('operator', layout)).toBe(true)
    expect(presetActive('manager', layout)).toBe(false)
    expect(presetActive('operator', moveCard(layout, 'health', 'queue'))).toBe(false)
  })

  it('keeps the fold state of the queue', () => {
    expect(presetLayout('manager', { queueShowAll: true }).queueShowAll).toBe(true)
  })
})

describe('moving a card', () => {
  const base = normalizeLayout({ order: ['a', ...SIX] })

  it('takes the place of the target, in either direction', () => {
    expect(moveCard(base, 'horizon', 'queue').order.slice(0, 4)).toEqual(['horizon', 'queue', 'health', 'hierarchy'])
    expect(moveCard(base, 'queue', 'horizon').order.slice(0, 4)).toEqual(['health', 'hierarchy', 'horizon', 'queue'])
  })

  it('leaves the layout as it is for itself or an unknown card', () => {
    expect(moveCard(base, 'queue', 'queue')).toBe(base)
    expect(moveCard(base, 'queue', 'nope')).toBe(base)
  })

  it('hides and shows a card without touching the order', () => {
    const hidden = setCardHidden(base, 'queue', true)
    expect(hidden.hidden).toEqual(['queue'])
    expect(hidden.order).toEqual(base.order)
    expect(setCardHidden(setCardHidden(hidden, 'queue', true), 'queue', false).hidden).toEqual([])
  })
})
