/** Account menu of the mockup: identity, method and lock, My account, Sign out; no language, no Settings. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

const logout = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const getCurrentUser = vi.hoisted(() => vi.fn())
const auth = vi.hoisted(() => ({ method: 'password' }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => { const { defaultValue: _defaultValue, ...v } = o || {}; return Object.keys(v).length ? `${k}|${Object.values(v).join(',')}` : k }, i18n: { language: 'fr-FR' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'probe', role: 'operator' }, logout, authMethod: auth.method }),
}))
vi.mock('../../../services/auth.service', () => ({ authService: { getCurrentUser } }))

import { UserMenu } from '../UserMenu'

function Where() { return <output data-testid="where">{useLocation().pathname}</output> }

function setup() {
  const user = userEvent.setup()
  render(
    <MemoryRouter initialEntries={['/certificates']}>
      <UserMenu />
      <Routes><Route path="*" element={<Where />} /></Routes>
    </MemoryRouter>
  )
  return user
}
const trigger = () => screen.getByRole('button', { name: 'shell.accountLabel|probe,common.operator' })

beforeEach(() => {
  vi.clearAllMocks()
  auth.method = 'password'
  getCurrentUser.mockResolvedValue({ data: { session_timeout: 1800 } })
})

describe('UserMenu', () => {
  it('names the account and its role on the button, the name in its tooltip', () => {
    setup()
    expect(trigger()).toHaveAttribute('title', 'probe')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('opens with the name, the role and login, the method and the inactivity lock', async () => {
    const user = setup()
    await user.click(trigger())
    expect(trigger()).toHaveAttribute('aria-expanded', 'true')
    const id = document.querySelector('.user-id')
    expect(id.querySelector('strong')).toHaveTextContent('probe')
    expect(id.querySelector('.mono')).toHaveTextContent('probe')
    expect(id).toHaveTextContent('common.operator · probe')
    expect(await screen.findByText(/shell\.lockAfter\|30/)).toBeVisible()
    expect(screen.getByText(/shell\.signedInWith\|shell\.method\.password/)).toBeVisible()
  })

  it('says only the lock for a session restored from the browser: the server no longer knows the method', async () => {
    auth.method = 'session'
    const user = setup()
    await user.click(trigger())
    expect(await screen.findByText(/shell\.lockAfter\|30/)).toBeVisible()
    expect(screen.queryByText(/shell\.signedInWith/)).toBeNull()
  })

  it('says nothing about a method the session does not know', async () => {
    auth.method = null
    const user = setup()
    await user.click(trigger())
    expect(screen.queryByText(/shell\.signedInWith/)).toBeNull()
  })

  it('has My account and Sign out only: the language and Settings live elsewhere', async () => {
    const user = setup()
    await user.click(trigger())
    const menu = document.getElementById('user-menu')
    const items = [...menu.querySelectorAll('a, button')].map(el => el.textContent)
    expect(items).toEqual(['common.account', 'shell.signOut'])
    expect(screen.queryByRole('group')).toBeNull()
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
})
