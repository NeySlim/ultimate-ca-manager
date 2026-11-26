import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, relative } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const srcDir = join(here, '..', '..')
const localesDir = join(here, '..', 'locales')
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'uk', 'zh']

const lookup = (tree, key) => key.split('.').reduce((node, part) => (node == null ? undefined : node[part]), tree)
// A plural key is stored as key_one / key_other
const present = (tree, key) => {
  if (typeof lookup(tree, key) === 'string') return true
  return ['_one', '_other'].some((suffix) => typeof lookup(tree, key + suffix) === 'string')
}

function sources(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) {
      if (!['__tests__', 'test', 'node_modules'].includes(name)) sources(path, out)
    } else if (/\.(jsx?|tsx?)$/.test(name) && !/\.test\./.test(name)) out.push(path)
  }
  return out
}

// Every t('a.b') literal of the interface: i18next shows a missing key raw, in every language
const LITERALS = []
for (const file of sources(srcDir)) {
  const text = readFileSync(file, 'utf8')
  for (const m of text.matchAll(/\bt\(\s*['"]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)['"]/g)) {
    LITERALS.push({ key: m[1], file: relative(srcDir, file) })
  }
}

describe('t() literals have a text (10 locales)', () => {
  it('finds the literals', () => { expect(LITERALS.length).toBeGreaterThan(1000) })
  for (const code of LOCALE_CODES) {
    it(`${code}: every literal key exists`, () => {
      const tree = JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))
      const missing = LITERALS.filter(({ key }) => !present(tree, key)).map(({ key, file }) => `${file}: ${key}`)
      expect([...new Set(missing)]).toEqual([])
    })
  }
})
