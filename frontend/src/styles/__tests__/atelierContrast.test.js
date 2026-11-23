/**
 * Contrast of the four palettes of tokens.css, on the pairs that tire the eye when they are weak:
 * body text 7:1 and muted text 4.5:1 on every surface they sit on (page, panel, table header and
 * dock tabs on raised, hovered and selected rows), control borders and state colours 3:1 (WCAG 1.4.11).
 * Atelier draws its surface hierarchy by luminance alone, Aurore by gradient borders and glows.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { parseTokens, contrast, resolve, hexToRgb, FAMILIES, MODES } from '../../lib/__tests__/themeTokensParser'
import { parseRules, splitSelectors, declarations } from './atelierCopy'
import { glowField, rgba, over, hex } from './auroreGlow'

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
  // the avatar's initials on its gradient
  ['on-accent', 'grad-a', 4.5], ['on-accent', 'grad-b', 4.5],
]

// Aurore's rules of the console: the mockup's block (maquette.css), then the product's (adjust.css), which outranks it
const read = (file) => fs.readFileSync(path.resolve(__dirname, file), 'utf8')
const MAQUETTE = parseRules(read('../atelier/maquette.css'))
const ADJUST = parseRules(read('../atelier/adjust.css'))
const DETACHED = parseRules(read('../atelier/detached.css'))
function auroreRules(rules, mode) {
  return rules.flatMap((r) => splitSelectors(r.sel).map((sel) => ({ ...r, sel }))).filter((r) => {
    if (r.media || !/^:root\[data-theme(\|=aurore|="aurore")\]/.test(r.sel)) return false
    const m = r.sel.match(/^:root\S*\[data-mode="(\w+)"\]/)
    return !m || m[1] === mode
  })
}
const valuesOf = (rules, re, prop) => rules.filter((r) => re.test(r.sel)).flatMap((r) => declarations(r.body))
  .filter(([p]) => p === prop).map(([, v]) => v.replace(/\s+/g, ' '))

// The key figures written in a gradient (--fig-a to --fig-b by tone): the mockup's, then the product's
function figureGradients(mode) {
  const ends = {}
  for (const r of [...auroreRules(MAQUETTE, mode), ...auroreRules(ADJUST, mode)]) {
    for (const [prop, v] of declarations(r.body)) {
      if (prop !== '--fig-a' && prop !== '--fig-b') continue
      const tone = r.sel.match(/\.value\.(warn|bad|good)/)?.[1] || 'plain'
      ends[tone] = { ...ends[tone], [prop]: v }
    }
  }
  return ends
}

// The glass surfaces Aurore lays over its glow (adjust.css): a surface token mixed with transparent
const GLASS = /^color-mix\(in srgb,\s*var\(--(bg|panel|raised|hover|selected)\) ([0-9.]+)%,\s*transparent\)$/
function glassSurfaces(mode) {
  // the light rules come after the shared ones: the last value for an element and a property holds
  const out = new Map()
  for (const r of auroreRules(ADJUST, mode)) {
    for (const [prop, v] of declarations(r.body)) {
      if (['--surf', 'background', 'background-color'].includes(prop)) out.set(`${r.sel.replace(/^:root\S*/, '')}|${prop}`, { sel: r.sel, value: v })
    }
  }
  return [...out.values()].filter((g) => GLASS.test(g.value))
}
// Every colour a glass surface can take over the glow, one per point of the layer
const glassOver = (field, value, t) => field.map((g) => over(rgba(value, t), g))
const worst = (fg, colours) => Math.min(...colours.map((c) => contrast(fg, hex(c))))

// color-mix(in srgb, a p, b): each channel weighted in sRGB (a transparent veil is read over the panel)
function mixHex(a, b, p) {
  const [x, y] = [hexToRgb(a), hexToRgb(b)]
  return `#${x.map((v, i) => Math.round(v * p + y[i] * (1 - p)).toString(16).padStart(2, '0')).join('')}`
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
          it('writes a technical value and a row\'s action 7:1, muted text 4.5:1, on their veil of the accent', () => {
            const veils = ['.code-value', '.btn-sm'].flatMap((cls) => valuesOf(auroreRules(ADJUST, mode), new RegExp(`\\${cls}$`), 'background'))
            expect(veils).toHaveLength(2)
            for (const veil of veils) {
              const m = veil.match(/^color-mix\(in srgb,\s*var\(--accent\) ([0-9.]+)%,\s*(?:var\(--panel\)|transparent)\)$/)
              expect(m, veil).not.toBeNull()
              const ground = mixHex(t.accent, t.panel, Number(m[1]) / 100)
              expect(contrast(t.text, ground)).toBeGreaterThanOrEqual(7)
              expect(contrast(t.muted, ground)).toBeGreaterThanOrEqual(4.5)
            }
          })
          // read on first use: a spot the field cannot read fails its tests, not the file
          let fieldCache
          const lazy = { get field() { return (fieldCache ??= glowField(t, mode)) } }
          const glass = glassSurfaces(mode)
          it('writes each key figure in a gradient whose two ends hold 4.5:1 on the card, at rest and hovered, and on the page', () => {
            const tones = figureGradients(mode)
            expect(Object.keys(tones).sort()).toEqual(['bad', 'good', 'plain', 'warn'])
            const grounds = [...['panel', 'hover'].map((s) => [hexToRgb(t[s])]), lazy.field, ...glass.map((g) => glassOver(lazy.field, g.value, t))]
            for (const [tone, ends] of Object.entries(tones)) {
              for (const end of [ends['--fig-a'] ?? tones.plain['--fig-a'], ends['--fig-b'] ?? tones.plain['--fig-b']]) {
                const fg = resolve(end, t)
                for (const g of grounds) expect(worst(fg, g), `${tone} ${end}`).toBeGreaterThanOrEqual(4.5)
              }
            }
          })
          it('keeps text 7:1, muted text and the accent 4.5:1 at the worst point of the glow', () => {
            expect(worst(t.text, lazy.field)).toBeGreaterThanOrEqual(7)
            expect(worst(t.muted, lazy.field)).toBeGreaterThanOrEqual(4.5)
            expect(worst(t.accent, lazy.field)).toBeGreaterThanOrEqual(4.5)
          })
          it('keeps text 7:1 and muted text 4.5:1 on each glass surface, over the worst point of the glow', () => {
            // the panels, the table, the dock and the bars, at rest and hovered
            expect(glass.map((g) => g.sel).join(' ')).toMatch(/\.panel/)
            expect(glass.map((g) => g.sel).join(' ')).toMatch(/\.masthead/)
            for (const g of glass) {
              const seen = glassOver(lazy.field, g.value, t)
              expect(worst(t.text, seen), `text on ${g.sel}`).toBeGreaterThanOrEqual(7)
              expect(worst(t.muted, seen), `muted on ${g.sel}`).toBeGreaterThanOrEqual(4.5)
            }
          })
          it('keeps text 7:1 and muted text 4.5:1 on a hovered row of a glass table, its tint over the glow', () => {
            const tints = auroreRules(ADJUST, mode).filter((r) => /tbody tr:not\(\.opened\):not\(\.checked\):hover$/.test(r.sel))
              .flatMap((r) => declarations(r.body)).filter(([p]) => p === 'background')
              .map(([, v]) => v.match(/^linear-gradient\(90deg,(color-mix\(.*?,transparent\)),transparent [0-9]+%\)$/)?.[1])
            expect(tints.length).toBeGreaterThan(0)
            const table = glass.filter((g) => /\.table-container/.test(g.sel))
            expect(table.length).toBeGreaterThan(0)
            for (const tint of tints) {
              for (const g of table) {
                const seen = glassOver(lazy.field, g.value, t).map((c) => over(rgba(tint, t), c))
                expect(worst(t.text, seen), tint).toBeGreaterThanOrEqual(7)
                expect(worst(t.muted, seen), tint).toBeGreaterThanOrEqual(4.5)
              }
            }
          })
          it('keeps text 7:1 and muted text 4.5:1 on the open row, at both ends of its tint', () => {
            const open = valuesOf(auroreRules(ADJUST, mode), /tbody tr\.opened$/, 'background').pop()
            const m = open.match(/^linear-gradient\(90deg, ?(color-mix\(.*\)), ?var\(--selected\) [0-9]+%\)$/)
            expect(m, open).not.toBeNull()
            for (const ground of [resolve(m[1], t), t.selected]) {
              expect(contrast(t.text, ground)).toBeGreaterThanOrEqual(7)
              expect(contrast(t.muted, ground)).toBeGreaterThanOrEqual(4.5)
              expect(contrast(t.accent, ground)).toBeGreaterThanOrEqual(4.5)
            }
          })
          // pills sit in the panels, the table, the dock and the bars; the tab counters on the page mix with --bg (opaque)
          it('writes the state pills 4.5:1 on their own tint, over each glass surface', () => {
            const tints = valuesOf(auroreRules(ADJUST, mode), /:is\(\.chip:not\(\.filter-chip\),\.badge,\.counter,\.queue-kind\)$/, 'background')
            expect(tints.length).toBeGreaterThan(0)
            const p = Number(tints.pop().match(/^color-mix\(in srgb, ?currentColor ([0-9.]+)%, ?transparent\)$/)[1]) / 100
            const grounds = glass.map((g) => glassOver(lazy.field, g.value, t))
            for (const tone of ['accent', 'good', 'warn', 'bad']) {
              for (const g of grounds) {
                expect(worst(t[tone], g.map((c) => over({ rgb: hexToRgb(t[tone]), a: p }, c))), tone).toBeGreaterThanOrEqual(4.5)
              }
            }
          })
          // a pill or a count on the selection (a checked or open row, the chain's box, the pressed queue chip)
          it('writes a pill or a count 4.5:1 on its tint over the selection ground', () => {
            const tints = valuesOf(auroreRules(ADJUST, mode), /:is\(tr\.checked,tr\.opened,\.chain-box,\.queue-chip\[aria-pressed=true\]\) :is\(\.badge,\.counter\)$/, 'background')
            const shared = valuesOf(auroreRules(ADJUST, mode), /:is\(\.chip:not\(\.filter-chip\),\.badge,\.counter,\.queue-kind\)$/, 'background')
            const value = (tints.length ? tints : shared).pop()
            const p = Number(value.match(/^color-mix\(in srgb, ?currentColor ([0-9.]+)%, ?transparent\)$/)[1]) / 100
            for (const tone of ['accent', 'good', 'warn', 'bad']) {
              const ground = over({ rgb: hexToRgb(t[tone]), a: p }, hexToRgb(t.selected))
              expect(contrast(t[tone], hex(ground)), tone).toBeGreaterThanOrEqual(4.5)
            }
          })
          it('writes the brand word in one colour that holds 3:1 (large text) on the bar\'s glass', () => {
            const brand = auroreRules(ADJUST, mode).filter((r) => /\.brand strong$/.test(r.sel)).flatMap((r) => declarations(r.body))
            expect(brand.some(([p, v]) => /^background/.test(p) && /gradient/.test(v))).toBe(false)
            const colour = brand.filter(([p]) => p === 'color').map(([, v]) => v).pop()
            const ref = /^var\(--([a-z-]+)\)$/.exec(colour)
            expect(ref).not.toBeNull()
            const bar = glass.filter((g) => /\.masthead/.test(g.sel)).map((g) => glassOver(lazy.field, g.value, t))
            expect(bar.length).toBeGreaterThan(0)
            for (const g of bar) expect(worst(t[ref[1]], g), ref[1]).toBeGreaterThanOrEqual(3)
          })
        }
        // the comparison: a line that differs on a light ground, its shared list elements muted, "+" in the accent
        it('keeps text 7:1, muted text 4.5:1 and the accent 3:1 on a differing line of the comparison', () => {
          const ground = valuesOf(DETACHED, /\.compare-view \.compare-table tr\.different td$/, 'background').pop()
          expect(ground).toMatch(/^color-mix\(/)
          const g = resolve(ground, t)
          expect(contrast(t.text, g)).toBeGreaterThanOrEqual(7)
          expect(contrast(t.muted, g)).toBeGreaterThanOrEqual(4.5)
          expect(contrast(t.accent, g)).toBeGreaterThanOrEqual(3)
        })
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
