/**
 * StateTabs: one tab per state with its counter, the selected one announced, and
 * the keyboard pattern of a tab list (arrows move, Enter or Space select).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const lang = vi.hoisted(() => ({ current: 'en' }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: lang.current } }),
}))

import { StateTabs } from '../StateTabs'

const VIEWS = [
  { id: '', label: 'All', count: 1234 },
  { id: 'expiring', label: 'To renew', count: 2, tone: 'warn' },
  { id: 'valid', label: 'Valid', count: 0 },
  { id: 'archived', label: 'Archived' },
]
const mount = (props = {}) => render(<StateTabs views={VIEWS} active="" label="Filter by state" onChange={() => {}} {...props} />)
const tabs = () => screen.getAllByRole('tab')
const focused = () => document.activeElement.textContent

describe('StateTabs', () => {
  it('is a named tab list with one selected tab', () => {
    mount({ active: 'expiring' })
    expect(screen.getByRole('tablist', { name: 'Filter by state' })).toBeInTheDocument()
    expect(tabs().map((el) => el.getAttribute('aria-selected'))).toEqual(['false', 'true', 'false', 'false'])
  })

  it('shows each counter, zero included, and none where there is no count', () => {
    mount()
    expect(tabs().map((el) => el.textContent)).toEqual(['All1,234', 'To renew2', 'Valid0', 'Archived'])
  })

  it('formats the counters for the language', () => {
    lang.current = 'fr'
    mount()
    lang.current = 'en'
    expect(tabs()[0].textContent).toMatch(/^All1\s234$/)
  })

  it('marks a view that needs attention with a dot the label already explains', () => {
    mount()
    const dots = tabs().map((el) => el.querySelector('.lv-dot'))
    expect(dots.map(Boolean)).toEqual([false, true, false, false])
    expect(dots[1]).toHaveAttribute('aria-hidden', 'true')
  })

  it('selects on click', () => {
    const onChange = vi.fn()
    mount({ onChange })
    fireEvent.click(screen.getByRole('tab', { name: /Valid/ }))
    expect(onChange).toHaveBeenCalledWith('valid')
    fireEvent.click(screen.getByRole('tab', { name: /All/ }))
    expect(onChange).toHaveBeenLastCalledWith('')
  })

  it('keeps one tab stop, on the selected tab', () => {
    mount({ active: 'valid' })
    expect(tabs().map((el) => el.tabIndex)).toEqual([-1, -1, 0, -1])
  })

  it('keeps the first tab reachable when the state on screen is no single view', () => {
    mount({ active: null })
    expect(tabs().map((el) => el.getAttribute('aria-selected'))).toEqual(['false', 'false', 'false', 'false'])
    expect(tabs().map((el) => el.tabIndex)).toEqual([0, -1, -1, -1])
  })

  it('moves the focus with the arrows, Home and End, wrapping at the ends, without selecting', () => {
    const onChange = vi.fn()
    mount({ onChange })
    tabs()[0].focus()
    fireEvent.keyDown(document.activeElement, { key: 'ArrowRight' })
    expect(focused()).toBe('To renew2')
    fireEvent.keyDown(document.activeElement, { key: 'End' })
    expect(focused()).toBe('Archived')
    fireEvent.keyDown(document.activeElement, { key: 'ArrowRight' })
    expect(focused()).toBe('All1,234')
    fireEvent.keyDown(document.activeElement, { key: 'ArrowLeft' })
    expect(focused()).toBe('Archived')
    fireEvent.keyDown(document.activeElement, { key: 'Home' })
    expect(focused()).toBe('All1,234')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('leaves the other keys to the browser', () => {
    mount()
    tabs()[0].focus()
    const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
    document.activeElement.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
    expect(focused()).toBe('All1,234')
  })

  it('names the panel it filters and gives each tab an id the panel can cite', () => {
    mount({ baseId: 'certs', controls: 'certs-panel', active: 'valid' })
    expect(tabs().map((el) => el.id)).toEqual(['certs-tab-all', 'certs-tab-expiring', 'certs-tab-valid', 'certs-tab-archived'])
    tabs().forEach((el) => expect(el).toHaveAttribute('aria-controls', 'certs-panel'))
  })

  it('are buttons that submit nothing', () => {
    mount()
    tabs().forEach((el) => expect(el).toHaveAttribute('type', 'button'))
  })
})
