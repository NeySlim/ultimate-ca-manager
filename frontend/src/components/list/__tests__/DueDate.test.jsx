/**
 * DueDate: the day, how far it is in a short form whose unit follows the size
 * (days, months, years, Expired), a tone by urgency, and the exact date, time and
 * long wording one level down, reachable with the keyboard.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts ? `${key}:${opts.count}` : key), i18n: { language: 'en' } }),
}))

import { DueDate } from '../DueDate'
import { formatDate } from '../../../lib/utils'

const NOW = new Date('2026-11-08T12:00:00Z')
const DAY = 86400000
const at = (days) => new Date(NOW.getTime() + days * DAY).toISOString()
const mount = (props) => render(<DueDate now={NOW} {...props} />).container.firstChild

describe('DueDate', () => {
  it('shows the day and how far it is', () => {
    const el = mount({ date: at(2.5) })
    expect(el.querySelector('time')).toHaveTextContent(formatDate(at(2.5), { time: false }))
    expect(el.querySelector('time')).toHaveAttribute('datetime', at(2.5))
    expect(el.querySelector('.lv-due-rel')).toHaveTextContent(/^time\.short\.days:3$/)
  })

  it.each([
    [-5, 'is-bad', 'time.short.expired'],
    [3, 'is-warn', 'time.short.days:3'],
    [40, null, 'time.short.days:40'],
    [59, null, 'time.short.days:59'],
    [61, null, 'time.short.months:2'],
    [493, null, 'time.short.months:16'],
    [729, null, 'time.short.months:23'],
    [731, null, 'time.short.years:2'],
    [3324, null, 'time.short.years:9'],
  ])('colours a date %i days away by urgency, the short words saying it too', (days, tone, words) => {
    const el = mount({ date: at(days) })
    expect(el.className.match(/is-\w+/)?.[0] ?? null).toBe(tone)
    expect(el.querySelector('.lv-due-rel')).toHaveTextContent(words)
  })

  it('takes the warning window of the caller', () => {
    expect(mount({ date: at(20), warnDays: 30 })).toHaveClass('is-warn')
    expect(mount({ date: at(20), warnDays: 7 })).not.toHaveClass('is-warn')
  })

  it('lets the caller set the tone, an empty one included', () => {
    expect(mount({ date: at(3), tone: '' }).className).not.toMatch(/is-/)
    expect(mount({ date: at(40), tone: 'bad' })).toHaveClass('is-bad')
  })

  it('takes a word of the caller instead of the distance (a revoked certificate)', () => {
    const el = mount({ date: at(40), relative: 'Revoked', tone: '' })
    expect(el.querySelector('.lv-due-rel')).toHaveTextContent(/^Revoked$/)
    expect(el.dataset.tip).toBe(formatDate(at(40), { time: true }))
  })

  it('shows the day alone when there is no deadline to count', () => {
    const el = mount({ date: at(-5), relative: null, tone: '' })
    expect(el.querySelector('.lv-due-rel')).toBeNull()
    expect(el.querySelector('time')).toBeInTheDocument()
  })

  it('keeps the exact date and time one level down, reachable with the keyboard', () => {
    const el = mount({ date: at(3) })
    expect(el).toHaveAttribute('tabindex', '0')
    expect(el).toHaveClass('lv-tip')
    expect(el.dataset.tip).toBe(`${formatDate(at(3), { time: true })} · time.inDays:3`)
    expect(el.dataset.tip).not.toBe(el.querySelector('time').textContent)
  })

  it('marks an absent date and offers no tooltip for it', () => {
    for (const date of [null, undefined, '', 'not a date']) {
      const el = mount({ date })
      expect(el).toHaveTextContent(/^—$/)
      expect(el).not.toHaveAttribute('tabindex')
      expect(el.dataset.tip).toBeUndefined()
    }
  })
})
