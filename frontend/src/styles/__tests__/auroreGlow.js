/**
 * Aurore's glow behind the console (components/shell/shell.css, body::before), read as the browser paints it:
 * each spot a radial gradient from its colour to transparent, sized and placed in percent of the layer, the
 * first spot on top. Shared by the contrast test (worst point of the field) and the accents test (the band).
 */
import fs from 'fs'
import path from 'path'
import { parseRules, declarations } from './atelierCopy'
import { hexToRgb, rgbToHex, splitArgs } from '../../lib/__tests__/themeTokensParser'

const SHELL = path.resolve(__dirname, '../../components/shell/shell.css')

/** `{ rgb, a }` of a colour written as rgba(), color-mix(in srgb, var(--x) N%, transparent), var(--x) or a hex. */
export function rgba(value, t) {
  const v = value.replace(/\s+/g, '')
  const mix = v.match(/^color-mix\(insrgb,var\(--([a-z-]+)\)([0-9.]+)%,transparent\)$/)
  if (mix) return { rgb: rgba(t[mix[1]], t).rgb, a: (Number(mix[2]) / 100) * rgba(t[mix[1]], t).a }
  const m = v.match(/^rgba\((\d+),(\d+),(\d+),([0-9.]+)\)$/)
  if (m) return { rgb: m.slice(1, 4).map(Number), a: Number(m[4]) }
  const ref = v.match(/^var\(--([a-z-]+)\)$/)
  if (ref) return rgba(t[ref[1]], t)
  if (/^#[0-9a-f]{6}$/i.test(v)) return { rgb: hexToRgb(v), a: 1 }
  throw new Error(`unread colour: ${value}`)
}

/** `top` laid over `under` (rgb arrays), straight alpha. */
export const over = ({ rgb, a }, under) => under.map((u, i) => rgb[i] * a + u * (1 - a))

/** The glow's rule for a mode: the light rule overrides the shared one's background. */
export function glowRule(mode) {
  const rules = parseRules(fs.readFileSync(SHELL, 'utf8')).filter((r) => !r.media && / body::before$/.test(r.sel))
  const base = rules.find((r) => !r.sel.includes('data-mode') && /radial-gradient/.test(r.body))
  const light = rules.find((r) => r.sel.includes('[data-mode="light"]') && /radial-gradient/.test(r.body))
  const decls = Object.fromEntries(declarations(base.body))
  if (mode === 'light' && light) Object.assign(decls, Object.fromEntries(declarations(light.body)))
  return decls
}

/** The spots of the glow, each `radial-gradient(<rx>% <ry>% at <x>% <y>%, <colour>, transparent <stop>%)`. */
export function glowSpots(t, mode) {
  const bg = glowRule(mode).background
  const spots = []
  for (let i = bg.indexOf('radial-gradient('); i >= 0; i = bg.indexOf('radial-gradient(', i + 1)) {
    let depth = 0
    let j = i + 'radial-gradient'.length
    for (; j < bg.length; j++) {
      if (bg[j] === '(') depth++
      if (bg[j] === ')' && --depth === 0) break
    }
    const [shape, colour, end] = splitArgs(bg.slice(i + 'radial-gradient('.length, j))
    const g = shape.match(/^([0-9.]+)% ([0-9.]+)% at ([0-9.]+)% ([0-9.]+)%$/)
    const s = end.match(/^transparent ([0-9.]+)%$/)
    if (!g || !s) throw new Error(`spot not in percent of the layer: ${shape}, ${end}`)
    const [rx, ry, x, y] = g.slice(1).map(Number)
    spots.push({ rx, ry, x, y, stop: Number(s[1]) / 100, ...rgba(colour, t) })
  }
  return spots
}

/** The page's colour at a point of the layer (percent of its box), the spots over --bg, the first on top. */
export function glowAt(spots, bg, bx, by) {
  let c = hexToRgb(bg)
  for (const s of [...spots].reverse()) {
    const d = Math.hypot((bx - s.x) / s.rx, (by - s.y) / s.ry)
    c = over({ rgb: s.rgb, a: s.a * Math.max(0, 1 - d / s.stop) }, c)
  }
  return c
}

/** Every point of the layer, one per percent each way: the colours the page can show behind a surface. */
export function glowField(t, mode) {
  const spots = glowSpots(t, mode)
  const out = []
  for (let by = 0; by <= 100; by++) for (let bx = 0; bx <= 100; bx++) out.push(glowAt(spots, t.bg, bx, by))
  return out
}

/** The layer's inset, in percent of the viewport (`inset: -12%`): maps a viewport point to the layer's box. */
export function viewportToLayer(mode) {
  const inset = glowRule(mode).inset.match(/^-([0-9.]+)%$/)
  const k = Number(inset[1])
  return (v) => ((v + k) / (100 + 2 * k)) * 100
}

export const hex = (rgb) => rgbToHex(rgb)
