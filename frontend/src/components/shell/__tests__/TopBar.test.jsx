/** The bar's landmarks, names, tab order, search entry, expiry badge and phone picker. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { ROLES, canFor, tStub } from './shellTestUtils'

const getStats = vi.hoisted(() => vi.fn())
const logout = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tStub, i18n: { language: 'en', changeLanguage: vi.fn() } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'probe', role: 'viewer' }, logout, authMethod: 'password' }),
}))
vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), themes: [] }),
}))
vi.mock('../../WebSocketIndicator', () => ({ WebSocketIndicator: () => <span data-testid="ws" /> }))
vi.mock('../../../services', () => ({ certificatesService: { getStats } }))

import { TopBar } from '../TopBar'

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>
}

function setup({ permissions = ROLES.admin, pins = [], activeId = '', hasHelp = true, ...rest } = {}) {
  const user = userEvent.setup()
  const props = { onOpenSearch: vi.fn(), onOpenHelp: vi.fn(), onTogglePin: vi.fn(), ...rest }
  render(
    <MemoryRouter>
      <TopBar can={canFor(permissions)} pins={pins} activeId={activeId} hasHelp={hasHelp} {...props} />
      <Routes><Route path="*" element={<Where />} /></Routes>
    </MemoryRouter>
  )
  return { user, ...props }
}

beforeEach(() => {
  localStorage.clear()
  getStats.mockReset().mockResolvedValue({ data: { expiring: 0, expired: 0 } })
})

describe('TopBar', () => {
  it('names its landmarks', () => {
    setup()
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'shell.mainNav' })).toBeInTheDocument()
  })

  it('marks the dashboard page current at the root, and only it', () => {
    setup({ activeId: '' })
    const nav = screen.getByRole('navigation', { name: 'shell.mainNav' })
    const current = within(nav).getAllByRole('link').filter(a => a.getAttribute('aria-current') === 'page')
    expect(current.map(a => a.getAttribute('data-module'))).toEqual(['dashboard'])
  })

  it('shows pinned modules after the fixed pages and before Modules, in stored order', () => {
    setup({ pins: ['users', 'audit'], activeId: 'audit' })
    const nav = screen.getByRole('navigation', { name: 'shell.mainNav' })
    const order = within(nav).getAllByRole('link').map(a => a.getAttribute('data-module'))
    expect(order.slice(0, 5)).toEqual(['dashboard', 'certificates', 'cas', 'users', 'audit'])
    const audit = within(nav).getAllByRole('link').find(a => a.getAttribute('data-module') === 'audit')
    expect(audit).toHaveAttribute('aria-current', 'page')
  })

  it('tabs through the bar in reading order: brand, pages, pins, Modules, search, help, account', async () => {
    const { user } = setup({ pins: ['users'] })
    const seen = []
    for (let i = 0; i < 10; i++) {
      await user.tab()
      const el = document.activeElement
      seen.push(el.getAttribute('data-module') || el.getAttribute('aria-label') || el.textContent)
    }
    // The phone picker is display:none on desktop (CSS, not applied in jsdom)
    expect(seen.filter(l => l !== 'shell.navigate')).toEqual([
      'UCM', 'dashboard', 'certificates', 'cas', 'users',
      'shell.modules', 'shell.search', 'common.help', 'common.account: probe',
    ])
  })

  it('opens the search from the bar', async () => {
    const { user, onOpenSearch } = setup()
    await user.click(screen.getByRole('button', { name: 'shell.search' }))
    expect(onOpenSearch).toHaveBeenCalledTimes(1)
  })

  it('shows the help button only when the page has help', async () => {
    const { user, onOpenHelp } = setup()
    await user.click(screen.getByRole('button', { name: 'common.help' }))
    expect(onOpenHelp).toHaveBeenCalledWith()
  })

  it('hides the help button on a page without help', () => {
    setup({ hasHelp: false })
    expect(screen.queryByRole('button', { name: 'common.help' })).toBeNull()
  })

  it('lists on the phone picker the same modules as the menu', async () => {
    setup({ permissions: ROLES.auditor })
    const picker = screen.getByRole('combobox', { name: 'shell.navigate' })
    const optionIds = within(picker).getAllByRole('option', { hidden: true }).map(o => o.getAttribute('value'))
    expect(optionIds[0]).toBe('dashboard')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /shell\.modules$/ }))
    const menuIds = within(screen.getByRole('navigation', { name: 'shell.modulesMenuLabel' }))
      .getAllByRole('link').map(a => a.getAttribute('data-module'))
    expect(optionIds.slice(1).sort()).toEqual(menuIds.sort())
  })

  it('navigates from the phone picker', async () => {
    const { user } = setup()
    await user.selectOptions(screen.getByRole('combobox', { name: 'shell.navigate' }), 'audit')
    expect(screen.getByTestId('where')).toHaveTextContent('/audit')
  })
})

describe('TopBar expiry badge', () => {
  it('shows the count on Certificates and hides it once dismissed', async () => {
    getStats.mockResolvedValue({ data: { expiring: 3, expired: 2 } })
    const { user } = setup()
    const badge = await screen.findByRole('button', { name: /shell\.expiringBadge/ })
    expect(badge).toHaveTextContent('5')
    await user.click(badge)
    expect(screen.queryByRole('button', { name: /shell\.expiringBadge/ })).toBeNull()
    expect(JSON.parse(localStorage.getItem('ucm_badge_dismissed')).count).toBe(5)
  })

  it('has no badge when nothing expires', async () => {
    setup()
    await Promise.resolve()
    expect(screen.queryByRole('button', { name: /shell\.expiringBadge/ })).toBeNull()
  })
})
