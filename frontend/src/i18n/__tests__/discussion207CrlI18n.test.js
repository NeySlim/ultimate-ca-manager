import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dir = dirname(fileURLToPath(import.meta.url))
const localesDir = join(dir, '..', 'locales')
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'uk', 'zh']

const CRL_KEYS = [
  'nextPublish',
  'fullCrlScheduleTitle',
  'fullCrlScheduleHelp',
  'crlValidityDays',
  'crlValidityDaysOption',
  'crlPublishInterval',
  'crlPublishIntervalOption',
  'crlDigest',
  'fullCrlConfigUpdated',
  'fullCrlConfigFailed',
]

function loadLocale(code) {
  return JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))
}

describe('discussion #207 CRL schedule i18n (9 locales)', () => {
  for (const code of LOCALE_CODES) {
    it(`${code}: crlOcsp schedule keys are defined`, () => {
      const bundle = loadLocale(code)
      for (const key of CRL_KEYS) {
        const value = bundle.crlOcsp?.[key]
        expect(value, `missing crlOcsp.${key} in ${code}`).toBeTruthy()
        expect(String(value).trim().length).toBeGreaterThan(2)
      }
      const helper = bundle.settings?.httpProtocolPortHelper || ''
      expect(helper.toLowerCase().includes('80') || helper.includes('8080'), `port 80 note missing in ${code}`).toBe(true)
    })
  }
})
