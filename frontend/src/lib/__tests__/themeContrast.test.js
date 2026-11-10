/**
 * WCAG contrast matrix over the 8 family x mode palettes of styles/tokens.css:
 * 4.5:1 for text, 3:1 for fills and control borders.
 * `line` is a decorative divider (exempt from 1.4.11); `control` is the border that carries 3:1.
 */
import { describe, it, expect } from 'vitest'
import { parseTokens, contrast, FAMILIES, MODES } from './themeTokensParser'

const tokens = parseTokens()

// Text colour of the primary button, fixed per family and mode.
const ON_ACCENT = {
  'atelier-dark': '#11243f',
  'aurore-dark': '#0b0e17',
  'purple-dark': (t) => t.bg,
  'sunset-dark': (t) => t.bg,
}
const onAccent = (key, t) => {
  const v = ON_ACCENT[key] ?? '#ffffff'
  return typeof v === 'function' ? v(t) : v
}

const TEXT_PAIRS = [
  ['text', 'bg'], ['text', 'panel'], ['text', 'raised'], ['muted', 'bg'], ['muted', 'panel'],
  ['good', 'goodbg'], ['warn', 'warnbg'], ['bad', 'badbg'],
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
        it('primary button text on accent >= 4.5', () => {
          expect(contrast(onAccent(key, t), t.accent)).toBeGreaterThanOrEqual(4.5)
        })
        if (family === 'aurore') {
          for (const g of ['grad-a', 'grad-b']) {
            it(`primary button text on ${g} >= 4.5`, () => {
              expect(contrast(onAccent(key, t), t[g])).toBeGreaterThanOrEqual(4.5)
            })
          }
        }
      })
    }
  }
})
