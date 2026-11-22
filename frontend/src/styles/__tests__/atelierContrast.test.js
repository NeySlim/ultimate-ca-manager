/**
 * Contrast of the four palettes of tokens.css, on the pairs that tire the eye when they are weak:
 * body text 7:1 and muted text 4.5:1 on every surface they sit on (page, panel, table header and
 * dock tabs on raised, hovered and selected rows), control borders and state colours 3:1 (WCAG 1.4.11).
 * Atelier draws its surface hierarchy by luminance alone, Aurore by gradient borders and glows.
 */
import { describe, it, expect } from 'vitest'
import { parseTokens, contrast, hexToRgb, FAMILIES, MODES } from '../../lib/__tests__/themeTokensParser'

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
