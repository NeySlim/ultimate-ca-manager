import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dir = dirname(fileURLToPath(import.meta.url))
const localesDir = join(dir, '..', 'locales')
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'uk', 'zh']

const CERT_KEYS = [
  'friendlyName',
  'friendlyNamePlaceholder',
  'templateUsed',
  'metadataSection',
  'metadataSaved',
  'metadataSaveFailed',
]

const CAS_KEYS = [
  'customValidityYears',
  'customValidityDate',
  'customValidityDateRequired',
  'customValidityYearsInvalid',
]

const PROTOCOL_KEYS = [
  'protocolTransportTitle',
  'protocolTransportHelp',
  'protocolModeInherit',
  'protocolModeHttp',
  'protocolModeHttps',
  'protocolModeCustom',
  'protocolBaseOverride',
  'protocolBaseOverrideHelp',
  'protocolAdvancedEndpoints',
  'protocolCdpBase',
  'protocolOcspBase',
  'protocolAiaBase',
  'protocolTlsLoopWarning',
  'protocolCustomEnabled',
  'protocolHttpEnabled',
  'protocolHttpsEnabled',
  'protocolHttpFailed',
]

function loadLocale(code) {
  return JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))
}

describe('discussion #207 batch-2 i18n (9 locales)', () => {
  for (const code of LOCALE_CODES) {
    it(`${code}: certificate / CA / protocol transport keys`, () => {
      const bundle = loadLocale(code)
      for (const key of CERT_KEYS) {
        const value = bundle.certificates?.[key]
        expect(value, `missing certificates.${key} in ${code}`).toBeTruthy()
        expect(String(value).trim().length).toBeGreaterThan(2)
      }
      for (const key of CAS_KEYS) {
        const value = bundle.cas?.[key]
        expect(value, `missing cas.${key} in ${code}`).toBeTruthy()
        expect(String(value).trim().length).toBeGreaterThan(2)
      }
      for (const key of PROTOCOL_KEYS) {
        const value = bundle.crlOcsp?.[key]
        expect(value, `missing crlOcsp.${key} in ${code}`).toBeTruthy()
        expect(String(value).trim().length).toBeGreaterThan(2)
      }
    })
  }
})
