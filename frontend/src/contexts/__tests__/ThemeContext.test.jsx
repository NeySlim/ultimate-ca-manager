import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'

const prefs = { value: {} }
const listeners = new Set()
const persistPreference = vi.fn()
vi.mock('../../stores/userPreferencesStore', () => ({
  getPreferences: () => prefs.value,
  subscribePreferences: (cb) => { listeners.add(cb); return () => listeners.delete(cb) },
  persistPreference: (...a) => persistPreference(...a),
}))

import { ThemeProvider, useTheme } from '../ThemeContext'
import { parseTokens } from '../../lib/__tests__/themeTokensParser'

let api
function Probe() {
  api = useTheme()
  return null
}
const mount = () => render(<ThemeProvider><Probe /></ThemeProvider>)
const attr = (n) => document.documentElement.getAttribute(n)

function mockSystemDark(matches) {
  const mq = { matches, addEventListener: vi.fn(), removeEventListener: vi.fn() }
  window.matchMedia = vi.fn().mockReturnValue(mq)
  return mq
}

beforeEach(() => {
  localStorage.clear()
  prefs.value = {}
  listeners.clear()
  persistPreference.mockClear()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.removeAttribute('data-mode')
  document.documentElement.removeAttribute('style')
  mockSystemDark(true)
})

describe('ThemeContext', () => {
  it('defaults to atelier and follows the system', () => {
    mount()
    expect(attr('data-theme')).toBe('atelier')
    expect(attr('data-mode')).toBe('dark')
    expect(api.themes.map((t) => t.id)).toEqual(['atelier', 'aurore', 'purple', 'sunset'])
  })

  for (const family of ['atelier', 'aurore', 'purple', 'sunset']) {
    for (const mode of ['dark', 'light']) {
      it(`sets data-theme=${family} data-mode=${mode}`, () => {
        mount()
        act(() => { api.setThemeFamily(family); api.setMode(mode) })
        expect(attr('data-theme')).toBe(family)
        expect(attr('data-mode')).toBe(mode)
        expect(localStorage.getItem('ucm-theme-family')).toBe(family)
        expect(localStorage.getItem('ucm-theme-mode')).toBe(mode)
        expect(persistPreference).toHaveBeenCalledWith('theme_family', family)
        expect(persistPreference).toHaveBeenCalledWith('theme_mode', mode)
      })
    }
  }

  it('picker accent is the --accent applied for the resolved mode', () => {
    const tokens = parseTokens()
    mount()
    for (const mode of ['dark', 'light']) {
      act(() => { api.setMode(mode) })
      for (const t of api.themes) {
        expect(t.accent.toLowerCase()).toBe(tokens[`${t.id}-${mode}`].accent)
      }
    }
  })

  it('writes no inline colour variable on <html>', () => {
    mount()
    act(() => { api.setThemeFamily('purple') })
    expect(document.documentElement.getAttribute('style') || '').not.toMatch(/--/)
  })

  it('reads a stored gray (localStorage) as atelier and persists atelier', () => {
    localStorage.setItem('ucm-theme-family', 'gray')
    mount()
    expect(attr('data-theme')).toBe('atelier')
    expect(localStorage.getItem('ucm-theme-family')).toBe('atelier')
  })

  it('reads a server gray as atelier', () => {
    prefs.value = { theme_family: 'gray', theme_mode: 'light' }
    mount()
    expect(attr('data-theme')).toBe('atelier')
    expect(attr('data-mode')).toBe('light')
  })

  it('a server gray arriving after another family switches to atelier', () => {
    mount()
    act(() => { api.setThemeFamily('purple') })
    act(() => { listeners.forEach((cb) => cb({ theme_family: 'gray' })) })
    expect(attr('data-theme')).toBe('atelier')
  })

  it("setCurrentTheme('gray') selects atelier", () => {
    mount()
    act(() => { api.setThemeFamily('purple') })
    act(() => { api.setCurrentTheme('gray') })
    expect(attr('data-theme')).toBe('atelier')
  })

  it('ignores an unknown family', () => {
    localStorage.setItem('ucm-theme-family', 'nope')
    mount()
    expect(attr('data-theme')).toBe('atelier')
  })

  it('system mode follows matchMedia changes', () => {
    const mq = mockSystemDark(false)
    mount()
    expect(attr('data-mode')).toBe('light')
    const onChange = mq.addEventListener.mock.calls.find((c) => c[0] === 'change')[1]
    act(() => { mq.matches = true; onChange() })
    expect(attr('data-mode')).toBe('dark')
  })
})
