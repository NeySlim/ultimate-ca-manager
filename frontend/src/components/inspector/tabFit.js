/**
 * Open-object strip: tabs keep their width while they all fit, else share it down
 * to a minimum; those beyond go into a « +N » menu, the active one always shown.
 */
// Width of the « +N » button the strip gives up when it overflows
export const MORE_W = 52

/** How many tabs fit in `avail` px at `min` px each: Infinity when all do or nothing is measured yet. */
export function tabsThatFit(avail, min, count) {
  if (!(avail > 0) || !(min > 0) || count * min <= avail) return Infinity
  return Math.max(1, Math.floor((avail - MORE_W) / min))
}

/** The keys shown in the strip and those left to the menu; the active key takes the last slot if needed. */
export function splitTabs(keys, activeKey, fit) {
  if (keys.length <= fit) return { shown: keys, hidden: [] }
  const slots = Math.max(1, fit)
  let shown = keys.slice(0, slots)
  if (activeKey != null && keys.includes(activeKey) && !shown.includes(activeKey)) {
    shown = [...shown.slice(0, slots - 1), activeKey]
  }
  return { shown, hidden: keys.filter((k) => !shown.includes(k)) }
}

/**
 * A row of tabs of known widths (their gap included) in `avail` px: all of them when they fit, else the first
 * ones that fit beside a « More » button of `moreW` px, the active one always shown (in the last place if it
 * lies beyond). Unmeasured widths show everything.
 */
export function splitByWidth(keys, widths, activeKey, avail, moreW) {
  const w = (k) => widths[k] || 0
  if (!(avail > 0) || keys.some((k) => !(w(k) > 0)) || keys.reduce((s, k) => s + w(k), 0) <= avail) return { shown: keys, hidden: [] }
  const active = keys.includes(activeKey) ? activeKey : null
  const room = avail - moreW
  const shown = new Set()
  let used = 0
  for (const k of keys) {
    const reserve = active !== null && !shown.has(active) && k !== active ? w(active) : 0
    if (used + w(k) + reserve > room) break
    shown.add(k)
    used += w(k)
  }
  if (active !== null) shown.add(active)
  return { shown: keys.filter((k) => shown.has(k)), hidden: keys.filter((k) => !shown.has(k)) }
}
