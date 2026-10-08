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
