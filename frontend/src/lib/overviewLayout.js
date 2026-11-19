/** Overview card layout: default order, presets, and the stored preference (`dashboard` key). */
export const CARD_IDS = ['queue', 'health', 'hierarchy', 'horizon', 'trend', 'states', 'compliance', 'activity']
export const PRESETS = {
  operator: ['queue', 'health', 'hierarchy', 'horizon'],
  manager: ['compliance', 'states', 'trend', 'horizon', 'hierarchy', 'activity'],
  all: CARD_IDS,
}

/** A stored value reduced to known ids: no duplicate, no unknown id, every card kept in the order. */
export function normalizeLayout(pref) {
  const known = new Set(CARD_IDS)
  const list = (v) => (Array.isArray(v) ? v.filter((id) => known.has(id)) : [])
  const order = [...new Set(list(pref?.order))]
  for (const id of CARD_IDS) if (!order.includes(id)) order.push(id)
  return { order, hidden: [...new Set(list(pref?.hidden))], queueShowAll: pref?.queueShowAll === true }
}

export function presetLayout(name, current) {
  const cards = PRESETS[name]
  if (!cards) return normalizeLayout(current)
  return normalizeLayout({
    order: cards, hidden: CARD_IDS.filter((id) => !cards.includes(id)), queueShowAll: current?.queueShowAll,
  })
}

export const visibleCards = (layout) => layout.order.filter((id) => !layout.hidden.includes(id))

/** True when the cards shown are exactly the preset's, in its order. */
export function presetActive(name, layout) {
  const cards = PRESETS[name] || []
  const shown = visibleCards(layout)
  return shown.length === cards.length && shown.every((id, i) => id === cards[i])
}

/** The card takes the place of `target` in the order; the cards between shift by one. */
export function moveCard(layout, id, target) {
  const from = layout.order.indexOf(id)
  const to = layout.order.indexOf(target)
  if (from < 0 || to < 0 || from === to) return layout
  const order = layout.order.filter((c) => c !== id)
  order.splice(to, 0, id)
  return { ...layout, order }
}

/** One step among the cards shown (hidden ones are skipped); unchanged at either end. */
export function stepCard(layout, id, delta) {
  const shown = visibleCards(layout)
  const target = shown[shown.indexOf(id) + delta]
  return shown.includes(id) && target ? moveCard(layout, id, target) : layout
}

export function setCardHidden(layout, id, hidden) {
  const rest = layout.hidden.filter((c) => c !== id)
  return { ...layout, hidden: hidden ? [...rest, id] : rest }
}
