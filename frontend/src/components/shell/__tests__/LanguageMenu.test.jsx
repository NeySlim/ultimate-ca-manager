/** The bar's language menu: radio items of the ten languages, the current one checked, the account's own path, one menu at a time. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ROLES, canFor, tStub } from './shellTestUtils'

const i18n = vi.hoisted(() => ({ language: 'fr-FR', changeLanguage: vi.fn() }))
const persistPreference = vi.hoisted(() => vi.fn())

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tStub, i18n }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../stores/userPreferencesStore', async (importOriginal) => ({ ...(await importOriginal()), persistPreference }))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'probe', role: 'viewer' }, logout: vi.fn(), authMethod: 'password' }),
}))
vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), resolvedMode: 'dark', themes: [] }),
}))
vi.mock('../../../services/dashboard.service', () => ({ dashboardService: { getQueue: vi.fn().mockResolvedValue({ data: { items: [] } }) } }))
vi.mock('../../../services/audit.service', () => ({ default: { getLogs: vi.fn().mockResolvedValue({ data: [] }) } }))
vi.mock('../../../services/auth.service', () => ({ authService: { getCurrentUser: vi.fn().mockResolvedValue({ data: {} }) } }))
vi.mock('../../WebSocketIndicator', () => ({ WebSocketIndicator: () => <span data-testid="ws" /> }))
vi.mock('../../../services', () => ({ certificatesService: { getStats: vi.fn().mockResolvedValue({ data: { expiring: 0, expired: 0 } }) } }))

import { TopBar } from '../TopBar'

const NAMES = ['English', 'Français', 'Deutsch', 'Español', 'Italiano', 'Português', 'Українська', 'Русский', '中文', '日本語']

function setup() {
  const user = userEvent.setup()
  render(
    <MemoryRouter>
      <TopBar can={canFor(ROLES.admin)} pins={[]} activeId="" hasHelp onOpenSearch={vi.fn()} onOpenHelp={vi.fn()} onTogglePin={vi.fn()} />
    </MemoryRouter>
  )
  return user
}
const trigger = () => screen.getByRole('button', { name: 'settings.language' })
const menu = () => document.getElementById('language-menu')

beforeEach(() => {
  vi.clearAllMocks()
  i18n.language = 'fr-FR'
  localStorage.clear()
})

describe('LanguageMenu in the bar', () => {
  it('sits in the tools just before the theme button', () => {
    setup()
    const tools = document.querySelector('.global-tools')
    const order = [...tools.children].map(el => el.querySelector('button')?.id || el.id)
    expect(order.indexOf('language-button')).toBe(order.indexOf('theme-button') - 1)
    expect(trigger()).toHaveClass('icon-btn', 'quiet')
    expect(trigger()).toHaveAttribute('aria-haspopup', 'menu')
  })

  it('opens on the ten languages, each in its own language, the current one checked and focused', async () => {
    const user = setup()
    expect(menu()).not.toBeVisible()
    await user.click(trigger())
    expect(trigger()).toHaveAttribute('aria-expanded', 'true')
    const list = screen.getByRole('menu', { name: 'settings.language' })
    const radios = within(list).getAllByRole('menuitemradio')
    expect(radios).toHaveLength(10)
    expect(radios.map(r => r.querySelector('.pop-label').textContent)).toEqual(NAMES)
    expect(radios.map(r => r.getAttribute('lang'))).toEqual(['en', 'fr', 'de', 'es', 'it', 'pt', 'uk', 'ru', 'zh', 'ja'])
    const checked = radios.filter(r => r.getAttribute('aria-checked') === 'true')
    expect(checked.map(r => r.getAttribute('lang'))).toEqual(['fr'])
    expect(checked[0]).toHaveFocus()
  })

  it('applies a choice by the account path, closes, and gives the focus back', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('menuitemradio', { name: /Deutsch/ }))
    expect(i18n.changeLanguage).toHaveBeenCalledWith('de')
    expect(localStorage.getItem('i18nextLng')).toBe('de')
    expect(persistPreference).toHaveBeenCalledWith('language', 'de')
    expect(menu()).not.toBeVisible()
    expect(trigger()).toHaveFocus()
  })

  it('moves with the arrows and closes on Escape, the focus back on the button', async () => {
    const user = setup()
    await user.click(trigger())
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitemradio', { name: /Deutsch/ })).toHaveFocus()
    await user.keyboard('{End}')
    expect(screen.getByRole('menuitemradio', { name: /日本語/ })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(menu()).not.toBeVisible()
    expect(trigger()).toHaveFocus()
    expect(i18n.changeLanguage).not.toHaveBeenCalled()
  })

  it('closes on a click outside', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(document.body)
    expect(menu()).not.toBeVisible()
  })

  it('keeps one menu open at a time with the theme and the account', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('button', { name: /^shell\.theme\.label/ }))
    expect(menu()).not.toBeVisible()
    expect(document.getElementById('theme-menu')).toBeVisible()
    await user.click(trigger())
    expect(document.getElementById('theme-menu')).not.toBeVisible()
    expect(menu()).toBeVisible()
    await user.click(screen.getByRole('button', { name: /^shell\.accountLabel/ }))
    expect(menu()).not.toBeVisible()
    expect(document.getElementById('user-menu')).toBeVisible()
  })
})
