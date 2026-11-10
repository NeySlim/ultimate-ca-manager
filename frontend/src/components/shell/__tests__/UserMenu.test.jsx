/** Account menu: identity, method, rights-gated settings, theme, language, sign out. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { ROLES, canFor, tStub } from './shellTestUtils'

const logout = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const setThemeFamily = vi.hoisted(() => vi.fn())
const setMode = vi.hoisted(() => vi.fn())
const changeLanguage = vi.hoisted(() => vi.fn())
const persistPreference = vi.hoisted(() => vi.fn())
const auth = vi.hoisted(() => ({ method: 'password' }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tStub, i18n: { language: 'fr-FR', changeLanguage } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'probe', role: 'operator' }, logout, authMethod: auth.method }),
}))
vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({
    themeFamily: 'atelier', setThemeFamily, mode: 'dark', setMode,
    themes: [{ id: 'atelier', nameKey: 'themes.atelier', accent: 'x' }, { id: 'aurore', nameKey: 'themes.aurore', accent: 'y' }],
  }),
}))
vi.mock('../../../stores/userPreferencesStore', () => ({ persistPreference }))

import { UserMenu } from '../UserMenu'

function Where() { return <output data-testid="where">{useLocation().pathname}</output> }

function setup(permissions = ROLES.admin) {
  const user = userEvent.setup()
  render(
    <MemoryRouter initialEntries={['/certificates']}>
      <UserMenu can={canFor(permissions)} />
      <Routes><Route path="*" element={<Where />} /></Routes>
    </MemoryRouter>
  )
  return user
}
const trigger = () => screen.getByRole('button', { name: 'common.account: probe' })

beforeEach(() => { vi.clearAllMocks(); auth.method = 'password' })

describe('UserMenu', () => {
  it('opens with the identity and the sign-in method', async () => {
    const user = setup()
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
    await user.click(trigger())
    expect(trigger()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('probe')).toBeVisible()
    expect(screen.getByText('operator')).toBeVisible()
    expect(screen.getByText('shell.signedInWith')).toBeVisible()
  })

  it('says nothing about a method the session does not know', async () => {
    auth.method = null
    const user = setup()
    await user.click(trigger())
    expect(screen.queryByText('shell.signedInWith')).toBeNull()
  })

  it('offers Settings to an administrator', async () => {
    const user = setup(ROLES.admin)
    await user.click(trigger())
    expect(screen.getByRole('link', { name: 'common.settings' })).toBeVisible()
  })

  it('hides Settings from an operator without the settings right', async () => {
    const user = setup(ROLES.operator)
    await user.click(trigger())
    expect(screen.queryByRole('link', { name: 'common.settings' })).toBeNull()
    expect(screen.getByRole('link', { name: 'common.account' })).toBeVisible()
  })

  it('sets the theme family and the mode', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('button', { name: /themes\.aurore/ }))
    expect(setThemeFamily).toHaveBeenCalledWith('aurore')
    await user.click(screen.getByRole('button', { name: /settings\.light/ }))
    expect(setMode).toHaveBeenCalledWith('light')
    expect(screen.getByRole('button', { name: /themes\.atelier/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('changes the language and saves it with the preferences', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('button', { name: /Deutsch/ }))
    expect(changeLanguage).toHaveBeenCalledWith('de')
    expect(persistPreference).toHaveBeenCalledWith('language', 'de')
    expect(screen.getByRole('button', { name: /Français/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('signs out then goes to the login page', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('button', { name: 'auth.logout' }))
    expect(logout).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/login'))
  })

  it('closes on Escape and returns the focus to the account button', async () => {
    const user = setup()
    await user.click(trigger())
    await user.keyboard('{Escape}')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
    expect(document.activeElement).toBe(trigger())
  })

  it('goes to the account page and closes', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('link', { name: 'common.account' }))
    expect(screen.getByTestId('where')).toHaveTextContent('/account')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })
})
