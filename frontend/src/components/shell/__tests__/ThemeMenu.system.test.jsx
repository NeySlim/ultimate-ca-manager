/**
 * The theme menu over the real ThemeContext: Aurore with System follows prefers-color-scheme and its
 * changes, and a saved System choice of an earlier build reads as Atelier with System.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k) => k, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
const persistPreference = vi.fn()
vi.mock('../../../stores/userPreferencesStore', () => ({
  getPreferences: () => ({}),
  subscribePreferences: () => () => {},
  persistPreference: (...a) => persistPreference(...a),
}))

import { ThemeProvider } from '../../../contexts/ThemeContext'
import { ThemeMenu } from '../ThemeMenu'

let mq
function mockSystemDark(matches) {
  const listeners = new Set()
  mq = {
    matches,
    addEventListener: (type, cb) => listeners.add(cb),
    removeEventListener: (type, cb) => listeners.delete(cb),
    flip(dark) { this.matches = dark; listeners.forEach((cb) => cb()) },
  }
  window.matchMedia = vi.fn().mockReturnValue(mq)
}
const attr = (n) => document.documentElement.getAttribute(n)
const trigger = () => screen.getByRole('button', { name: /^shell\.theme\.label/ })
const mount = () => render(<MemoryRouter><ThemeProvider><ThemeMenu /></ThemeProvider></MemoryRouter>)

beforeEach(() => {
  localStorage.clear()
  persistPreference.mockClear()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.removeAttribute('data-mode')
  mockSystemDark(true)
})

describe('Aurore with the system mode', () => {
  it('picks Aurore then System in the menu and follows the OS between dark and light', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(trigger())
    await user.click(screen.getByRole('menuitemradio', { name: 'settings.themeFamilies.aurore' }))
    await user.click(trigger())
    await user.click(screen.getByRole('menuitemradio', { name: /^shell\.theme\.system/ }))
    expect(attr('data-theme')).toBe('aurore')
    expect(attr('data-mode')).toBe('dark')
    expect(persistPreference).toHaveBeenCalledWith('theme_family', 'aurore')
    expect(persistPreference).toHaveBeenLastCalledWith('theme_mode', 'system')
    act(() => mq.flip(false))
    expect(attr('data-theme')).toBe('aurore')
    expect(attr('data-mode')).toBe('light')
    act(() => mq.flip(true))
    expect(attr('data-mode')).toBe('dark')
    await user.click(trigger())
    expect(screen.getByRole('menuitemradio', { name: 'settings.themeFamilies.aurore' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: /^shell\.theme\.system/ })).toHaveAttribute('aria-checked', 'true')
  })

  it('reads the former System choice as Atelier with System', async () => {
    localStorage.setItem('ucm-theme-family', 'atelier')
    localStorage.setItem('ucm-theme-mode', 'system')
    mockSystemDark(false)
    const user = userEvent.setup()
    mount()
    expect(attr('data-theme')).toBe('atelier')
    expect(attr('data-mode')).toBe('light')
    await user.click(trigger())
    expect(screen.getByRole('menuitemradio', { name: 'settings.themeFamilies.atelier' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: /^shell\.theme\.system/ })).toHaveAttribute('aria-checked', 'true')
    expect(persistPreference).not.toHaveBeenCalled()
  })
})
