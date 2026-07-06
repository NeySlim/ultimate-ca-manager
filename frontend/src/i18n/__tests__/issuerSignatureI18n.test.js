import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dir = dirname(fileURLToPath(import.meta.url))
const localesDir = join(dir, '..', 'locales')
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'uk', 'zh']
const KEYS = ['issuerSignatureAlgorithm', 'issuerSignatureShort', 'issuerSignatureAlgorithmHint']

function loadLocale(code) {
  return JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))
}

describe('issuer signature i18n keys (9 locales)', () => {
  for (const code of LOCALE_CODES) {
    it(`${code}: common issuer signature keys are defined`, () => {
      const bundle = loadLocale(code)
      for (const key of KEYS) {
        const value = bundle.common?.[key]
        expect(value, `missing common.${key} in ${code}`).toBeTruthy()
        expect(String(value).trim().length).toBeGreaterThan(3)
      }
    })
  }
})
