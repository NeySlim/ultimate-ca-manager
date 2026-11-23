/**
 * A muted pill (a state turned off: Disabled, Never run, Not tested) keeps 4.5:1 between its words and its tinted
 * ground on every surface a pill sits on, in the four palettes: Atelier tints it with the muted colour, Aurore with
 * its own ink (currentColor), lighter on a checked or opened row. Measured in a browser in e2e/graphic-review-final.spec.ts.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { parseRules, splitSelectors, declarations } from './atelierCopy'
import { parseTokens, contrast, resolve, hexToRgb, rgbToHex } from '../../lib/__tests__/themeTokensParser'

const read = (file) => fs.readFileSync(path.resolve(__dirname, file), 'utf8')
const ADJUST = parseRules(read('../atelier/adjust.css')).filter((r) => !r.media)
const TOKENS = parseTokens()
const PALETTES = [['atelier', 'dark'], ['atelier', 'light'], ['aurore', 'dark'], ['aurore', 'light']]
const SURFACES = ['bg', 'panel', 'raised', 'hover', 'selected']

// Whether a selector's theme root holds for a palette (a bare :root holds for all four)
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
// The last value of a property among the rules whose selector passes `test`, in source order
function last(family, mode, test, prop) {
  let found
  for (const r of ADJUST) {
    if (!splitSelectors(r.sel).some((s) => applies(s, family, mode) && test(s))) continue
    for (const [p, v] of declarations(r.body)) if (p === prop) found = v
  }
  return found
}
const over = (ink, ground, p) => rgbToHex(hexToRgb(ink).map((x, i) => x * p + hexToRgb(ground)[i] * (1 - p)))
const share = (value, of) => {
  const m = value?.match(new RegExp(`^color-mix\\(in srgb,\\s*${of.replace(/[()]/g, '\\$&')} ([0-9.]+)%,\\s*transparent\\)$`))
  return m ? parseFloat(m[1]) / 100 : null
}

describe('the muted pill', () => {
  for (const [family, mode] of PALETTES) {
    const tokens = TOKENS[`${family}-${mode}`]
    const ink = resolve(last(family, mode, (s) => /\.badge\.muted$/.test(s), 'color') || 'var(--muted)', tokens)
    for (const surface of SURFACES) {
      it(`${family}-${mode}: its words keep 4.5:1 on its tint over ${surface}`, () => {
        let ground
        if (family === 'atelier') {
          const p = share(last(family, mode, (s) => /\.badge:not\(\.good,\.warn,\.bad\)$/.test(s), 'background-color'), 'var(--muted)')
          expect(p).not.toBeNull()
          ground = over(tokens.muted, tokens[surface], p)
        } else {
          const pill = (s) => /:is\(.*\.badge[,)]/.test(s)
          const row = (s) => pill(s) && /tr\.opened/.test(s)
          const general = last(family, mode, (s) => pill(s) && !row(s), 'background')
          const p = share((surface === 'selected' && last(family, mode, row, 'background')) || general, 'currentColor')
          expect(p).not.toBeNull()
          ground = over(ink, tokens[surface], p)
        }
        expect(contrast(ink, ground)).toBeGreaterThanOrEqual(4.5)
      })
    }
  }
})
