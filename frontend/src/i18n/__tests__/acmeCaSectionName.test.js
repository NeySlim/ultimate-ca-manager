import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { helpContent } from '../../data/helpContent'
import { helpGuides } from '../../data/helpGuides'

const dir = dirname(fileURLToPath(import.meta.url))
const LOCALES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'uk', 'zh']
const load = (code) => JSON.parse(readFileSync(join(dir, '..', 'locales', `${code}.json`), 'utf8'))
const helpFile = (code) => readFileSync(join(dir, '..', '..', 'data', 'help', code, 'acme.js'), 'utf8')

// One rule: a string that points at the section contains the exact screen title
// (acme.certificateAuthorities), suffix included.
const sectionName = (acme) => acme.certificateAuthorities
// Old section name per locale; plain account wording (e.g. "No external CA accounts") is not matched.
const OLD_NAMES = {
  de: ['Externe CA-Konten'],
  en: ['External CA Accounts'],
  es: ['Cuentas CA externas'],
  fr: ['Comptes CA externes'],
  it: ['Account CA esterni'],
  ja: ['下の外部CAアカウント', '外部 CA アカウントで'],
  pt: ['Contas CA externas'],
  uk: ['Зовнішніх CA'],
  zh: ['“外部 CA 账户”', '外部 CA 账户中'],
}
const POINTERS = ['proxyUsageNote', 'proxyUpstreamCAAccountHelper', 'proxyNoCaAccounts', 'proxyManageCaAccountsHint']

describe('ACME proxy strings name the CA section as the screen does', () => {
  for (const code of LOCALES) {
    it(`${code}: the four pointers contain the section title and not the old name`, () => {
      const acme = load(code).acme
      const name = sectionName(acme)
      expect(name.length).toBeGreaterThan(2)
      for (const key of POINTERS) {
        expect(acme[key], `${code} acme.${key}`).toContain(name)
        for (const old of OLD_NAMES[code]) {
          expect(acme[key], `${code} acme.${key}`).not.toContain(old)
        }
      }
    })
  }
})

// Old section names in the built-in help; plain account wording ("each external CA account") is not matched.
const OLD_SECTION = [
  /External CA Accounts/,
  /Comptes CA externes/,
  /(?:\*\*|“|^### |label: ')\s*外部 ?CA ?账户|外部 ?CA ?账户\s*(?:\*\*|”)|外部 CA 账户中/m,
]

describe('built-in help does not cite the old section name', () => {
  const blobs = {
    en: JSON.stringify(helpContent) + '\n' + JSON.stringify(helpGuides),
    fr: helpFile('fr'),
    zh: helpFile('zh'),
  }
  for (const [code, text] of Object.entries(blobs)) {
    it(`${code}: no reference to the old section name`, () => {
      for (const re of OLD_SECTION) {
        const m = text.match(re)
        expect(m && m[0], `${code} still cites ${re}`).toBeNull()
      }
    })
  }
})

describe('help pointers to the section carry the exact screen title', () => {
  const title = (code) => load(code).acme.certificateAuthorities
  const bare = (code) => title(code).replace(/\s*\(CA\)\s*$/, '')
  // The bare name must always be followed by the "(CA)" suffix.
  const bareUses = (text, code) => text.split(bare(code)).slice(1).filter((rest) => !rest.startsWith(' (CA)')).length

  it('en: the upstream account item points at the section', () => {
    const item = JSON.stringify(helpContent).match(/"label":"Upstream CA account","text":"([^"]*)"/)
    expect(item[1]).toContain(title('en'))
  })
  for (const code of ['fr', 'zh']) {
    it(`${code}: the upstream account item points at the section`, () => {
      const m = helpFile(code).match(/label: ['"](?:Compte CA en amont|上游 CA 账户)['"], text: ['"]((?:[^'"\\]|\\.)*)['"]/)
      expect(m, `${code} item`).not.toBeNull()
      expect(m[1]).toContain(title(code))
    })
    it(`${code}: help never cites the section without the suffix`, () => {
      expect(bareUses(helpFile(code), code)).toBe(0)
    })
  }
})
