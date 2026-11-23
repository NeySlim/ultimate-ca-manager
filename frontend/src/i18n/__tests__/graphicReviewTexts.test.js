/** Texts the graphic review of the PKI and protocol pages found wrong, held in every language. */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dir = dirname(fileURLToPath(import.meta.url))
const LOCALES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'uk', 'zh']
const load = (code) => JSON.parse(readFileSync(join(dir, '..', 'locales', `${code}.json`), 'utf8'))
const strings = (node, path = '') => (typeof node === 'string' ? [[path, node]]
  : Object.entries(node).flatMap(([k, v]) => strings(v, path ? `${path}.${k}` : k)))
const EMPTY_TEXTS = [['templates', 'noTemplatesDescription'], ['trustStore', 'addCertificatesForChain'], ['sshCas', 'noDataDescription'],
  ['sshCertificates', 'noDataDescription'], ['csrs', 'signToSee']]

describe('the texts of the PKI and protocol pages', () => {
  for (const code of LOCALES) {
    const d = load(code)
    it(`${code}: names the two DNS-01 waits apart`, () => {
      expect(d.acme.dnsPropagationTimeout).not.toBe(d.acme.dnsPropagationDelay)
    })
    it(`${code}: writes no Markdown marks in the proxy's usage note`, () => {
      expect(d.acme.proxyUsageNote).not.toContain('**')
    })
    it(`${code}: ends each empty-state sentence of the PKI lists with a full stop`, () => {
      for (const [ns, key] of EMPTY_TEXTS) expect(d[ns][key], `${ns}.${key}`).toMatch(/[.。]$/)
    })
  }

  it('fr: one gender for a CSR (une CSR) and « défi » for the SCEP challenge', () => {
    const fr = load('fr')
    const masculine = strings(fr).filter(([, v]) => /\b(un|du|le|ce|au|Nouveau|nouveau)\s+CSR\b|CSR\s+(créé|supprimé|signé)(?![eé])/.test(v))
    expect(masculine).toEqual([])
    for (const key of ['confirmRegenerateChallenge', 'profileChallengeHelp', 'intuneEnabled']) {
      expect(fr.scep[key], key).not.toMatch(/\bchallenge\b/)
    }
  })
})
