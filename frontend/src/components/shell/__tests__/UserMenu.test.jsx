/** Account menu: the account card and the session's facts read from the server, My account, Settings for who may see it,
 * Lock and Sign out apart (Lock also by Alt+Shift+L); the language on a phone. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { ROLES, canFor } from './shellTestUtils'

const logout = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const lock = vi.hoisted(() => vi.fn())
const getCurrentUser = vi.hoisted(() => vi.fn())
const auth = vi.hoisted(() => ({ method: 'password', user: null }))
const i18n = vi.hoisted(() => ({ language: 'fr-FR', changeLanguage: vi.fn() }))
const persistPreference = vi.hoisted(() => vi.fn())

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => { const { defaultValue: _defaultValue, ...v } = o || {}; return Object.keys(v).length ? `${k}|${Object.values(v).join(',')}` : k }, i18n }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: auth.user, logout, lock, authMethod: auth.method }),
}))
vi.mock('../../../stores/userPreferencesStore', async (importOriginal) => ({ ...(await importOriginal()), persistPreference }))
vi.mock('../../../services/auth.service', () => ({ authService: { getCurrentUser } }))

import { UserMenu } from '../UserMenu'

function Where() { return <output data-testid="where">{useLocation().pathname}</output> }

function setup(can = canFor(ROLES.operator)) {
  const user = userEvent.setup()
  render(
    <MemoryRouter initialEntries={['/certificates']}>
      <UserMenu can={can} />
      <Routes><Route path="*" element={<Where />} /></Routes>
    </MemoryRouter>
  )
  return user
}
const trigger = () => screen.getByRole('button', { name: 'shell.accountLabel|probe,common.operator' })

beforeEach(() => {
  vi.clearAllMocks()
  auth.method = 'password'
  auth.user = { username: 'probe', role: 'operator' }
  getCurrentUser.mockResolvedValue({ data: { session_timeout: 1800 } })
})

describe('UserMenu', () => {
  it('names the account and its role on the button, the name in its tooltip', () => {
    setup()
    expect(trigger()).toHaveAttribute('title', 'probe')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('opens on the account card: the avatar beside the name, the role and login, then the facts known', async () => {
    auth.user = { username: 'probe', role: 'operator', full_name: 'Probe Person', email: 'probe@example.com' }
    const user = setup()
    await user.click(screen.getByRole('button', { name: 'shell.accountLabel|Probe Person,common.operator' }))
    const card = document.querySelector('#user-menu > .user-id > .auth-user')
    expect(card.querySelector('.avatar')).toHaveTextContent('PR')
    expect(card.querySelector('.avatar')).toHaveAttribute('aria-hidden', 'true')
    expect(card.querySelector('.avatar').nextElementSibling.querySelector('strong')).toHaveTextContent('Probe Person')
    expect(card).toHaveTextContent('common.operator · probe')
    const facts = document.querySelector('.user-id > dl.kv')
    await waitFor(() => expect([...facts.querySelectorAll('dt')].map(dt => dt.textContent)).toEqual(['common.email', 'shell.userCard.signIn', 'shell.userCard.session']))
    expect([...facts.querySelectorAll('dd')].map(dd => dd.textContent)).toEqual(['probe@example.com', 'shell.method.password', 'shell.userCard.lockIn|30'])
  })

  it('names an SSO or LDAP sign-in', async () => {
    auth.method = 'sso'
    const user = setup()
    await user.click(trigger())
    expect(screen.getByText('shell.method.sso')).toBeVisible()
  })

  it('says only the lock for a session restored from the browser: the server no longer knows the method', async () => {
    auth.method = 'session'
    const user = setup()
    await user.click(trigger())
    expect(await screen.findByText('shell.userCard.lockIn|30')).toBeVisible()
    expect(screen.queryByText('shell.userCard.signIn')).toBeNull()
  })

  it('says nothing about a method the session does not know, nor an e-mail it has not', async () => {
    auth.method = null
    const user = setup()
    await user.click(trigger())
    expect(screen.queryByText('shell.userCard.signIn')).toBeNull()
    expect(screen.queryByText('common.email')).toBeNull()
  })

  it('has My account and Sign out only for who may not see Settings', async () => {
    const user = setup()
    await user.click(trigger())
    const menu = document.getElementById('user-menu')
    const items = [...menu.querySelectorAll('a, button')].map(el => el.textContent)
    expect(items).toEqual(['common.account', 'shell.lock', 'shell.signOut'])
    // Lock and Sign out stand apart
    expect(screen.getByRole('separator').nextElementSibling).toHaveAttribute('id', 'user-lock')
    expect(document.getElementById('user-lock').nextElementSibling).toHaveAttribute('id', 'user-logout')
  })

  it('puts Settings between My account and Sign out for who may see it, with the module glyph', async () => {
    const user = setup(canFor(ROLES.admin))
    await user.click(trigger())
    const menu = document.getElementById('user-menu')
    const items = [...menu.querySelectorAll('a, button')]
    expect(items.map(el => el.textContent)).toEqual(['common.account', 'common.settings', 'shell.lock', 'shell.signOut'])
    expect(items[1]).toHaveClass('pop-item')
    expect(items[1].querySelector('svg.icon')).not.toBeNull()
  })

  it('goes to Settings and closes, the keyboard walking the four items', async () => {
    const user = setup(canFor(ROLES.admin))
    await user.click(trigger())
    expect(screen.getByRole('button', { name: 'common.account' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('button', { name: 'common.settings' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('button', { name: 'shell.lock' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('button', { name: 'shell.signOut' })).toHaveFocus()
    await user.keyboard('{ArrowUp}{ArrowUp}')
    await user.keyboard('{Enter}')
    expect(screen.getByTestId('where')).toHaveTextContent('/settings')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('offers the language on a phone, the bar having no room for it, by the account path', async () => {
    const user = setup()
    await user.click(trigger())
    const select = screen.getByRole('combobox', { name: 'settings.language' })
    expect(select.closest('#user-menu')).not.toBeNull()
    expect(select).toHaveValue('fr')
    expect([...select.options].map(o => o.textContent)).toEqual(['English', 'Français', 'Deutsch', 'Español', 'Italiano', 'Português', 'Українська', 'Русский', '中文', '日本語'])
    await user.selectOptions(select, 'ja')
    expect(i18n.changeLanguage).toHaveBeenCalledWith('ja')
    expect(persistPreference).toHaveBeenCalledWith('language', 'ja')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('signs out then goes to the login page', async () => {
    const user = setup()
    await user.click(trigger())
    await user.click(screen.getByRole('button', { name: 'shell.signOut' }))
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
    await user.click(screen.getByRole('button', { name: 'common.account' }))
    expect(screen.getByTestId('where')).toHaveTextContent('/account')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('after a reload, names the real method and its provider, the second factors and both deadlines', async () => {
    auth.method = 'session'
    getCurrentUser.mockResolvedValue({ data: {
      auth_method: 'sso', auth_provider: 'Company SSO', session_timeout: 1800,
      mfa: { enabled: true, methods: ['totp', 'webauthn'] },
      session: { idle_timeout_s: 900, expires_at: '2026-11-23T08:00:00Z' },
    } })
    const user = setup()
    await user.click(trigger())
    const facts = document.querySelector('.user-id > dl.kv')
    await waitFor(() => expect([...facts.querySelectorAll('dt')].map(dt => dt.textContent))
      .toEqual(['shell.userCard.signIn', 'shell.userCard.mfa', 'shell.userCard.session']))
    // One value per term: the end of the session under its lock delay, in the same value cell (no dd of its own)
    const values = [...facts.querySelectorAll('dd')].map(dd => dd.firstChild.textContent)
    expect(values).toEqual([
      'shell.userCard.methodVia|shell.method.sso,Company SSO',
      'shell.userCard.mfaOn|shell.mfaMethod.totp, shell.method.webauthn',
      'shell.userCard.lockIn|15',
    ])
    const session = facts.querySelectorAll(':scope > .row')[2]
    expect(session.querySelector('dd.v > .sub').textContent).toMatch(/^shell\.userCard\.endsAt\|.*2026/)
  })

  it('says the second factor is off, and reads the facts again at each opening', async () => {
    getCurrentUser.mockResolvedValue({ data: { auth_method: 'password', mfa: { enabled: false, methods: [] }, session_timeout: 1800 } })
    const user = setup()
    await user.click(trigger())
    // Off is a neutral state, not a value
    expect(await screen.findByText('shell.userCard.mfaOff')).toBeVisible()
    expect(screen.getByText('shell.userCard.mfaOff').closest('.badge')).toHaveClass('muted')
    await user.keyboard('{Escape}')
    getCurrentUser.mockResolvedValue({ data: { auth_method: 'password', mfa: { enabled: true, methods: ['totp'] }, session_timeout: 1800 } })
    await user.click(trigger())
    expect(await screen.findByText('shell.userCard.mfaOn|shell.mfaMethod.totp')).toBeVisible()
    expect(getCurrentUser).toHaveBeenCalledTimes(2)
  })

  it('locks the session from the menu, by hand', async () => {
    const user = setup()
    await user.click(trigger())
    const entry = screen.getByRole('button', { name: 'shell.lock' })
    expect(entry).toHaveAttribute('aria-keyshortcuts', 'Alt+Shift+L')
    await user.click(entry)
    expect(lock).toHaveBeenCalledWith('manual')
    expect(logout).not.toHaveBeenCalled()
  })

  it('locks on Alt+Shift+L outside a text field, the menu closed', async () => {
    const user = setup()
    await user.keyboard('{Alt>}{Shift>}L{/Shift}{/Alt}')
    expect(lock).toHaveBeenCalledWith('manual')
  })

  it('leaves Alt+Shift+L to a text field, and other combinations alone', async () => {
    const user = setup()
    const field = document.createElement('input')
    document.body.appendChild(field)
    field.focus()
    await user.keyboard('{Alt>}{Shift>}L{/Shift}{/Alt}')
    field.remove()
    await user.keyboard('{Control>}{Shift>}L{/Shift}{/Control}')
    await user.keyboard('{Alt>}L{/Alt}')
    expect(lock).not.toHaveBeenCalled()
  })
})
