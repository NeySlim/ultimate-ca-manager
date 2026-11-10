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
    themes: [{ id: 'atelier', nameKey: 'themes.atelier', accent: 'x' }, { id: 'aurore', nameKey: 'themes.aurore', accent: 'y' }],
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
  it('picks a family and a mode through the shared context', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('radio', { name: /themes\.aurore/ }))
    expect(theme.setThemeFamily).toHaveBeenCalledWith('aurore')
    await user.click(screen.getByRole('radio', { name: /settings\.light/ }))
    expect(theme.setMode).toHaveBeenCalledWith('light')
    await user.click(screen.getByRole('radio', { name: /settings\.followSystem/ }))
    expect(theme.setMode).toHaveBeenCalledWith('system')
  })

  it('marks the current family and mode, and focuses the current family on open', async () => {
    const user = setup()
    await user.click(trigger())
    expect(screen.getByRole('radio', { name: /themes\.atelier/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /settings\.followSystem/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /themes\.atelier/ })).toHaveFocus()
  })

  it('shows the applied mode in the icon, not the chosen one', () => {
    theme.value = { themeFamily: 'atelier', mode: 'system', resolvedMode: 'light' }
    setup()
    expect(trigger().querySelector('svg')).toHaveAttribute('data-mode', 'light')
  })

  it('loops the arrow keys over the options', async () => {
    const user = setup()
    await user.click(trigger())
    const radios = screen.getAllByRole('radio')
    await user.keyboard('{ArrowUp}')
    expect(radios[radios.length - 1]).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(radios[0]).toHaveFocus()
  })

  it.each(['{Escape}', '{Tab}'])('closes on %s and gives the focus back to the button', async (key) => {
    const user = setup()
    await user.click(trigger())
    await user.keyboard(key)
    expect(screen.queryByRole('radio', { name: /themes\.aurore/ })).toBeNull()
    expect(trigger()).toHaveFocus()
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })
})
