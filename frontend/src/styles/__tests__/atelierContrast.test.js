/**
 * Contrast of the four palettes of tokens.css, on the pairs that tire the eye when they are weak:
 * body text 7:1 and muted text 4.5:1 on every surface they sit on (page, panel, table header and
 * dock tabs on raised, hovered and selected rows), control borders and state colours 3:1 (WCAG 1.4.11).
 * Atelier draws its surface hierarchy by luminance alone, Aurore by gradient borders and glows.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { parseTokens, contrast, hexToRgb, rgbToHex, splitArgs, FAMILIES, MODES } from '../../lib/__tests__/themeTokensParser'
import { parseRules, declarations } from './atelierCopy'

const tokens = parseTokens()
const SURFACES = ['bg', 'panel', 'raised', 'hover', 'selected']

const PAIRS = [
  ...SURFACES.map((s) => ['text', s, 7]),
  ...SURFACES.map((s) => ['muted', s, 4.5]),
  ...['bg', 'panel', 'raised', 'hover'].map((s) => ['control', s, 3]),
  ...['accent', 'good', 'warn', 'bad', 'warn-fill'].flatMap((c) => ['bg', 'panel', 'raised'].map((s) => [c, s, 3])),
  // the active tab and the current menu item write the accent on the selection
  ['accent', 'selected', 4.5],
  ['good', 'goodbg', 4.5], ['warn', 'warnbg', 4.5], ['bad', 'badbg', 4.5],
]

// Atelier only: its surfaces stand apart by luminance, its dividers show without weighing
const ATELIER_STEPS = [
  ['panel', 'bg', 1.15], ['raised', 'panel', 1.12], ['hover', 'panel', 1.2], ['selected', 'panel', 1.3],
  ['line', 'panel', 1.7], ['line', 'raised', 1.4],
]

// Aurore's accents: the gradient's two ends under the active tabs (page, dock), the sorted column (raised header)
// and beside the open row (selected), 3:1; the module icons tinted by family on every ground of the bar,
// the Modules menu and the palette, 3:1 (WCAG 1.4.11)
const AURORE_PAIRS = [
  ...['grad-a', 'grad-b'].flatMap((c) => ['bg', 'panel', 'raised', 'selected'].map((s) => [c, s, 3])),
  ...['pki', 'protocols', 'governance', 'admin'].flatMap((f) => SURFACES.map((s) => [`fam-${f}`, s, 3])),
]

// The key figures written in a gradient (maquette.css, --fig-a to --fig-b by tone): both ends on the card's ground
const read = (file) => fs.readFileSync(path.resolve(__dirname, file), 'utf8')
function figureGradients(mode) {
  const ends = {}
  for (const r of parseRules(read('../atelier/maquette.css'))) {
    const light = r.sel.startsWith(':root[data-theme="aurore"][data-mode="light"]')
    if (!(r.sel.startsWith(':root[data-theme|=aurore]') || (light && mode === 'light'))) continue
    for (const [prop, v] of declarations(r.body)) {
      if (prop !== '--fig-a' && prop !== '--fig-b') continue
      const tone = r.sel.match(/\.value\.(warn|bad|good)/)?.[1] || 'plain'
      ends[tone] = { ...ends[tone], [prop]: v }
    }
  }
  return ends
}

// The glow behind the console (shell.css): each of its three spots at full strength over the page; their
// centres lie outside one another's reach, so each peak is measured alone
function rgba(value, t) {
  const v = value.replace(/\s+/g, '')
  const mix = v.match(/^color-mix\(insrgb,var\(--([a-z-]+)\)([0-9.]+)%,transparent\)$/)
  if (mix) return { rgb: hexToRgb(t[mix[1]]), a: Number(mix[2]) / 100 }
  const m = v.match(/^rgba\((\d+),(\d+),(\d+),([0-9.]+)\)$/)
  if (m) return { rgb: m.slice(1, 4).map(Number), a: Number(m[4]) }
  const ref = v.match(/^var\(--([a-z-]+)\)$/)
  if (ref) return rgba(t[ref[1]], t)
  throw new Error(`unread glow: ${value}`)
}
function glowPeaks(t, mode) {
  const rules = parseRules(read('../../components/shell/shell.css')).filter((r) => !r.media && / body::before$/.test(r.sel))
  const rule = rules.filter((r) => mode === 'light' || !r.sel.includes('data-mode="light"')).filter((r) => /radial-gradient/.test(r.body)).pop()
  const spots = []
  for (let i = rule.body.indexOf('radial-gradient('); i >= 0; i = rule.body.indexOf('radial-gradient(', i + 1)) {
    let depth = 0
    let j = i + 'radial-gradient'.length
    for (; j < rule.body.length; j++) {
      if (rule.body[j] === '(') depth++
      if (rule.body[j] === ')' && --depth === 0) break
    }
    spots.push(splitArgs(rule.body.slice(i + 'radial-gradient('.length, j))[1])
  }
  expect(spots).toHaveLength(3)
  return spots.map((spot) => {
    const { rgb, a } = rgba(spot, t)
    return rgbToHex(hexToRgb(t.bg).map((b, i) => rgb[i] * a + b * (1 - a)))
  })
}

function saturation(hex) {
  const [r, g, b] = hexToRgb(hex).map((v) => v / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  return max === min ? 0 : (max - min) / (1 - Math.abs(2 * l - 1))
}

describe('contrast of the palettes', () => {
  for (const family of FAMILIES) {
    for (const mode of MODES) {
      const key = `${family}-${mode}`
      const t = tokens[key]
      describe(key, () => {
        for (const [fg, bg, min] of PAIRS) {
          it(`${fg} on ${bg} >= ${min}`, () => {
            expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(min)
          })
        }
        if (family === 'atelier') {
          for (const [fg, bg, min] of ATELIER_STEPS) {
            it(`${fg} against ${bg} >= ${min}`, () => {
              expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(min)
            })
          }
        }
        if (family === 'aurore') {
          for (const [fg, bg, min] of AURORE_PAIRS) {
            it(`${fg} on ${bg} >= ${min}`, () => {
              expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(min)
            })
          }
          it('writes each key figure in a gradient whose two ends hold 4.5:1 on the card, at rest and hovered', () => {
            const tones = figureGradients(mode)
            expect(Object.keys(tones).sort()).toEqual(['bad', 'good', 'plain', 'warn'])
            for (const [tone, ends] of Object.entries(tones)) {
              for (const end of [ends['--fig-a'] ?? tones.plain['--fig-a'], ends['--fig-b'] ?? tones.plain['--fig-b']]) {
                const ref = end.match(/^var\(--([a-z-]+)\)$/)
                const hex = ref ? t[ref[1]] : end
                for (const s of ['panel', 'hover']) expect(contrast(hex, t[s]), `${tone} ${end} on ${s}`).toBeGreaterThanOrEqual(4.5)
              }
            }
          })
          it('keeps text 7:1, muted text and the accent 4.5:1 where the glow peaks', () => {
            for (const peak of glowPeaks(t, mode)) {
              expect(contrast(t.text, peak), `text on ${peak}`).toBeGreaterThanOrEqual(7)
              expect(contrast(t.muted, peak), `muted on ${peak}`).toBeGreaterThanOrEqual(4.5)
              expect(contrast(t.accent, peak), `accent on ${peak}`).toBeGreaterThanOrEqual(4.5)
            }
          })
        }
        it('tints the page and the raised surfaces instead of a neutral grey', () => {
          for (const s of ['bg', 'raised']) expect(saturation(t[s]), s).toBeGreaterThanOrEqual(0.25)
        })
        if (mode === 'dark') {
          it('puts no pure white on pure black', () => {
            expect(t.text).not.toBe('#ffffff')
            for (const s of SURFACES) expect(t[s], s).not.toBe('#000000')
          })
        }
      })
    }
  }
})
