/** The backup counter agrees with its count in Ukrainian and Russian, whose 1, 2 to 4 and 5 forms differ. */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import i18next from 'i18next'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'locales')
const load = (code) => JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))

async function label(code, key, count) {
  const i18n = i18next.createInstance()
  await i18n.init({ lng: code, resources: { [code]: { translation: load(code) } }, interpolation: { escapeValue: false } })
  return i18n.t(key, { count, size: '12 MiB' })
}

describe('settings.backupCount', () => {
  it.each([
    ['uk', 1, '1 копія'], ['uk', 2, '2 копії'], ['uk', 4, '4 копії'], ['uk', 5, '5 копій'], ['uk', 21, '21 копія'], ['uk', 11, '11 копій'],
    ['ru', 1, '1 резервная копия'], ['ru', 2, '2 резервные копии'], ['ru', 5, '5 резервных копий'], ['ru', 22, '22 резервные копии'],
  ])('%s, %i', async (code, count, expected) => {
    expect(await label(code, 'settings.backupCount', count)).toBe(expected)
  })
})

describe('settings.backupSpaceUsed', () => {
  it.each([
    ['uk', 1, 'у 1 копії'], ['uk', 3, 'у 3 копіях'], ['uk', 7, 'у 7 копіях'],
    ['ru', 1, '1 копия'], ['ru', 3, '3 копии'], ['ru', 7, '7 копий'],
  ])('%s, %i', async (code, count, expected) => {
    expect(await label(code, 'settings.backupSpaceUsed', count)).toContain(expected)
  })
})
