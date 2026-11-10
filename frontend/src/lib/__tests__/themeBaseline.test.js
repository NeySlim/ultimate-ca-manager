/**
 * Every token of every palette is pinned in styles/tokens.baseline.json.
 * Changing a value in tokens.css means updating the baseline in the same commit:
 * `UPDATE_THEME_BASELINE=1 npx vitest run src/lib/__tests__/themeBaseline.test.js`.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { parseTokens, TOKEN_NAMES, ALIAS_NAMES } from './themeTokensParser'

const BASELINE = path.resolve(__dirname, '../../styles/tokens.baseline.json')
const tokens = parseTokens()

if (process.env.UPDATE_THEME_BASELINE) {
  fs.writeFileSync(BASELINE, JSON.stringify(tokens, null, 2) + '\n')
}
const baseline = JSON.parse(fs.readFileSync(BASELINE, 'utf8'))

describe('theme baseline', () => {
  it('covers 8 palettes of 21 tokens and 1 alias', () => {
    expect(Object.keys(baseline)).toHaveLength(8)
    for (const palette of Object.values(baseline)) {
      expect(Object.keys(palette).sort()).toEqual([...TOKEN_NAMES, ...ALIAS_NAMES].sort())
    }
  })

  for (const key of Object.keys(baseline)) {
    it(`${key} matches the baseline`, () => {
      expect(tokens[key]).toEqual(baseline[key])
    })
  }
})
