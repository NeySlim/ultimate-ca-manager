/** Theme menu: same ThemeContext as Appearance, applied mode icon, keyboard loop and focus return. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { tStub } from './shellTestUtils'

const theme = vi.hoisted(() => ({
  setThemeFamily: vi.fn(), setMode: vi.fn(),
  value: { themeFamily: 'atelier', mode: 'system', resolvedMode: 'dark' },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tStub, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({
    ...theme.value, setThemeFamily: theme.setThemeFamily, setMode: theme.setMode,
    themes: [{ id: 'atelier', nameKey: 'themes.atelier', accent: 'x' }, { id: 'aurore', nameKey: 'themes.aurore', accent: 'y' }, { id: 'purple', nameKey: 'themes.purple', accent: 'z' }],
  }),
}))

import { ThemeMenu } from '../ThemeMenu'

const trigger = () => screen.getByRole('button', { name: 'shell.theme.menu' })

function setup() {
  const user = userEvent.setup()
  render(<MemoryRouter><ThemeMenu /><button type="button">after</button></MemoryRouter>)
  return user
}

beforeEach(() => {
  theme.setThemeFamily.mockReset()
  theme.setMode.mockReset()
  theme.value = { themeFamily: 'atelier', mode: 'system', resolvedMode: 'dark' }
})

describe('ThemeMenu', () => {
  it('offers the five choices of the mockup, then the other families', async () => {
    const user = setup()
    await user.click(trigger())
    const names = screen.getAllByRole('menuitemradio').map(b => b.textContent)
    expect(names.slice(0, 5)).toEqual(['shell.theme.system' + 'shell.theme.systemNow', 'shell.theme.dark',
      'shell.theme.light', 'shell.theme.aurore', 'shell.theme.auroreLight'])
    expect(names.slice(5)).toEqual(['themes.purple'])
  })

  it('applies family and mode together, closes, and gives the focus back to the button', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('menuitemradio', { name: /shell\.theme\.auroreLight/ }))
    expect(theme.setThemeFamily).toHaveBeenCalledWith('aurore')
    expect(theme.setMode).toHaveBeenCalledWith('light')
    expect(screen.queryByRole('menu')).toBeNull()
    expect(trigger()).toHaveFocus()
    await user.click(trigger())
    await user.click(screen.getByRole('menuitemradio', { name: /shell\.theme\.system/ }))
    expect(theme.setThemeFamily).toHaveBeenLastCalledWith('atelier')
    expect(theme.setMode).toHaveBeenLastCalledWith('system')
    await user.click(trigger())
    await user.click(screen.getByRole('menuitemradio', { name: /themes\.purple/ }))
    expect(theme.setThemeFamily).toHaveBeenLastCalledWith('purple')
  })

  it('checks the current choice and focuses it on open', async () => {
    theme.value = { themeFamily: 'atelier', mode: 'dark', resolvedMode: 'dark' }
    const user = setup()
    await user.click(trigger())
    const dark = screen.getByRole('menuitemradio', { name: /shell\.theme\.dark/ })
    expect(dark).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: /shell\.theme\.system/ })).toHaveAttribute('aria-checked', 'false')
    expect(dark).toHaveFocus()
  })

  it('shows the applied theme in the icon and the title', () => {
    theme.value = { themeFamily: 'atelier', mode: 'system', resolvedMode: 'light' }
    setup()
    expect(trigger().querySelector('svg')).toHaveAttribute('data-mode', 'light')
    expect(trigger().getAttribute('title')).toBe('shell.theme.current|shell.theme.system (shell.theme.light)')
  })

  it('opens on the down arrow of its button', async () => {
    const user = setup()
    trigger().focus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menu')).toBeInTheDocument()
  })

  it('loops the arrow keys over the options', async () => {
    const user = setup()
    await user.click(trigger())
    const items = screen.getAllByRole('menuitemradio')
    await user.keyboard('{ArrowUp}')
    expect(items[items.length - 1]).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(items[0]).toHaveFocus()
  })

  it.each(['{Escape}', '{Tab}'])('closes on %s and gives the focus back to the button', async (key) => {
    const user = setup()
    await user.click(trigger())
    await user.keyboard(key)
    expect(screen.queryByRole('menu')).toBeNull()
    expect(trigger()).toHaveFocus()
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })
})
