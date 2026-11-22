/** Theme menu: same ThemeContext as Appearance, applied mode icon, keyboard loop and focus return. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { PATHS } from '../../atelier/icons'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

const theme = vi.hoisted(() => ({
  setThemeFamily: vi.fn(), setMode: vi.fn(),
  value: { themeFamily: 'atelier', mode: 'system', resolvedMode: 'dark' },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o ? `${k}|${Object.values(o).join(',')}` : k), i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({
    ...theme.value, setThemeFamily: theme.setThemeFamily, setMode: theme.setMode,
    // A family the context might still list never reaches the menu: the mockup's five choices only
    themes: [{ id: 'atelier', nameKey: 'themes.atelier', accent: 'x' }, { id: 'aurore', nameKey: 'themes.aurore', accent: 'y' }, { id: 'purple', nameKey: 'themes.purple', accent: 'z' }],
  }),
}))

import { ThemeMenu } from '../ThemeMenu'

const trigger = () => screen.getByRole('button', { name: /^shell\.theme\.label\|/ })
const drawn = (svg) => svg.innerHTML
// The mockup's pictogram, as Icon draws it
const drawnOf = (name) => {
  const box = document.createElement('div')
  box.innerHTML = `<svg>${PATHS[name]}</svg>`
  return box.querySelector('svg').innerHTML
}

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
  it('offers the family and the mode as two named radio groups, a separator between them', async () => {
    const user = setup()
    await user.click(trigger())
    const menu = screen.getByRole('menu')
    const [families, modes] = within(menu).getAllByRole('group')
    expect(families).toHaveAccessibleName('shell.theme.family')
    expect(modes).toHaveAccessibleName('shell.theme.mode')
    expect(within(families).getAllByRole('menuitemradio').map(b => b.textContent)).toEqual(['settings.themeFamilies.atelier', 'settings.themeFamilies.aurore'])
    expect(within(modes).getAllByRole('menuitemradio').map(b => b.textContent)).toEqual([
      'shell.theme.system' + 'shell.theme.systemNow|shell.theme.dark', 'shell.theme.dark', 'shell.theme.light'])
    expect(within(menu).getAllByRole('separator')).toHaveLength(1)
    // A family the context might still list never reaches the menu
    expect(within(menu).queryByText('themes.purple')).toBeNull()
  })

  it('applies the family alone or the mode alone, closes, and gives the focus back to the button', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('menuitemradio', { name: 'settings.themeFamilies.aurore' }))
    expect(theme.setThemeFamily).toHaveBeenCalledWith('aurore')
    expect(theme.setMode).not.toHaveBeenCalled()
    expect(screen.queryByRole('menu')).toBeNull()
    expect(trigger()).toHaveFocus()
    await user.click(trigger())
    await user.click(screen.getByRole('menuitemradio', { name: /shell\.theme\.system/ }))
    expect(theme.setMode).toHaveBeenLastCalledWith('system')
    expect(theme.setThemeFamily).toHaveBeenCalledTimes(1)
  })

  it('checks Aurore and System together: System follows the OS in either family', async () => {
    theme.value = { themeFamily: 'aurore', mode: 'system', resolvedMode: 'light' }
    const user = setup()
    await user.click(trigger())
    expect(screen.getByRole('menuitemradio', { name: 'settings.themeFamilies.aurore' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: /shell\.theme\.system/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: 'settings.themeFamilies.atelier' })).toHaveAttribute('aria-checked', 'false')
    expect(trigger()).toHaveAccessibleName('shell.theme.label|settings.themeFamilies.aurore, shell.theme.system (shell.theme.light)')
  })

  it('checks the current choice and focuses it on open', async () => {
    theme.value = { themeFamily: 'atelier', mode: 'dark', resolvedMode: 'dark' }
    const user = setup()
    await user.click(trigger())
    const atelier = screen.getByRole('menuitemradio', { name: 'settings.themeFamilies.atelier' })
    expect(atelier).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: 'shell.theme.dark' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('menuitemradio', { name: /shell\.theme\.system/ })).toHaveAttribute('aria-checked', 'false')
    // The first checked item takes the focus
    expect(atelier).toHaveFocus()
  })

  it('shows the applied theme in the icon and the title', () => {
    theme.value = { themeFamily: 'atelier', mode: 'system', resolvedMode: 'light' }
    setup()
    expect(trigger()).toHaveAttribute('data-mode', 'light')
    expect(trigger().getAttribute('title')).toBe('shell.theme.label|settings.themeFamilies.atelier, shell.theme.system (shell.theme.light)')
  })

  it('opens on the down arrow of its button', async () => {
    const user = setup()
    trigger().focus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menu')).toBeInTheDocument()
  })

  it('opens on the up arrow of its button, on the last choice, as the mockup', async () => {
    const user = setup()
    trigger().focus()
    await user.keyboard('{ArrowUp}')
    const choices = within(screen.getByRole('menu')).getAllByRole('menuitemradio')
    expect(choices[choices.length - 1]).toHaveFocus()
    expect(choices[choices.length - 1]).toHaveTextContent('shell.theme.light')
  })

  it('names the theme in force on the button: "Theme: Atelier, System (dark)", a menu popup', () => {
    setup()
    expect(trigger()).toHaveAccessibleName('shell.theme.label|settings.themeFamilies.atelier, shell.theme.system (shell.theme.dark)')
    expect(trigger()).toHaveAttribute('title', 'shell.theme.label|settings.themeFamilies.atelier, shell.theme.system (shell.theme.dark)')
    expect(trigger()).toHaveAttribute('aria-haspopup', 'menu')
  })

  it('draws sparkles for the Aurore family, else the applied mode, with the mockup\'s icon', () => {
    theme.value = { themeFamily: 'aurore', mode: 'light', resolvedMode: 'light' }
    const { unmount } = render(<MemoryRouter><ThemeMenu /></MemoryRouter>)
    expect(trigger()).toHaveAccessibleName('shell.theme.label|settings.themeFamilies.aurore, shell.theme.light')
    const svg = trigger().querySelector('svg')
    expect(svg).toHaveClass('icon')
    expect(drawn(svg)).toBe(drawnOf('sparkles'))
    unmount()
    theme.value = { themeFamily: 'atelier', mode: 'dark', resolvedMode: 'dark' }
    render(<MemoryRouter><ThemeMenu /></MemoryRouter>)
    expect(drawn(trigger().querySelector('svg'))).toBe(drawnOf('moon'))
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
