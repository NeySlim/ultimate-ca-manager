/**
 * COLONNES-SPEC L8: the header of a fit or number column of the protocol lists (ACME, SCEP, EST, TSA, CRL / OCSP) holds
 * 16 characters at most in every language; a longer name goes in labelFull (title and aria-label), not in the header.
 */
import { describe, it, expect } from 'vitest'

const locales = import.meta.glob('../../../i18n/locales/*.json', { eager: true, import: 'default' })

// The header keys of the fit and number columns these pages declare, the state included
const KEYS = [
  'atelier.state', 'acme.createdOn', 'acme.columns.orders', 'acme.method', 'common.expires', 'common.created', 'common.source', 'common.issued',
  'acme.environment', 'acme.columns.failures', 'acme.columns.wildcard', 'common.default', 'acme.proxy', 'common.type', 'acme.eab.created',
  'scep.requested', 'scep.columns.lastTest', 'est.columns.authShort', 'tsa.columns.digest', 'tsa.columns.policy',
  'crlOcsp.columns.published', 'crlOcsp.columns.nextUpdate',
]
const at = (tree, key) => key.split('.').reduce((node, part) => node?.[part], tree)

describe('the short headers of the protocol lists', () => {
  it('has ten languages to read', () => {
    expect(Object.keys(locales)).toHaveLength(10)
  })

  it.each(KEYS)('%s holds 16 characters at most in every language', (key) => {
    const long = Object.entries(locales)
      .map(([file, tree]) => [file.split('/').pop(), at(tree, key)])
      .filter(([, value]) => typeof value !== 'string' || [...value].length > 16)
    expect(long).toEqual([])
  })
})
