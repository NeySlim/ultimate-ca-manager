/**
 * Relative wording of a due date and its urgency tone: hours inside 48 h, days
 * beyond on the product's rounding (time left rounds up, time past rounds down).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import i18next from 'i18next'
import { dueTone, relativeParts, relativeDue, relativeAgo, shortParts, shortDue } from '../relativeTime'
import { daysRemaining } from '../utils'
import en from '../../i18n/locales/en.json'
import fr from '../../i18n/locales/fr.json'
import ru from '../../i18n/locales/ru.json'

const NOW = new Date('2026-11-08T12:00:00Z')
const HOUR = 3600000
const DAY = 24 * HOUR
const at = (ms) => new Date(NOW.getTime() + ms).toISOString()
const t = (key, opts) => `${key}:${opts.count}`

afterEach(() => { vi.useRealTimers() })

describe('relativeParts', () => {
  it('counts hours inside 48 h and never says zero', () => {
    expect(relativeParts(at(28 * HOUR), { now: NOW })).toEqual({ key: 'time.inHours', count: 28 })
    expect(relativeParts(at(10 * 60000), { now: NOW })).toEqual({ key: 'time.inHours', count: 1 })
    expect(relativeParts(at(47.4 * HOUR), { now: NOW })).toEqual({ key: 'time.inHours', count: 47 })
  })

  it('counts days from 48 h on, rounded up like days_remaining', () => {
    expect(relativeParts(at(48 * HOUR), { now: NOW })).toEqual({ key: 'time.inDays', count: 2 })
    expect(relativeParts(at(2.2 * DAY), { now: NOW })).toEqual({ key: 'time.inDays', count: 3 })
    expect(relativeParts(at(30 * DAY), { now: NOW })).toEqual({ key: 'time.inDays', count: 30 })
  })

  it('says overdue in days once the date is past, one day at least', () => {
    expect(relativeParts(at(-2 * HOUR), { now: NOW })).toEqual({ key: 'time.overdueDays', count: 1 })
    expect(relativeParts(at(-5.5 * DAY), { now: NOW })).toEqual({ key: 'time.overdueDays', count: 6 })
    expect(relativeParts(at(0), { now: NOW })).toEqual({ key: 'time.overdueDays', count: 1 })
  })

  it('agrees with daysRemaining on both sides of now', () => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
    for (const days of [2.2, 9, 400, -0.1, -5.5, -90]) {
      const date = at(days * DAY)
      expect(relativeParts(date).count).toBe(Math.abs(daysRemaining(date)))
    }
  })

  it('tells a past event in hours, then days', () => {
    expect(relativeParts(at(-20 * HOUR), { now: NOW, mode: 'event' })).toEqual({ key: 'time.hoursAgo', count: 20 })
    expect(relativeParts(at(-60000), { now: NOW, mode: 'event' })).toEqual({ key: 'time.hoursAgo', count: 1 })
    expect(relativeParts(at(-3.7 * DAY), { now: NOW, mode: 'event' })).toEqual({ key: 'time.daysAgo', count: 3 })
  })

  it('has nothing to say without a readable date', () => {
    expect(relativeParts(null, { now: NOW })).toBeNull()
    expect(relativeParts('', { now: NOW })).toBeNull()
    expect(relativeParts('not a date', { now: NOW })).toBeNull()
  })
})

describe('relativeDue and relativeAgo', () => {
  it('hand the count to the translator, so the plural is its own', () => {
    expect(relativeDue(at(3 * DAY), t, { now: NOW })).toBe('time.inDays:3')
    expect(relativeDue(at(-5 * DAY), t, { now: NOW })).toBe('time.overdueDays:5')
    expect(relativeAgo(at(-20 * HOUR), t, { now: NOW })).toBe('time.hoursAgo:20')
    expect(relativeDue(null, t, { now: NOW })).toBe('')
  })

  it.each([
    ['en', en, ['in 3 days', 'expired 1 day ago', 'expired 5 days ago', 'in 1 hour', 'in 28 hours', '20 hours ago']],
    ['fr', fr, ['dans 3 jours', 'échu depuis 1 jour', 'échu depuis 5 jours', 'dans 1 heure', 'dans 28 heures', 'il y a 20 heures']],
  ])('reads in %s with its plurals', async (lng, resources, expected) => {
    const i18n = i18next.createInstance()
    await i18n.init({ lng, resources: { [lng]: { translation: resources } } })
    const say = i18n.t.bind(i18n)
    expect([
      relativeDue(at(2.5 * DAY), say, { now: NOW }),
      relativeDue(at(-2 * HOUR), say, { now: NOW }),
      relativeDue(at(-4.5 * DAY), say, { now: NOW }),
      relativeDue(at(HOUR), say, { now: NOW }),
      relativeDue(at(28 * HOUR), say, { now: NOW }),
      relativeAgo(at(-20 * HOUR), say, { now: NOW }),
    ]).toEqual(expected)
  })

  it('takes the Russian few and many forms', async () => {
    const i18n = i18next.createInstance()
    await i18n.init({ lng: 'ru', resources: { ru: { translation: ru } } })
    const say = i18n.t.bind(i18n)
    const forms = [3, 5, 21].map((d) => relativeDue(at((d - 0.5) * DAY), say, { now: NOW }))
    expect(new Set(forms).size).toBe(3)
    forms.forEach((text, i) => expect(text).toContain(String([3, 5, 21][i])))
    expect(forms.join(' ')).not.toMatch(/\bin\b|days?/)
  })
})

describe('dueTone', () => {
  it('is bad once past, a warning inside the window, quiet beyond', () => {
    expect(dueTone(at(-HOUR), { now: NOW })).toBe('bad')
    expect(dueTone(at(3 * DAY), { now: NOW })).toBe('warn')
    expect(dueTone(at(8 * DAY), { now: NOW })).toBe('')
  })

  it('takes the window of the caller', () => {
    expect(dueTone(at(20 * DAY), { now: NOW, warnDays: 30 })).toBe('warn')
    expect(dueTone(at(31 * DAY), { now: NOW, warnDays: 30 })).toBe('')
  })

  it('is quiet without a date', () => {
    expect(dueTone(null, { now: NOW })).toBe('')
    expect(dueTone('nope', { now: NOW })).toBe('')
  })
})

describe('shortDue', () => {
  it.each([
    [1, { key: 'time.shortDays', count: 1 }],
    [59, { key: 'time.shortDays', count: 59 }],
    [60, { key: 'time.shortMonths', count: 2 }],
    [493, { key: 'time.shortMonths', count: 16 }],
    [729, { key: 'time.shortMonths', count: 24 }],
    [730, { key: 'time.shortYears', count: 2 }],
    [3287, { key: 'time.shortYears', count: 9 }],
    [0, { key: 'time.lapsed' }],
    [-40, { key: 'time.lapsed' }],
  ])('counts %i days in the unit of their size', (days, parts) => {
    expect(shortParts(at(days * DAY), { now: NOW })).toEqual(parts)
  })

  it('has nothing to say without a date', () => {
    expect(shortParts(null, { now: NOW })).toBeNull()
    expect(shortDue('nope', t, { now: NOW })).toBe('')
  })

  it('reads short in English, French, Russian and Chinese', async () => {
    const zh = (await import('../../i18n/locales/zh.json')).default
    const say = async (lng, resources) => {
      const i18n = i18next.createInstance()
      await i18n.init({ lng, resources: { [lng]: { translation: resources } } })
      return (days) => shortDue(at(days * DAY), i18n.t.bind(i18n), { now: NOW })
    }
    const [inEn, inFr, inRu, inZh] = await Promise.all([say('en', en), say('fr', fr), say('ru', ru), say('zh', zh)])
    expect([3, 493, 3287, -2].map(inEn)).toEqual(['3 d', '16 mo', '9 y', 'Lapsed'])
    expect([3, 493, 3287, -2].map(inFr)).toEqual(['3 j', '16 mois', '9 ans', 'Échu'])
    expect([3, 493, 3287, -2].map(inRu)).toEqual(['3 дн.', '16 мес.', '9 л.', 'Истёк'])
    expect([800, 7670].map(inRu)).toEqual(['2 г.', '21 г.'])
    expect([3, 493, 3287, -2].map(inZh)).toEqual(['3 天', '16 个月', '9 年', '已到期'])
  })
})
