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

// One rule: a string that points at the section contains the screen title
// (acme.certificateAuthorities) without its trailing "(CA)" suffix.
const sectionName = (acme) => acme.certificateAuthorities.replace(/\s*\(CA\)\s*$/, '')
const POINTERS = ['proxyUsageNote', 'proxyUpstreamCAAccountHelper', 'proxyNoCaAccounts', 'proxyManageCaAccountsHint']

describe('ACME proxy strings name the CA section as the screen does', () => {
  for (const code of LOCALES) {
    it(`${code}: the four pointers contain the section title`, () => {
      const acme = load(code).acme
      const name = sectionName(acme)
      expect(name.length).toBeGreaterThan(2)
      for (const key of POINTERS) {
        expect(acme[key], `${code} acme.${key}`).toContain(name)
      }
    })
  }
})

// Old section names; plain account wording ("each external CA account") is not matched.
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
