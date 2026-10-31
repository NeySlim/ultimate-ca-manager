import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'locales')
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'uk', 'zh']

// Either the English term kept whole, or a translation: never half of each
describe('templates.commonName (9 locales)', () => {
  for (const code of LOCALE_CODES) {
    it(`${code}: is not half translated`, () => {
      const value = JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8')).templates.commonName
      expect(value).toMatch(/\(CN\)$/)
      if (value.startsWith('Common ')) expect(value).toBe('Common Name (CN)')
    })
  }
})
