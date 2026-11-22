/**
 * The header of a fit or number column of the PKI lists is short in every language (COLONNES-SPEC L8):
 * 16 characters at most, the whole label going to labelFull when a short one is needed.
 */
import { describe, it, expect } from 'vitest'

const locales = import.meta.glob('../locales/*.json', { eager: true, import: 'default' })

// Certificates, authorities, CSRs, templates, trust store, user certificates, SSH CAs and SSH certificates
const KEYS = [
  'certificates.state', 'certificates.source', 'certificates.expiry', 'common.key', 'certificates.complianceColumn',
  'certificates.hybrid.column', 'certificates.creationColumn', 'common.type', 'common.status', 'common.certificates',
  'common.algorithm', 'csrs.module.key', 'csrs.module.submitted', 'atelier.state', 'templates.source', 'common.validity',
  'templates.module.uses', 'trustStore.module.expires', 'userCertificates.module.expires', 'sshCas.caType', 'sshCas.keyType',
  'sshCas.stats.certificates', 'sshCertificates.certType',
]
const read = (tree, key) => key.split('.').reduce((node, part) => node?.[part], tree)

describe('fit and number headers of the PKI lists', () => {
  it('ten languages are read', () => {
    expect(Object.keys(locales)).toHaveLength(10)
  })

  for (const [file, tree] of Object.entries(locales)) {
    it(`are 16 characters at most in ${file.split('/').pop()}`, () => {
      const long = KEYS.map((key) => [key, read(tree, key)]).filter(([, label]) => typeof label !== 'string' || [...label].length > 16)
      expect(long).toEqual([])
    })
  }
})
