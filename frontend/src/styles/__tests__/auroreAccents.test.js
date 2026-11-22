/**
 * Aurore set apart from Atelier (styles/atelier/adjust.css, components/shell/shell.css): Atelier stays flat and
 * only tints its state pills, on the pill box Aurore draws, so that a change of theme moves nothing; Aurore
 * underlines the active tabs and the sorted column with its gradient, edges the open row, adds a glow to the
 * focus ring, tints the module icons by family and eases its hovers. The geometry and the focus glow are
 * measured in a browser (e2e/theme-geometry.spec.ts); the contrast of each new pair in atelierContrast.test.js.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { parseRules, splitSelectors, declarations } from './atelierCopy'
import { GROUPS } from '../../navigation/registry'

const read = (file) => fs.readFileSync(path.resolve(__dirname, file), 'utf8')
const ADJUST = parseRules(read('../atelier/adjust.css'))
const MAQUETTE = parseRules(read('../atelier/maquette.css'))
const SHELL = parseRules(read('../../components/shell/shell.css'))
const PALETTES = [['atelier', 'dark'], ['atelier', 'light'], ['aurore', 'dark'], ['aurore', 'light']]

// Whether the theme root a selector starts with holds for a palette (a bare :root holds for all four)
function applies(sel, family, mode) {
  const root = sel.match(/^:root((?:\[[^\]]+\]|:not\([^)]*\))*)/)
  if (!root) return false
  const quals = root[1]
  const aurore = family === 'aurore'
  if (/:not\(\[data-theme\|=aurore\]\)/.test(quals) && aurore) return false
  if (/^\[data-theme\|=aurore\]|\[data-theme="aurore"\]/.test(quals) && !aurore) return false
  const m = quals.match(/\[data-mode="(\w+)"\]/)
  return !m || m[1] === mode
}
const rulesFor = (family, mode, rules = ADJUST) => rules.flatMap((r) => splitSelectors(r.sel)
  .filter((s) => applies(s, family, mode)).map((sel) => ({ sel, decls: declarations(r.body), media: r.media })))
const matching = (family, mode, re) => rulesFor(family, mode).filter((r) => re.test(r.sel))
// The value a property ends with across the matching rules, in source order (one specificity per test)
const value = (rules, prop) => rules.flatMap((r) => r.decls).filter(([p]) => p === prop).map(([, v]) => v).pop()
const GRADIENT = 'linear-gradient(90deg,var(--grad-a),var(--grad-b))'

describe('Aurore set apart from Atelier', () => {
  for (const [family, mode] of PALETTES) {
    const aurore = family === 'aurore'
    describe(`${family}-${mode}`, () => {
      it(aurore ? 'underlines the active page and protocol tab with the gradient, on the tab\'s own rule' : 'keeps the plain accent rule under the active tab', () => {
        const tab = matching(family, mode, /\.view-btn\.active$/)
        if (!aurore) return expect(tab).toEqual([])
        expect(value(tab, 'border-bottom-color')).toBe('transparent')
        // border-box: the gradient takes the 2 px of the transparent border, where the accent rule was drawn
        expect(value(tab, 'background')).toBe(`${GRADIENT} left bottom/100% 2px no-repeat border-box`)
        expect(value(tab, 'box-shadow')).toBe(mode === 'dark' ? '0 10px 14px -12px var(--grad-b)' : 'none')
      })

      it(aurore ? 'underlines the sorted column with the gradient, over the header\'s raised ground' : 'leaves the sorted column to its weight and colour', () => {
        const sorted = matching(family, mode, /th:is\(\[aria-sort=ascending\],\[aria-sort=descending\]\)$/)
          .filter((r) => r.decls.some(([p]) => p.startsWith('background')))
        if (!aurore) return expect(sorted).toEqual([])
        expect(value(sorted, 'background-image')).toBe(GRADIENT)
        expect(value(sorted, 'background-size')).toBe('100% 2px')
        expect(value(sorted, 'background-position')).toBe('left bottom')
        expect(value(sorted, 'background-repeat')).toBe('no-repeat')
        // the colour stays the header's: the raised ground of the row shows through
        expect(value(sorted, 'background')).toBeUndefined()
        expect(value(sorted, 'background-color')).toBeUndefined()
      })

      it(aurore ? 'edges the open work row with the gradient, as the open table row' : 'keeps the accent edge of the open work row', () => {
        const row = matching(family, mode, /\.work-row\.opened$/)
        if (!aurore) return expect(row).toEqual([])
        expect(value(row, 'box-shadow')).toBe('none')
        expect(value(row, 'background')).toBe('linear-gradient(180deg,var(--grad-a),var(--grad-b)) left/2px 100% no-repeat,var(--selected)')
        // the open table row's edge is the mockup's own (maquette.css)
        expect(MAQUETTE.some((r) => /tbody tr\.opened td:first-child:before$/.test(r.sel) && r.body.includes('linear-gradient(180deg,var(--grad-a),var(--grad-b))'))).toBe(true)
      })

      it(aurore ? 'adds a --glow to the focus ring and keeps the outline' : 'draws the focus ring without a glow', () => {
        const focus = matching(family, mode, /:focus-visible:not\(\[aria-invalid=true\]\)$/)
        if (!aurore) return expect(focus).toEqual([])
        const shadow = value(focus, 'box-shadow')
        expect(shadow).toMatch(/^0 0 0 [45]px var\(--halo\),0 0 \d+px \d+px var\(--glow\)$/)
        expect(value(focus, 'outline')).toBeUndefined()
        // no harsh glow on a light ground
        expect(Number(shadow.match(/0 0 (\d+)px \d+px var\(--glow\)/)[1])).toBeLessThanOrEqual(mode === 'dark' ? 18 : 10)
      })

      it(aurore ? 'tints the module icons by family in the bar, the Modules menu and the palette' : 'leaves the module icons untinted', () => {
        const families = matching(family, mode, /\[data-family=\w+\]$/)
        if (!aurore) return expect(families).toEqual([])
        expect(families.map((r) => r.sel.match(/\[data-family=(\w+)\]$/)[1]).sort()).toEqual(GROUPS.map((g) => g.id).sort())
        for (const r of families) expect(value([r], '--fam')).toBe(`var(--fam-${r.sel.match(/\[data-family=(\w+)\]$/)[1]})`)
        const icons = matching(family, mode, /\[data-family\]>\.icon$/)
        expect(icons.map((r) => r.sel.replace(/^:root\[data-theme\|=aurore\] \.atl /, ''))).toEqual(
          expect.arrayContaining(['.main-nav a[data-family]>.icon', '.menu-item a[data-family]>.icon', '.command-result[data-family]>.icon']))
        for (const r of icons) expect(value([r], 'color')).toBe('var(--fam)')
      })

      it(aurore ? 'eases its hovers in 120 to 180 ms' : 'adds no transition', () => {
        const eased = rulesFor(family, mode).filter((r) => r.decls.some(([p]) => p === 'transition'))
        if (!aurore) return expect(eased).toEqual([])
        expect(eased.length).toBeGreaterThan(0)
        for (const r of eased) {
          const times = [...value([r], 'transition').matchAll(/(\d*\.?\d+)(m?s)\b/g)].map(([, n, u]) => (u === 's' ? Number(n) * 1000 : Number(n)))
          expect(times.length, r.sel).toBeGreaterThan(0)
          for (const ms of times) expect(ms, r.sel).toBeGreaterThanOrEqual(120)
          for (const ms of times) expect(ms, r.sel).toBeLessThanOrEqual(180)
        }
      })

      it(aurore ? 'draws its own pills (the mockup\'s Aurore block)' : 'tints the state pills, on the box of Aurore\'s pills', () => {
        const pills = matching(family, mode, /\.badge\.(good|warn|bad)$/)
        if (aurore) return expect(pills).toEqual([])
        for (const tone of ['good', 'warn', 'bad']) {
          expect(value(matching(family, mode, new RegExp(`\\.badge\\.${tone}$`)), 'background-color'), tone).toBe(`var(--${tone}bg)`)
        }
        // Aurore's pill box (maquette.css): Atelier takes it, so the badge, the counter and the chip measure the same
        const auroreBox = (re) => MAQUETTE.filter((r) => r.sel.startsWith(':root[data-theme|=aurore] .atl') && re.test(r.sel))
          .flatMap((r) => declarations(r.body))
        const box = (re) => matching(family, mode, re).flatMap((r) => r.decls)
        const get = (decls, p) => decls.filter(([k]) => k === p).map(([, v]) => v).pop()
        expect(get(box(/ \.badge$/), 'padding')).toBe(get(auroreBox(/ \.badge$/), 'padding'))
        expect(get(box(/ \.badge$/), 'border')).toBe('1px solid transparent')
        expect(get(box(/ \.counter$/), 'padding')).toBe(get(auroreBox(/ \.counter$/), 'padding'))
        expect(get(box(/ \.chip:not\(\.filter-chip\)$/), 'padding-left')).toBe(get(auroreBox(/ \.chip:not\(\.filter-chip\)$/), 'padding-left'))
        expect(get(box(/ \.chip:not\(\.filter-chip\)$/), 'padding-right')).toBe(get(auroreBox(/ \.chip:not\(\.filter-chip\)$/), 'padding-right'))
        // flat: no gradient, no shadow, no glow
        for (const r of rulesFor(family, mode)) {
          if (!/^:root:not\(\[data-theme\|=aurore\]\)/.test(r.sel)) continue
          for (const [, v] of r.decls) expect(v, r.sel).not.toMatch(/gradient|shadow|glow/)
        }
      })
    })
  }

  it('stops every new transition and animation when motion is reduced', () => {
    const moving = ADJUST.filter((r) => /(^|;)\s*(transition|animation)\s*:/.test(r.body))
    expect(moving.length).toBeGreaterThan(0)
    // the copied rule of the mockup stops every transition and animation under the zone scope
    const reduce = MAQUETTE.find((r) => /prefers-reduced-motion:\s*reduce/.test(r.media) && splitSelectors(r.sel).includes('.atl *'))
    expect(reduce.body).toMatch(/transition:none!important/)
    expect(reduce.body).toMatch(/animation:none!important/)
    for (const r of moving) for (const s of splitSelectors(r.sel)) expect(s, s).toMatch(/^:root\S* \.atl /)
    // the glow's drift, outside the zone, has its own stop
    const halo = SHELL.filter((r) => /prefers-reduced-motion:\s*reduce/.test(r.media))
    expect(halo.some((r) => r.sel.includes('body::before') && /animation:\s*none/.test(r.body))).toBe(true)
  })

  it('keeps the glow one layer behind the console, with no new glass on the rows', () => {
    const glows = SHELL.filter((r) => /radial-gradient/.test(r.body))
    expect(glows.length).toBeGreaterThan(0)
    for (const r of glows) for (const s of splitSelectors(r.sel)) expect(s).toMatch(/ body::before$/)
    expect(SHELL.some((r) => /body::after/.test(r.sel))).toBe(false)
    for (const r of ADJUST) expect(r.body, r.sel).not.toMatch(/backdrop-filter|radial-gradient/)
    expect(SHELL.some((r) => /prefers-reduced-transparency:\s*reduce/.test(r.media) && r.sel.includes('body::before') && /display:\s*none/.test(r.body))).toBe(true)
  })
})
