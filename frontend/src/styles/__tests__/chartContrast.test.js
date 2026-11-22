/**
 * The chart tokens of tokens.css on the four palettes: the three series stand out from the card
 * (3:1, WCAG 1.4.11) and from each other for every colour vision (CIEDE2000 after simulation), and
 * the gauges of the overview (styles/dataviz.css) keep their fill apart from their track.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { parseTokens, contrast, resolve, FAMILIES, MODES } from '../../lib/__tests__/themeTokensParser'
import { parseRules, declarations } from './atelierCopy'
import { minSeparation } from './seriesSeparation'

const tokens = parseTokens()
const SERIES = ['s1', 's2', 's3']
const DATAVIZ = parseRules(fs.readFileSync(path.resolve(__dirname, '../dataviz.css'), 'utf8'))
const valueOf = (re, prop) => DATAVIZ.filter((r) => !r.media && re.test(r.sel)).flatMap((r) => declarations(r.body))
  .filter(([p]) => p === prop).map(([, v]) => v.trim()).pop()

describe('chart tokens', () => {
  for (const family of FAMILIES) {
    for (const mode of MODES) {
      const t = tokens[`${family}-${mode}`]
      describe(`${family}-${mode}`, () => {
        it('draws each series 3:1 on the card, the light teal excepted at 2.8:1 (its figures are always written)', () => {
          for (const s of SERIES) {
            const floor = mode === 'light' && s === 's3' ? 2.8 : 3
            expect(contrast(t[s], t.panel), s).toBeGreaterThanOrEqual(floor)
          }
        })

        it('draws the dark series 3:1 on the page and the raised surfaces too', () => {
          if (mode !== 'dark') return
          for (const s of SERIES) for (const ground of ['bg', 'raised']) expect(contrast(t[s], t[ground]), `${s} on ${ground}`).toBeGreaterThanOrEqual(3)
        })

        it('keeps the three series apart for every colour vision (CIEDE2000 >= 8, 15 for normal vision)', () => {
          const colours = SERIES.map((s) => t[s])
          expect(minSeparation(colours, 'normal')).toBeGreaterThanOrEqual(15)
          for (const vision of ['protan', 'deutan', 'tritan']) expect(minSeparation(colours, vision), vision).toBeGreaterThanOrEqual(8)
        })

        it('keeps the retreat grey and the heat ramp in order: the ramp darkens or lightens one step at a time', () => {
          expect(t.s0).toBe(t.control)
          const ramp = ['h0', 'h1', 'h2', 'h3', 'h4'].map((h) => contrast(t[h], t.panel))
          for (let i = 1; i < ramp.length; i += 1) expect(ramp[i], `h${i}`).toBeGreaterThan(ramp[i - 1])
          expect(t.h4).toBe(t.accent)
        })

        it('keeps each gauge fill 3:1 against its own track', () => {
          const track = valueOf(/\.meter \.track$/, 'background')
          expect(track).toMatch(/var\(--tone\)/)
          for (const tone of ['good', 'warn-fill', 'bad', 's0']) {
            const bg = resolve(track.replace('var(--tone)', `var(--${tone})`), t)
            expect(contrast(t[tone], bg), tone).toBeGreaterThanOrEqual(3)
          }
        })

        it('keeps the ring arc, at both ends of its gradient, 3:1 against its track', () => {
          const ring = resolve(valueOf(/\.ring-track$/, 'stroke'), t)
          for (const end of ['grad-a', 'grad-b']) expect(contrast(t[end], ring), end).toBeGreaterThanOrEqual(3)
        })
      })
    }
  }
})
