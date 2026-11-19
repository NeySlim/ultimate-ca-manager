/** Overview layout: a preference stored before a card existed stays readable, and a card moves by one place or onto another. */
import { describe, it, expect } from 'vitest'
import {
  CARD_IDS, PRESETS, moveCard, normalizeLayout, presetActive, presetLayout, setCardHidden, stepCard, visibleCards,
} from '../overviewLayout'

const SIX = ['queue', 'health', 'hierarchy', 'horizon', 'compliance', 'activity']

describe('stored layout', () => {
  it('a layout saved with six cards keeps its order and hidden cards, the new cards come after', () => {
    const stored = { order: ['activity', 'queue', 'horizon', 'health', 'hierarchy', 'compliance'], hidden: ['health'], queueShowAll: true }
    const layout = normalizeLayout(stored)
    expect(layout.order.slice(0, 6)).toEqual(stored.order)
    expect(layout.order.slice(6).sort()).toEqual(['states', 'trend'])
    expect(layout.hidden).toEqual(['health'])
    expect(layout.queueShowAll).toBe(true)
    expect(visibleCards(layout)).toEqual(['activity', 'queue', 'horizon', 'hierarchy', 'compliance', 'trend', 'states'])
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

  it('one step skips the hidden cards and stops at both ends', () => {
    const layout = setCardHidden(base, 'health', true)
    expect(visibleCards(stepCard(layout, 'queue', 1)).slice(0, 2)).toEqual(['hierarchy', 'queue'])
    expect(stepCard(layout, 'queue', -1)).toBe(layout)
    const last = visibleCards(layout).at(-1)
    expect(stepCard(layout, last, 1)).toBe(layout)
    expect(stepCard(layout, 'health', 1)).toBe(layout)
  })

  it('hides and shows a card without touching the order', () => {
    const hidden = setCardHidden(base, 'queue', true)
    expect(hidden.hidden).toEqual(['queue'])
    expect(hidden.order).toEqual(base.order)
    expect(setCardHidden(setCardHidden(hidden, 'queue', true), 'queue', false).hidden).toEqual([])
  })
})
