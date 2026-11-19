/** Geometry of the overview's hand-written SVG charts. */

/** A smooth path through the points that never overshoots them (monotone cubic, Fritsch-Carlson). */
export function monotonePath(points) {
  const n = points.length
  if (n === 0) return ''
  const f = (v) => Number(v.toFixed(2))
  if (n === 1) return `M${f(points[0][0])},${f(points[0][1])}`
  const dx = []
  const slope = []
  for (let i = 0; i < n - 1; i += 1) {
    dx.push(points[i + 1][0] - points[i][0])
    slope.push((points[i + 1][1] - points[i][1]) / dx[i])
  }
  const m = [slope[0]]
  for (let i = 1; i < n - 1; i += 1) m.push(slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2)
  m.push(slope[n - 2])
  for (let i = 0; i < n - 1; i += 1) {
    if (slope[i] === 0) { m[i] = 0; m[i + 1] = 0; continue }
    const a = m[i] / slope[i]
    const b = m[i + 1] / slope[i]
    const s = a * a + b * b
    if (s > 9) {
      const k = 3 / Math.sqrt(s)
      m[i] = k * a * slope[i]
      m[i + 1] = k * b * slope[i]
    }
  }
  let d = `M${f(points[0][0])},${f(points[0][1])}`
  for (let i = 0; i < n - 1; i += 1) {
    const [x0, y0] = points[i]
    const [x1, y1] = points[i + 1]
    d += `C${f(x0 + dx[i] / 3)},${f(y0 + (m[i] * dx[i]) / 3)} ${f(x1 - dx[i] / 3)},${f(y1 - (m[i + 1] * dx[i]) / 3)} ${f(x1)},${f(y1)}`
  }
  return d
}

/** The axis top for a largest value: a round even figure at or above it, never under 4, so the middle tick is whole. */
export function niceMax(value) {
  const v = Math.max(4, Math.ceil(value))
  const step = 10 ** Math.floor(Math.log10(v))
  for (const k of [1, 2, 4, 6, 8, 10]) if (k * step >= v && (k * step) % 2 === 0) return k * step
  return 10 * step
}

/** Up to `count` indexes spread over 0..n-1, first and last included. */
export function tickIndexes(n, count = 5) {
  if (n <= count) return Array.from({ length: n }, (_, i) => i)
  return [...new Set(Array.from({ length: count }, (_, i) => Math.round((i * (n - 1)) / (count - 1))))]
}

/**
 * Donut slices as stroke dashes on a circle of circumference `c`: each {key, value, length, offset},
 * a `gap` of bare ring between two slices, nothing for a zero.
 */
export function donutSlices(parts, c, gap = 2) {
  const total = parts.reduce((sum, p) => sum + Math.max(0, p.value), 0)
  if (total <= 0) return []
  const drawn = parts.filter((p) => p.value > 0)
  const room = drawn.length > 1 ? gap : 0
  let at = 0
  return drawn.map((p) => {
    const full = (p.value / total) * c
    const slice = { key: p.key, value: p.value, length: Math.max(1, full - room), offset: at + room / 2 }
    at += full
    return slice
  })
}
