/**
 * DueDate: the day, how far it is in a short form whose unit follows the size, a tone by
 * urgency, and the full wording with the exact date and time one level down, reachable
 * with the keyboard.
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
    expect(el.querySelector('.lv-due-rel')).toHaveTextContent(/^time\.shortDays:3$/)
  })

  it.each([
    [1, 'time.shortDays:1'],
    [59, 'time.shortDays:59'],
    [60, 'time.shortMonths:2'],
    [493, 'time.shortMonths:16'],
    [729, 'time.shortMonths:24'],
    [731, 'time.shortYears:2'],
    [3650, 'time.shortYears:10'],
    [-1, 'time.lapsed'],
  ])('counts a date %i days away in the unit of its size', (days, words) => {
    expect(mount({ date: at(days) }).querySelector('.lv-due-rel').textContent).toBe(words)
  })

  it.each([
    [-5, 'is-bad', 'time.lapsed'],
    [3, 'is-warn', 'time.shortDays:3'],
    [40, null, 'time.shortDays:40'],
  ])('colours a date %i days away by urgency, the words saying it too', (days, tone, words) => {
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

  it('shows the day alone when there is no deadline to count', () => {
    const el = mount({ date: at(-5), relative: null, tone: '' })
    expect(el.querySelector('.lv-due-rel')).toBeNull()
    expect(el.querySelector('time')).toBeInTheDocument()
  })

  it('keeps the exact date and time one level down, reachable with the keyboard', () => {
    const el = mount({ date: at(3) })
    expect(el).toHaveAttribute('tabindex', '0')
    expect(el).toHaveClass('lv-tip')
    // The short count is spelled out there, before the exact date and time
    expect(el.dataset.tip).toBe(`time.inDays:3 · ${formatDate(at(3), { time: true })}`)
    expect(mount({ date: at(3), relative: 'Revoked' }).dataset.tip).toBe(formatDate(at(3), { time: true }))
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
