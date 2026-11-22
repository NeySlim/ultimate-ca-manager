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
import { FLOW_SERIES } from '../../lib/overviewHorizon'
import { coverParts } from '../../lib/overviewTiles'

const tokens = parseTokens()
const SERIES = ['s1', 's2', 's3']
const DATAVIZ = parseRules(fs.readFileSync(path.resolve(__dirname, '../dataviz.css'), 'utf8'))
const token = (color) => color.match(/^var\(--([a-z0-9-]+)\)$/)[1]
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

        it('draws the issuances of every source 3:1 on the card (the light teal at its 2.8:1), two sources of one colour told apart by hatching', () => {
          for (const s of FLOW_SERIES) {
            const floor = mode === 'light' && token(s.color) === 's3' ? 2.8 : 3
            expect(contrast(t[token(s.color)], t.panel), s.key).toBeGreaterThanOrEqual(floor)
          }
          const byColour = {}
          for (const s of FLOW_SERIES) (byColour[s.color] ||= []).push(s)
          for (const group of Object.values(byColour)) expect(group.filter((s) => !s.hatch), group.map((s) => s.key).join()).toHaveLength(1)
          expect(valueOf(/\.flow \.hatch-line$/, 'stroke')).toBe('var(--panel)')
        })

        it('draws the horizon columns, the manual hatching and the authority diamond 3:1 on the card', () => {
          expect(valueOf(/\.card-horizon \.auto$/, 'background')).toBe('var(--s0)')
          expect(valueOf(/\.card-horizon \.manual$/, 'background')).toMatch(/^repeating-linear-gradient\(135deg,var\(--warn-fill\) /)
          expect(valueOf(/\.card-horizon \.mark$/, 'border')).toMatch(/var\(--warn-fill\)$/)
          for (const tone of ['s0', 'warn-fill']) expect(contrast(t[tone], t.panel), tone).toBeGreaterThanOrEqual(3)
        })

        it('keeps the validity gauge of a tile and the countdown of a deadline 3:1 against their track', () => {
          const life = valueOf(/\.life \.track$/, 'background')
          const countdown = valueOf(/\.queue-due \.countdown$/, 'background')
          for (const [track, tones] of [[life, ['accent', 'warn-fill']], [countdown, ['s0', 'warn-fill', 'bad']]]) {
            expect(track).toMatch(/var\(--tone\)/)
            for (const tone of tones) {
              const bg = resolve(track.replace('var(--tone)', `var(--${tone})`), t)
              expect(contrast(t[tone], bg), tone).toBeGreaterThanOrEqual(3)
            }
          }
        })

        it('draws the three parts of the revocation cover 3:1 on the card, the figures written in them 4.5:1', () => {
          const label = token(valueOf(/\.cover i$/, 'color'))
          for (const part of coverParts({})) {
            expect(contrast(t[token(part.color)], t.panel), part.key).toBeGreaterThanOrEqual(3)
            // The grey part carries no figure (RevocationCard), the legend gives it
            if (part.key !== 'noCdp') expect(contrast(t[label], t[token(part.color)]), part.key).toBeGreaterThanOrEqual(4.5)
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
