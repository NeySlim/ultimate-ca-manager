/**
 * Counted texts of the PKI and protocol pages: real plural forms in every language (one and
 * other, few and many in Russian and Ukrainian), never a frozen « (s) ».
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dir = dirname(fileURLToPath(import.meta.url))
const LOCALES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'uk', 'zh']
const load = (code) => JSON.parse(readFileSync(join(dir, '..', 'locales', `${code}.json`), 'utf8'))
const at = (data, path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), data)

const COUNTED = [
  'acme.revokeExistingSuperseded', 'acme.revokeSupersededConfirmDesc', 'acme.revokeSupersededConfirmAction',
  'acme.supersededRevoked', 'acme.eab.totalCount', 'acme.localOrdersCount', 'acme.purgeLocalOrdersDone',
  'scep.intuneAppUsedBy', 'tsa.signerChainPartial', 'trustStore.addedCount', 'trustStore.addSelected',
  'export.skippedUnreadable', 'import.successImported', 'import.keyPairsDetected', 'import.importObjects',
  'import.privateKeysMatched', 'discovery.scans.foundNew',
]
const ZONES = ['acme', 'scep', 'est', 'tsa', 'crlOcsp', 'discovery', 'trustStore', 'sshCas', 'sshCertificates',
  'certificates', 'cas', 'csrs', 'templates', 'import', 'export', 'userCertificates', 'overview', 'protocols', 'inspector']
// « certificat(s) », « Bestellung(en) », « profilo/i », « замовлення(нь) »: a plural frozen in one string
const FROZEN = /[\p{L}]\((?:s|es|e|en|n|i|is|ов|нь|ях|и)\)|[\p{L}]\/i\b/u

const leaves = (o, p = '') => (o && typeof o === 'object'
  ? Object.entries(o).flatMap(([k, v]) => leaves(v, p ? `${p}.${k}` : k))
  : [[p, o]])

describe('PKI and protocol counts', () => {
  it.each(LOCALES)('%s gives each counted text the plural forms of its language, and no bare key', (code) => {
    const data = load(code)
    const needed = new Intl.PluralRules(code).resolvedOptions().pluralCategories.filter((c) => ['one', 'few', 'many', 'other'].includes(c))
    // French and Spanish « many » only serves millions: the checker does not ask for it
    const forms = ['ru', 'uk'].includes(code) ? needed : ['one', 'other']
    for (const key of COUNTED) {
      expect(at(data, key), `${code} ${key}`).toBeUndefined()
      for (const form of forms) expect(at(data, `${key}_${form}`), `${code} ${key}_${form}`).toMatch(/\{\{count\}\}/)
    }
  })

  it.each(['en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'uk'])('%s writes no frozen plural on the PKI and protocol pages', (code) => {
    const data = load(code)
    const frozen = ZONES.flatMap((ns) => leaves(data[ns], ns)).filter(([, v]) => typeof v === 'string' && FROZEN.test(v))
    expect(frozen).toEqual([])
  })

  it('agrees the French words with the count', () => {
    const fr = load('fr')
    expect(at(fr, 'acme.localOrdersCount_one')).toBe('{{count}} commande')
    expect(at(fr, 'acme.localOrdersCount_other')).toBe('{{count}} commandes')
    expect(at(fr, 'discovery.scans.foundNew_other')).toBe('{{total}}, dont {{count}} nouveaux')
    expect(at(fr, 'trustStore.addSelected_other')).toBe('Ajouter {{count}} AC sélectionnées')
  })
})
