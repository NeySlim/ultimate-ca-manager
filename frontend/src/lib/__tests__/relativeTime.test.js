/**
 * Relative wording of a due date and its urgency tone: hours inside 48 h, whole
 * days beyond, truncated both ways as the mockup counts them ("dans 4 j" at 4 d 22 h).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import i18next from 'i18next'
import { dueTone, relativeParts, relativeDue, relativeAgo, shortParts, relativeShort } from '../relativeTime'
import en from '../../i18n/locales/en.json'
import fr from '../../i18n/locales/fr.json'
import ru from '../../i18n/locales/ru.json'
import zh from '../../i18n/locales/zh.json'

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

  it('counts whole days from 48 h on, the part of a day left out', () => {
    expect(relativeParts(at(48 * HOUR), { now: NOW })).toEqual({ key: 'time.inDays', count: 2 })
    expect(relativeParts(at(2.2 * DAY), { now: NOW })).toEqual({ key: 'time.inDays', count: 2 })
    expect(relativeParts(at(4 * DAY + 22 * HOUR), { now: NOW })).toEqual({ key: 'time.inDays', count: 4 })
    expect(relativeParts(at(10 * DAY + 21 * HOUR), { now: NOW })).toEqual({ key: 'time.inDays', count: 10 })
    expect(relativeParts(at(30 * DAY), { now: NOW })).toEqual({ key: 'time.inDays', count: 30 })
  })

  it('says overdue in whole days once the date is past, one day at least', () => {
    expect(relativeParts(at(-2 * HOUR), { now: NOW })).toEqual({ key: 'time.overdueDays', count: 1 })
    expect(relativeParts(at(-(2 * DAY + 3 * HOUR)), { now: NOW })).toEqual({ key: 'time.overdueDays', count: 2 })
    expect(relativeParts(at(-5.5 * DAY), { now: NOW })).toEqual({ key: 'time.overdueDays', count: 5 })
    expect(relativeParts(at(0), { now: NOW })).toEqual({ key: 'time.overdueDays', count: 1 })
  })

  it('reads the clock when no now is given', () => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
    for (const [days, count] of [[2.2, 2], [9.9, 9], [400.5, 400], [-0.1, 1], [-5.5, 5], [-90.2, 90]]) {
      expect(relativeParts(at(days * DAY)).count).toBe(count)
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
    ['en', en, ['in 2 days', 'expired 1 day ago', 'expired 4 days ago', 'in 1 hour', 'in 28 hours', '20 hours ago']],
    ['fr', fr, ['dans 2 jours', 'échu depuis 1 jour', 'échu depuis 4 jours', 'dans 1 heure', 'dans 28 heures', 'il y a 20 heures']],
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
    const forms = [3, 5, 21].map((d) => relativeDue(at((d + 0.5) * DAY), say, { now: NOW }))
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

describe('relativeShort: the short expiry of a list', () => {
  it.each([
    [3, 'time.short.days', 3],
    [59, 'time.short.days', 59],
    [61, 'time.short.months', 2],
    [365, 'time.short.months', 11],
  ])('reads %i days in the unit its size calls for', (days, key, count) => {
    expect(shortParts(at((days - 0.5) * DAY), { now: NOW })).toEqual({ key, count })
  })

  it.each([
    [493, 'time.short.yearsMonths', 1, 4],
    [731, 'time.short.years', 2, undefined],
    [3324, 'time.short.yearsMonths', 9, 1],
    [3290, 'time.short.years', 9, undefined],
  ])('reads %i days in years and the months left beyond twelve months', (days, key, count, months) => {
    const want = months === undefined ? { key, count } : { key, count, months }
    expect(shortParts(at((days - 0.5) * DAY), { now: NOW })).toEqual(want)
  })

  it('says Expired once the date is past, and nothing without a date', () => {
    expect(shortParts(at(-HOUR), { now: NOW })).toEqual({ key: 'time.short.expired' })
    expect(relativeShort(null, t, { now: NOW })).toBe('')
  })

  it.each([
    ['en', en, ['3 d', '10 mo', '1 y 4 mo', '9 y', 'Expired']],
    ['fr', fr, ['3 j', '10 mois', '1 a 4 mois', '9 ans', 'Échu']],
  ])('is translated in %s', async (lng, resources, expected) => {
    const i18n = i18next.createInstance()
    await i18n.init({ lng, resources: { [lng]: { translation: resources } } })
    const say = i18n.t.bind(i18n)
    expect([2.5, 310, 492.5, 3289.5, -1].map((d) => relativeShort(at(d * DAY), say, { now: NOW }))).toEqual(expected)
  })

  it.each([['ru', ru], ['zh', zh]])('has its own words in %s', async (lng, resources) => {
    const i18n = i18next.createInstance()
    await i18n.init({ lng, resources: { [lng]: { translation: resources } } })
    const say = i18n.t.bind(i18n)
    const words = [2.5, 310, 492.5, 3289.5, -1].map((d) => relativeShort(at(d * DAY), say, { now: NOW }))
    expect(new Set(words).size).toBe(5)
    expect(words.join(' ')).not.toMatch(/time\.short|Expired|\bmo\b/)
  })
})

describe('relativeParts with minutes', () => {
  it('counts minutes under one hour, one at least, and hours from one hour on', () => {
    expect(relativeParts(at(-56 * 60000), { now: NOW, mode: 'event', minutes: true })).toEqual({ key: 'time.minutesAgo', count: 56 })
    expect(relativeParts(at(-10000), { now: NOW, mode: 'event', minutes: true })).toEqual({ key: 'time.minutesAgo', count: 1 })
    expect(relativeParts(at(5 * 60000), { now: NOW, minutes: true })).toEqual({ key: 'time.inMinutes', count: 5 })
    expect(relativeParts(at(-HOUR), { now: NOW, mode: 'event', minutes: true })).toEqual({ key: 'time.hoursAgo', count: 1 })
  })

  it('keeps an overdue date overdue in due mode', () => {
    expect(relativeParts(at(-5 * 60000), { now: NOW, minutes: true })).toEqual({ key: 'time.overdueDays', count: 1 })
  })

  it('has the minute forms in English, French, Russian and Chinese', async () => {
    const i18n = i18next.createInstance()
    await i18n.init({ lng: 'fr', resources: { fr: { translation: fr }, en: { translation: en }, ru: { translation: ru }, zh: { translation: zh } } })
    expect(i18n.t('time.compact.minutesAgo', { count: 56 })).toBe('il y a 56 min')
    expect(i18n.t('time.compact.inMinutes', { count: 5 })).toBe('dans 5 min')
    for (const lng of ['en', 'ru', 'zh']) expect(i18n.t('time.compact.minutesAgo', { lng, count: 3 })).not.toMatch(/time\./)
  })
})
