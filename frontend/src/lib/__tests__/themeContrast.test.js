/**
 * WCAG contrast matrix over the 8 family x mode palettes of styles/tokens.css:
 * 4.5:1 for text, 3:1 for fills and control borders.
 * `line` is a decorative divider (exempt from 1.4.11); `control` is the border that carries 3:1.
 */
import { describe, it, expect } from 'vitest'
import { parseTokens, contrast, hexToRgb, rgbToHex, FAMILIES, MODES } from './themeTokensParser'

const tokens = parseTokens()

// Gradient end stops as composed in index.css (--gradient-*: 70% of the token mixed with a constant).
const mix = (c, k) => rgbToHex(hexToRgb(c).map((v, i) => v * 0.7 + hexToRgb(k)[i] * 0.3))

const TEXT_PAIRS = [
  ['text', 'bg'], ['text', 'panel'], ['text', 'raised'], ['muted', 'bg'], ['muted', 'panel'],
  ['good', 'goodbg'], ['warn', 'warnbg'], ['bad', 'badbg'],
  ['text-tertiary', 'bg'], ['text-tertiary', 'panel'],
]
const FILL_PAIRS = [['accent', 'bg'], ['control', 'bg'], ['warn-fill', 'bg']]

describe('theme contrast matrix', () => {
  it('finds all 8 palettes', () => {
    expect(Object.keys(tokens).sort()).toEqual(
      FAMILIES.flatMap((f) => MODES.map((m) => `${f}-${m}`)).sort()
    )
  })

  for (const family of FAMILIES) {
    for (const mode of MODES) {
      const key = `${family}-${mode}`
      describe(key, () => {
        const t = tokens[key]
        for (const [fg, bg] of TEXT_PAIRS) {
          it(`${fg} on ${bg} >= 4.5`, () => {
            expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5)
          })
        }
        for (const [fg, bg] of FILL_PAIRS) {
          it(`${fg} on ${bg} >= 3`, () => {
            expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(3)
          })
        }
        // --on-accent is the text colour of .btn-gradient (primary, success, danger).
        const fills = {
          accent: [t.accent, t['grad-b'] && mix(t.accent, '#8B5CF6')],
          good: [t.good, mix(t.good, '#059669')],
          bad: [t.bad, mix(t.bad, '#DC2626')],
        }
        for (const [name, stops] of Object.entries(fills)) {
          it(`on-accent on ${name} gradient >= 4.5`, () => {
            for (const c of stops) expect(contrast(t['on-accent'], c)).toBeGreaterThanOrEqual(4.5)
          })
        }
        if (family === 'aurore') {
          for (const g of ['grad-a', 'grad-b']) {
            it(`primary button text on ${g} >= 4.5`, () => {
              expect(contrast(t['on-accent'], t[g])).toBeGreaterThanOrEqual(4.5)
            })
          }
        }
      })
    }
  }
})
