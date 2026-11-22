/** Overview card layout: default order, presets, and the stored preference (`dashboard` key). */
// The mockup's cards (dashCards) and the widgets of the overview study, two per line where they pair
export const CARD_IDS = ['queue', 'health', 'issuance', 'horizon', 'compliance', 'revocation', 'hierarchy', 'activity', 'authorities']
// A card renamed since: a stored layout keeps its place and its visibility under the new id
const RENAMED = { trend: 'issuance' }
export const PRESETS = {
  operator: ['queue', 'health', 'hierarchy', 'horizon'],
  manager: ['compliance', 'horizon', 'hierarchy', 'activity'],
  all: CARD_IDS,
}

/** A stored value reduced to known ids: no duplicate, no unknown id, every card kept in the order. */
export function normalizeLayout(pref) {
  const known = new Set(CARD_IDS)
  const list = (v) => (Array.isArray(v) ? v.map((id) => RENAMED[id] || id).filter((id) => known.has(id)) : [])
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

export function setCardHidden(layout, id, hidden) {
  const rest = layout.hidden.filter((c) => c !== id)
  return { ...layout, hidden: hidden ? [...rest, id] : rest }
}
