import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { helpContent } from '../../data/helpContent'
import { helpGuides } from '../../data/helpGuides'
import { HELP_TRANSLATED_LANGUAGES } from '../../data/helpLanguages'

const dir = dirname(fileURLToPath(import.meta.url))
const localesDir = join(dir, '..', 'locales')
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'uk', 'zh']
const LOG_KEYS = ['subtitle', 'level', 'lines', 'searchPlaceholder', 'empty',
  'unavailable', 'showing', 'scanCap', 'linesOpt', 'filters', 'exclude', 'readingFrom', 'source', 'sourceApp', 'sourceAccess',
  'sourceError', 'sourceJournal', 'component', 'allComponents', 'follow', 'time', 'message', 'levelShort', 'from', 'to', 'serverTime', 'errors', 'warnings', 'components', 'copyAll', 'copySelected']
const HELP_FILES = HELP_TRANSLATED_LANGUAGES
  .map((c) => join(dir, '..', '..', 'data', 'help', c, 'systemLogs.js'))

function loadLocale(code) {
  return JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))
}

describe('system logs i18n keys (9 locales)', () => {
  for (const code of LOCALE_CODES) {
    it(`${code}: the nav label is defined`, () => {
      const value = loadLocale(code).common?.systemLogs
      expect(value, `missing common.systemLogs in ${code}`).toBeTruthy()
      expect(String(value).trim().length).toBeGreaterThan(2)
    })

    it(`${code}: every page key is defined`, () => {
      const bundle = loadLocale(code).logs
      expect(bundle, `missing logs namespace in ${code}`).toBeTruthy()
      for (const key of LOG_KEYS) {
        expect(bundle[key], `missing logs.${key} in ${code}`).toBeTruthy()
      }
    })
  }

  it('no page string carries an em dash, in any locale', () => {
    // The project keeps them at zero in the text it shows people. A colon or a
    // shorter sentence says the same thing in every one of these languages.
    for (const code of LOCALE_CODES) {
      for (const [key, value] of Object.entries(loadLocale(code).logs)) {
        expect(String(value), `logs.${key} in ${code}`).not.toContain('\u2014')
      }
    }
  })

  it('no help text carries an em dash either', () => {
    for (const file of HELP_FILES) {
      expect(readFileSync(file, 'utf8'), file).not.toContain('\u2014')
    }
    // Imported rather than read as text: a help file is a module, and a stray
    // backtick in a guide's template literal breaks the build, not a substring
    // search.
    expect(helpContent.systemLogs?.sections?.length, 'helpContent.systemLogs').toBeGreaterThan(0)
    expect(helpGuides.systemLogs?.content?.length, 'helpGuides.systemLogs').toBeGreaterThan(100)
    expect(JSON.stringify(helpContent.systemLogs)).not.toContain('\u2014')
    expect(helpGuides.systemLogs.content).not.toContain('\u2014')
  })

  it('every locale describes the same filters as English', () => {
    const english = helpContent.systemLogs.sections.map((s) => s.items.length)
    for (const file of HELP_FILES) {
      const body = readFileSync(file, 'utf8')
      const counts = [...body.matchAll(/items: \[([\s\S]*?)\]/g)]
        .map((m) => m[1].split('\n').filter((l) => l.trim().startsWith('"')).length)
      expect(counts, `${file} lists different filters from English`).toEqual(english)
    }
  })

  it('no locale was left on the English string', () => {
    const english = loadLocale('en')
    for (const code of LOCALE_CODES.filter((c) => c !== 'en')) {
      expect(loadLocale(code).common.systemLogs,
        `${code} still carries the English nav label`).not.toBe(english.common.systemLogs)
    }
  })
})
