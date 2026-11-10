/**
 * WCAG contrast matrix over the 8 family x mode palettes of styles/tokens.css:
 * 4.5:1 for text, 3:1 for fills and control borders.
 * `line` is a decorative divider (exempt from 1.4.11); `control` is the border that carries 3:1.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { parseTokens, paletteDecls, resolve, splitArgs, contrast, FAMILIES, MODES } from './themeTokensParser'

const tokens = parseTokens()
const INDEX_CSS = fs.readFileSync(path.resolve(__dirname, '../../index.css'), 'utf8')
  .replace(/\/\*[\s\S]*?\*\//g, '')
const decls = paletteDecls(INDEX_CSS)

// Declarations of every rule whose selector list is exactly `selector`, in source order.
function ruleDecls(css, selector) {
  const out = []
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!m[1].split(',').map((x) => x.trim()).includes(selector)) continue
    for (const d of m[2].matchAll(/(?:^|;)\s*([a-z-]+)\s*:\s*([^;]+)/g)) out.push([d[1], d[2].trim()])
  }
  return out
}
const lastValue = (pairs, prop) => pairs.filter(([p]) => p === prop).map(([, v]) => v).pop()

// Text colour and gradient stops of a .btn-gradient variant, resolved against one palette.
function gradientButton(key, variant) {
  const rules = [...ruleDecls(INDEX_CSS, '.btn-gradient'), ...(variant ? ruleDecls(INDEX_CSS, `.btn-gradient.${variant}`) : [])]
  const bg = lastValue(rules, 'background').match(/^var\(--([a-z-]+)\)$/)[1]
  const grad = decls[key][bg].match(/^linear-gradient\((.*)\)$/)[1]
  const stops = splitArgs(grad).filter((x) => !/deg$/.test(x))
  return {
    color: resolve(lastValue(rules, 'color'), decls[key]),
    stops: stops.map((x) => resolve(x.replace(/\s+[0-9.]+%$/, ''), decls[key])),
  }
}

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
        // .btn-gradient (primary, success, danger) as index.css draws it: text is --on-accent,
        // every stop of its --gradient-* background is readable under it.
        for (const variant of ['', 'success', 'danger']) {
          it(`.btn-gradient${variant && '.' + variant} text is on-accent, >= 4.5 on each stop`, () => {
            const { color, stops } = gradientButton(key, variant)
            expect(color).toBe(t['on-accent'])
            expect(stops.length).toBeGreaterThanOrEqual(2)
            for (const c of stops) expect(contrast(color, c)).toBeGreaterThanOrEqual(4.5)
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
