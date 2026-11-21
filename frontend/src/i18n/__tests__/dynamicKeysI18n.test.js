import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { KEY_ALGORITHMS } from '../../lib/keyAlgorithms'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'locales')
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'uk', 'zh']

// Keys built at run time (`prefix_${value}`) that no literal in the source names: a dead-key sweep must keep them
const DYNAMIC_KEYS = [
  ...['ssh', 'http'].map((k) => `deploy.kind_${k}`),
  ...['rfc5280', 'cabf', 'etsi'].map((p) => `lint.profile_${p}`),
  ...['csv', 'json'].flatMap((f) => [`audit.format_${f}`, `userCertificates.module.format_${f}`]),
  ...KEY_ALGORITHMS.map((a) => a.csrKey).filter((k) => k && k.startsWith('csrs.')),
]

const lookup = (tree, key) => key.split('.').reduce((node, part) => (node == null ? undefined : node[part]), tree)

describe('keys built at run time (10 locales)', () => {
  for (const code of LOCALE_CODES) {
    it(`${code}: every key a template literal builds has a label`, () => {
      const tree = JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))
      for (const key of DYNAMIC_KEYS) {
        expect(String(lookup(tree, key) || '').trim(), `${key} in ${code}`).not.toBe('')
      }
    })
  }
})
