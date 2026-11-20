/**
 * An empty certificate list counts in the plural, as the mockup: "0 identités", "0–0 sur 0
 * certificats". French CLDR puts 0 with 1, so the zero form is spelled out.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import i18next from 'i18next'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'locales')
const load = (code) => JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))

async function say(code, key, options) {
  const i18n = i18next.createInstance()
  await i18n.init({ lng: code, resources: { [code]: { translation: load(code) } } })
  return i18n.t(key, options)
}

describe('certificate list counters at zero', () => {
  it.each([
    ['fr', 'certificates.total', { count: 0 }, '0 identités'],
    ['fr', 'certificates.total', { count: 1 }, '1 identité'],
    ['fr', 'certificates.range', { count: 0, start: 0, end: 0 }, '0–0 sur 0 certificats'],
    ['en', 'certificates.total', { count: 0 }, '0 identities'],
    ['ru', 'certificates.total', { count: 0 }, '0 субъектов'],
  ])('%s %s %o', async (code, key, options, expected) => {
    expect(await say(code, key, options)).toBe(expected)
  })
})
