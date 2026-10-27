import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { helpContent } from '../../data/helpContent'
import { helpGuides } from '../../data/helpGuides'

const dir = dirname(fileURLToPath(import.meta.url))
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'uk', 'zh']
const load = (code) => JSON.parse(readFileSync(join(dir, '..', 'locales', `${code}.json`), 'utf8'))
const helpFile = (code) => join(dir, '..', '..', 'data', 'help', code, 'acme.js')

const en = load('en').acme.dnsUpdate

describe('acme.dnsUpdate i18n keys (9 locales)', () => {
  it('English defines the namespace', () => {
    expect(Object.keys(en).length).toBeGreaterThan(50)
  })

  for (const code of LOCALE_CODES) {
    it(`${code}: every key exists and is not empty`, () => {
      const bundle = load(code).acme.dnsUpdate
      expect(bundle, `missing acme.dnsUpdate in ${code}`).toBeTruthy()
      for (const key of Object.keys(en)) {
        expect(String(bundle[key] ?? '').trim().length, `acme.dnsUpdate.${key} in ${code}`).toBeGreaterThan(0)
      }
      expect(Object.keys(bundle).sort()).toEqual(Object.keys(en).sort())
    })

    it(`${code}: keeps the interpolation variables of English`, () => {
      const bundle = load(code).acme.dnsUpdate
      for (const [key, value] of Object.entries(en)) {
        const vars = (String(value).match(/\{\{\w+\}\}/g) || []).sort()
        expect((String(bundle[key]).match(/\{\{\w+\}\}/g) || []).sort(), `${key} in ${code}`).toEqual(vars)
      }
    })
  }

  it('the other locales are translated, not copied from English', () => {
    // Product names and short cognates (Active, Notes) can match English. A sentence cannot.
    const PRODUCT_TABS = new Set(['tabAcmesh', 'tabCertbot', 'tabLego', 'tabCertManager', 'tabWinAcme', 'tabPoshAcme'])
    for (const code of LOCALE_CODES.filter((c) => c !== 'en')) {
      const bundle = load(code).acme.dnsUpdate
      const same = Object.keys(en).filter((k) => !PRODUCT_TABS.has(k) && bundle[k] === en[k])
      for (const key of same) {
        expect(en[key].length, `acme.dnsUpdate.${key} in ${code} is an English sentence`).toBeLessThan(20)
      }
      expect(same.length, `${code} copies too many English strings: ${same.join(', ')}`).toBeLessThanOrEqual(6)
    }
  })

  it('no string carries an em dash, in any locale', () => {
    for (const code of LOCALE_CODES) {
      for (const [key, value] of Object.entries(load(code).acme.dnsUpdate)) {
        expect(String(value), `acme.dnsUpdate.${key} in ${code}`).not.toContain('—')
      }
    }
  })

  it('English help carries the DNS UPDATE section and guide, without em dashes', () => {
    const section = helpContent.acme.sections.find((s) => s.title.includes('DNS UPDATE'))
    expect(section?.items?.length).toBe(7)
    expect(JSON.stringify(section)).not.toContain('—')
    expect(helpGuides.acme.content).toContain('### DNS UPDATE (RFC 2136)')
  })

  it('every translated help file carries the section and the guide, without em dashes', async () => {
    for (const code of LOCALE_CODES.filter((c) => c !== 'en')) {
      const text = readFileSync(helpFile(code), 'utf8')
      const added = text.slice(text.indexOf('DNS UPDATE'))
      expect(text, code).toContain('DNS UPDATE (RFC 2136)')
      expect(added, code).not.toContain('—')
      expect(text, code).toContain('NSUPDATE_KEY')
      const mod = (await import(/* @vite-ignore */ helpFile(code))).default
      const section = mod.helpContent.sections.find((s) => s.title.includes('DNS UPDATE'))
      expect(section?.items?.length, code).toBe(7)
      expect(mod.helpGuides.content, code).toContain('### DNS UPDATE (RFC 2136)')
    }
  })
})
