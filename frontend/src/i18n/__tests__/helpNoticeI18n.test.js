/** The "help is English, French and Chinese" notice exists, translated, in every locale. */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const codes = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'uk', 'zh']
const dir = dirname(fileURLToPath(import.meta.url))
const load = (c) => JSON.parse(readFileSync(join(dir, '..', 'locales', `${c}.json`), 'utf8'))

describe('help.englishOnlyNotice', () => {
  const en = load('en').help.englishOnlyNotice
  it('is the agreed English sentence', () => {
    expect(en).toBe('Help is available in English, French and Chinese.')
  })
  it.each(codes.filter((c) => c !== 'en'))('is translated in %s', (c) => {
    const v = load(c).help.englishOnlyNotice
    expect(v).toBeTruthy()
    expect(v).not.toBe(en)
  })
})
