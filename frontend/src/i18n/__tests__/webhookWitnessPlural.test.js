/**
 * The webhook witness of the overview health card reads "1 active endpoint", not "1 active
 * endpoints"; Ukrainian and Russian have four forms (1, 2-4, 5-20, 21).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import i18next from 'i18next'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'locales')
const load = (code) => JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))

async function line(code, state, count) {
  const i18n = i18next.createInstance()
  await i18n.init({ lng: code, resources: { [code]: { translation: load(code) } } })
  return i18n.t(`overview.health.witness.webhooks.${state}`, { count })
}

describe('webhook witness plural forms', () => {
  it.each([
    ['en', 'active', 1, '1 active endpoint'], ['en', 'active', 2, '2 active endpoints'],
    ['en', 'none_active', 1, '1 endpoint, none active'], ['en', 'none_active', 2, '2 endpoints, none active'],
    ['fr', 'active', 1, '1 point de terminaison actif'], ['fr', 'active', 2, '2 points de terminaison actifs'],
    ['de', 'none_active', 1, '1 Endpunkt, keiner aktiv'], ['de', 'none_active', 3, '3 Endpunkte, keiner aktiv'],
    ['uk', 'active', 1, '1 активна кінцева точка'], ['uk', 'active', 2, '2 активні кінцеві точки'],
    ['uk', 'active', 5, '5 активних кінцевих точок'], ['uk', 'active', 21, '21 активна кінцева точка'],
    ['uk', 'none_active', 1, '1 кінцева точка, не активна'], ['uk', 'none_active', 3, '3 кінцеві точки, жодна не активна'],
    ['uk', 'none_active', 11, '11 кінцевих точок, жодна не активна'],
    ['ru', 'active', 1, '1 активная конечная точка'], ['ru', 'active', 2, '2 активные конечные точки'],
    ['ru', 'active', 5, '5 активных конечных точек'], ['ru', 'active', 21, '21 активная конечная точка'],
    ['ru', 'none_active', 1, '1 конечная точка, ни одной активной'], ['ru', 'none_active', 3, '3 конечные точки, ни одной активной'],
    ['ru', 'none_active', 11, '11 конечных точек, ни одной активной'],
  ])('%s %s %i', async (code, state, count, expected) => {
    expect(await line(code, state, count)).toBe(expected)
  })

  it.each(['en', 'fr', 'de', 'es', 'it', 'pt', 'ja', 'zh', 'uk', 'ru'])('%s renders a sentence for 1 and 2', async (code) => {
    for (const state of ['active', 'none_active']) {
      for (const count of [1, 2]) {
        const out = await line(code, state, count)
        expect(out).not.toContain('witness.webhooks')
        expect(out).toContain(String(count))
      }
    }
  })
})
