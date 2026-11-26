/** formatDate writes month names in the interface's language, not the browser's. */
import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import i18next from 'i18next'
import { formatDate } from '../utils'
import { setDateFormat, setShowTime } from '../../stores/dateFormatStore'
import { setAppTimezone } from '../../stores/timezoneStore'

const DAY = '2026-01-06T12:00:00Z'

describe('formatDate and the interface language', () => {
  beforeAll(async () => {
    await i18next.init({ lng: 'fr', fallbackLng: 'en', resources: { en: { translation: { hi: 'Hello' } }, fr: { translation: { hi: 'Bonjour' } }, de: { translation: { hi: 'Hallo' } } } })
    setAppTimezone('UTC')
    setShowTime(false)
  })
  afterEach(() => { setDateFormat('short') })

  it.each([['fr', 'janvier', 'janv.'], ['de', 'Januar', 'Jan.']])('%s', async (lang, long, short) => {
    await i18next.changeLanguage(lang)
    setDateFormat('long')
    expect(formatDate(DAY)).toContain(long)
    setDateFormat('short')
    expect(formatDate(DAY)).toContain(short)
    expect(formatDate(DAY)).not.toContain('Jan 6')
  })

  it('follows the language shown, not an unsupported one asked for', async () => {
    await i18next.changeLanguage('nl-NL')
    setDateFormat('long')
    expect(formatDate(DAY)).toContain('January')
  })

  it('keeps the numeric formats as they are named', async () => {
    await i18next.changeLanguage('fr')
    setDateFormat('us')
    expect(formatDate(DAY)).toBe('01/06/2026')
  })
})
