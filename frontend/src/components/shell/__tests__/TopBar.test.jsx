/** The bar's landmarks, names, tab order, search entry, expiry badge and phone picker. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
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
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), resolvedMode: 'dark', themes: [] }),
}))
vi.mock('../../../services/dashboard.service', () => ({ dashboardService: { getQueue: vi.fn().mockResolvedValue({ data: { items: [] } }) } }))
vi.mock('../../../services/audit.service', () => ({ default: { getLogs: vi.fn().mockResolvedValue({ data: [] }) } }))
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

  it('shows pinned modules after Activity and before Modules, in stored order', () => {
    setup({ pins: ['users', 'reports'], activeId: 'reports' })
    const nav = screen.getByRole('navigation', { name: 'shell.mainNav' })
    const order = within(nav).getAllByRole('link').map(a => a.getAttribute('data-module'))
    expect(order.slice(0, 6)).toEqual(['dashboard', 'certificates', 'cas', 'audit', 'users', 'reports'])
    const reports = within(nav).getAllByRole('link').find(a => a.getAttribute('data-module') === 'reports')
    expect(reports).toHaveAttribute('aria-current', 'page')
  })

  it('names the main pages with the bar words, Activity leading to the audit journal', () => {
    setup({ activeId: 'audit' })
    const nav = screen.getByRole('navigation', { name: 'shell.mainNav' })
    const links = within(nav).getAllByRole('link')
    expect(links.slice(0, 4).map(a => a.textContent)).toEqual(['shell.bar.dashboard', 'shell.bar.certificates', 'shell.bar.cas', 'shell.bar.activity'])
    const activity = links.find(a => a.getAttribute('data-module') === 'audit')
    expect(activity).toHaveAttribute('href', '/audit')
    expect(activity).toHaveAttribute('aria-current', 'page')
  })

  it('shows Activity only to who may read the journal', () => {
    setup({ permissions: ROLES.operator })
    const nav = screen.getByRole('navigation', { name: 'shell.mainNav' })
    expect(within(nav).getAllByRole('link').map(a => a.getAttribute('data-module'))).not.toContain('audit')
  })

  it('tabs through the bar in reading order: brand, pages, pins, Modules, search, theme, bell, help, account', async () => {
    const { user } = setup({ pins: ['users'] })
    const seen = []
    for (let i = 0; i < 13; i++) {
      await user.tab()
      const el = document.activeElement
      seen.push(el.getAttribute('data-module') || el.getAttribute('aria-label') || el.textContent.trim())
    }
    // The phone picker is display:none on desktop (CSS, not applied in jsdom)
    expect(seen.filter(l => l !== 'shell.navigate')).toEqual([
      'UCM', 'dashboard', 'certificates', 'cas', 'audit', 'users',
      'shell.modules', 'shell.search', 'shell.theme.label', 'shell.bell.label', 'common.help',
      'shell.accountLabel|probe',
    ])
  })

  it('has no live connection indicator: it sits in the status bar', () => {
    setup()
    expect(screen.queryByTestId('ws')).toBeNull()
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

  it('lists on the phone picker the main pages, then the same modules as the menu', async () => {
    setup({ permissions: ROLES.auditor })
    const picker = screen.getByRole('combobox', { name: 'shell.navigate' })
    const optionIds = within(picker).getAllByRole('option', { hidden: true }).map(o => o.getAttribute('value'))
    expect(optionIds.slice(0, 4)).toEqual(['dashboard', 'certificates', 'cas', 'audit'])
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /shell\.modules$/ }))
    const menuIds = within(screen.getByRole('navigation', { name: 'shell.modulesMenuLabel' }))
      .getAllByRole('link').map(a => a.getAttribute('data-module'))
    expect(optionIds.slice(4).sort()).toEqual(menuIds.sort())
  })

  it('navigates from the phone picker', async () => {
    const { user } = setup()
    await user.selectOptions(screen.getByRole('combobox', { name: 'shell.navigate' }), 'audit')
    expect(screen.getByTestId('where')).toHaveTextContent('/audit')
  })
})

describe('TopBar expiry badge', () => {
  const certLink = () => screen.getAllByRole('link').find(a => a.getAttribute('data-module') === 'certificates')

  it('shows the count on the Certificates link, says it, and dismisses it once the link is followed', async () => {
    getStats.mockResolvedValue({ data: { expiring: 3, expired: 2 } })
    const { user } = setup()
    await waitFor(() => expect(document.querySelector('.nav-count')).toHaveTextContent('5'))
    expect(certLink()).toContainElement(document.querySelector('.nav-count'))
    expect(certLink()).toHaveTextContent('shell.expiringCount')
    await user.click(certLink())
    expect(document.querySelector('.nav-count')).toBeNull()
    expect(JSON.parse(localStorage.getItem('ucm_badge_dismissed')).count).toBe(5)
  })

  it('adds no tab stop: the count is part of its link', async () => {
    getStats.mockResolvedValue({ data: { expiring: 1, expired: 0 } })
    setup()
    await waitFor(() => expect(document.querySelector('.nav-count')).toHaveTextContent('1'))
    expect(screen.queryByRole('button', { name: /expiring/ })).toBeNull()
    expect(document.querySelector('.nav-count')).toHaveAttribute('aria-hidden', 'true')
  })

  // jsdom has no layout: the cascade of the real stylesheet is what it can check
  it('keeps the count out of the link geometry: over the link, above its label, no pointer', async () => {
    const sheets = ['src/styles/atelier/scope.css', 'src/styles/atelier/maquette.css', 'src/components/shell/shell.css'].map((f) => {
      const sheet = document.createElement('style')
      sheet.textContent = readFileSync(resolve(process.cwd(), f), 'utf8')
      document.head.appendChild(sheet)
      return sheet
    })
    try {
      getStats.mockResolvedValue({ data: { expiring: 30, expired: 2 } })
      const user = userEvent.setup()
      render(<MemoryRouter><div className="atl"><TopBar can={canFor(ROLES.admin)} pins={[]} activeId="certificates" hasHelp onOpenSearch={vi.fn()} onOpenHelp={vi.fn()} onTogglePin={vi.fn()} /></div></MemoryRouter>)
      void user
      await waitFor(() => expect(document.querySelector('.nav-count')).toHaveTextContent('32'))
      const badge = document.querySelector('.nav-count')
      const style = getComputedStyle(badge)
      expect(style.position).toBe('absolute')
      expect(style.pointerEvents).toBe('none')
      expect(badge.parentElement).toBe(certLink())
      expect(getComputedStyle(certLink()).position).toBe('relative')
      // In the 61 px bar the 12 px label is centred from 23 px down: the count ends above it
      expect(parseFloat(style.top) + parseFloat(style.height)).toBeLessThanOrEqual(22)
      // The link keeps the padding of every bar link, the underline its symmetric insets
      expect(getComputedStyle(certLink()).paddingRight).toBe(getComputedStyle(certLink()).paddingLeft)
    } finally {
      sheets.forEach((s) => s.remove())
    }
  })

  it('has no badge when nothing expires', async () => {
    setup()
    await Promise.resolve()
    expect(document.querySelector('.nav-count')).toBeNull()
  })
})
