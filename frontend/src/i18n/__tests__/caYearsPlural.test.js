/**
 * The CA validity presets start at 1 year (#378): each locale must agree the
 * count, Ukrainian included, whose 2-4 form differs from 5 and up.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import i18next from 'i18next'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'locales')
const load = (code) => JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))

async function yearsLabel(code, count) {
  const i18n = i18next.createInstance()
  await i18n.init({ lng: code, resources: { [code]: { translation: load(code) } } })
  return i18n.t('cas.yearsValidity', { count })
}

describe('cas.yearsValidity plural forms', () => {
  it.each([
    ['en', 1, '1 year'], ['en', 2, '2 years'],
    ['fr', 1, '1 an'], ['fr', 3, '3 ans'],
    ['de', 1, '1 Jahr'], ['es', 1, '1 año'], ['it', 1, '1 anno'], ['pt', 1, '1 ano'],
    ['uk', 1, '1 рік'], ['uk', 2, '2 роки'], ['uk', 3, '3 роки'], ['uk', 5, '5 років'], ['uk', 20, '20 років'],
    ['ja', 1, '1年'], ['zh', 2, '2年'],
  ])('%s, %i', async (code, count, expected) => {
    expect(await yearsLabel(code, count)).toBe(expected)
  })
})

describe('Ukrainian plural keys', () => {
  const flat = (obj, prefix = '') => Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' ? flat(v, `${prefix}${k}.`) : [`${prefix}${k}`])
  const pluralKeys = flat(load('uk')).filter(k => k.endsWith('_one')).map(k => k.slice(0, -4))

  it('covers the plural keys', () => {
    expect(pluralKeys.length).toBeGreaterThan(20)
  })

  // one (1, 21), few (2-4, 22), many (5-20): each form must exist, else the key shows
  it.each([1, 2, 5, 11, 21, 22])('every key renders a sentence for %i', async (count) => {
    const i18n = i18next.createInstance()
    await i18n.init({ lng: 'uk', resources: { uk: { translation: load('uk') } } })
    for (const key of pluralKeys) {
      const out = i18n.t(key, { count })
      expect(out, key).not.toBe(key)
      expect(out, key).toContain(String(count))
    }
  })

  it('agrees the noun with the count', async () => {
    const i18n = i18next.createInstance()
    await i18n.init({ lng: 'uk', resources: { uk: { translation: load('uk') } } })
    expect([1, 2, 5].map(count => i18n.t('common.subtitle', { count })))
      .toEqual(['1 сертифікат', '2 сертифікати', '5 сертифікатів'])
  })
})
