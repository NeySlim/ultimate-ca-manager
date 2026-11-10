/** Overview card layout: default order, presets, and the stored preference (`dashboard` key). */
export const CARD_IDS = ['queue', 'health', 'hierarchy', 'horizon', 'compliance', 'activity']
export const PRESETS = {
  operator: ['queue', 'health', 'hierarchy', 'horizon'],
  manager: ['compliance', 'horizon', 'hierarchy', 'activity'],
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
