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
    expect(api.themes.map((t) => t.id)).toEqual(['atelier', 'aurore'])
  })

  for (const family of ['atelier', 'aurore']) {
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
    act(() => { api.setThemeFamily('aurore') })
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
    act(() => { api.setThemeFamily('aurore') })
    act(() => { listeners.forEach((cb) => cb({ theme_family: 'gray' })) })
    expect(attr('data-theme')).toBe('atelier')
  })

  it("setCurrentTheme('gray') selects atelier", () => {
    mount()
    act(() => { api.setThemeFamily('aurore') })
    act(() => { api.setCurrentTheme('gray') })
    expect(attr('data-theme')).toBe('atelier')
  })

  it('ignores an unknown family', () => {
    localStorage.setItem('ucm-theme-family', 'nope')
    mount()
    expect(attr('data-theme')).toBe('atelier')
  })

  // The families of 2.x and of earlier 3.0 builds are gone: Atelier in the stored mode, nothing written back
  for (const gone of ['purple', 'sunset', 'ocean', 'forest', 'cyber']) {
    it(`a stored ${gone} (localStorage) gives Atelier in the stored mode`, () => {
      localStorage.setItem('ucm-theme-family', gone)
      localStorage.setItem('ucm-theme-mode', 'light')
      mount()
      expect(attr('data-theme')).toBe('atelier')
      expect(attr('data-mode')).toBe('light')
      expect(localStorage.getItem('ucm-theme-family')).toBe('atelier')
      expect(persistPreference).not.toHaveBeenCalled()
    })

    it(`a server ${gone} gives Atelier in the stored mode, over another family kept in the browser`, () => {
      localStorage.setItem('ucm-theme-family', 'aurore')
      prefs.value = { theme_family: gone, theme_mode: 'light' }
      mount()
      expect(attr('data-theme')).toBe('atelier')
      expect(attr('data-mode')).toBe('light')
      expect(api.themeFamily).toBe('atelier')
      expect(persistPreference).not.toHaveBeenCalled()
    })
  }

  it('a retired family pushed again and again settles on Atelier without a write loop', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    mount()
    act(() => { api.setThemeFamily('aurore') })
    persistPreference.mockClear()
    setItem.mockClear()
    for (let i = 0; i < 5; i++) act(() => { listeners.forEach((cb) => cb({ theme_family: 'purple', theme_mode: 'dark' })) })
    expect(attr('data-theme')).toBe('atelier')
    expect(persistPreference).not.toHaveBeenCalled()
    // One switch to Atelier writes the two keys once; the next identical pushes write nothing
    expect(setItem.mock.calls.filter(([k]) => k === 'ucm-theme-family')).toEqual([['ucm-theme-family', 'atelier']])
    setItem.mockRestore()
  })

  it('a retired family asked through the setters selects Atelier', () => {
    mount()
    act(() => { api.setThemeFamily('aurore') })
    act(() => { api.setCurrentTheme('purple') })
    expect(attr('data-theme')).toBe('atelier')
    act(() => { api.setThemeFamily('aurore') })
    act(() => { api.setThemeFamily('sunset') })
    expect(attr('data-theme')).toBe('atelier')
    expect(persistPreference).toHaveBeenLastCalledWith('theme_family', 'atelier')
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
