/**
 * The shell's panels, two by two: one open at a time (opening one closes the other), a click outside and
 * Escape close each, and the notifications' cross closes them after another menu was opened.
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ROLES, tStub } from './shellTestUtils'

const perms = vi.hoisted(() => ({ list: ['*'] }))
const probe = vi.hoisted(() => ({ showWarning: vi.fn(), getStats: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tStub, i18n: { language: 'en', changeLanguage: vi.fn() } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { username: 'probe', role: 'admin' }, logout: vi.fn(), permissions: perms.list, authMethod: null, isAuthenticated: true }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), themes: [] }),
}))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => ({ showWarning: probe.showWarning }) }))
vi.mock('../../WebSocketIndicator', () => ({ WebSocketIndicator: () => null }))
vi.mock('../../../services', () => ({
  certificatesService: { getStats: probe.getStats },
  settingsService: { getExpiryAlerts: vi.fn().mockResolvedValue({ data: {} }) },
  acmeService: {}, crlService: {},
}))
vi.mock('../../../services/dashboard.service', () => ({ dashboardService: { getQueue: vi.fn().mockResolvedValue({ data: { items: [] } }) } }))
vi.mock('../../../services/audit.service', () => ({ default: { getLogs: vi.fn().mockResolvedValue({ data: [] }) } }))
vi.mock('../../CommandPalette', async () => {
  const actual = await vi.importActual('../../CommandPalette')
  return {
    ...actual,
    CommandPalette: ({ open, onOpenChange, can, onOpenHelp }) => (
      <div data-testid="palette" data-open={String(open)} data-read-logs={String(!!can?.isAdmin())}
        data-write-certs={String(!!can?.hasPermission('write:certificates'))}>
        {open && <button type="button" onClick={() => onOpenChange(false)}>close palette</button>}
        {open && onOpenHelp && <button type="button" onClick={() => { onOpenChange(false); onOpenHelp() }}>palette help</button>}
      </div>
    ),
  }
})
vi.mock('../../UpdatePopup', () => ({ UpdatePopup: () => <div data-testid="update-popup" /> }))
vi.mock('../../KofiSupportCard', () => ({ KofiSupportCard: () => <div data-testid="kofi" /> }))

import { AppShell } from '../../AppShell'
import { loadEnglishHelp } from '../../../data/helpData'
import { InspectorProvider } from '../../../contexts/InspectorContext'

beforeAll(async () => { await loadEnglishHelp() })
beforeEach(() => {
  perms.list = ROLES.admin
  probe.getStats.mockReset().mockResolvedValue({ data: {} })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', version: '3.0.0' }) }))
})

function setup() {
  const user = userEvent.setup()
  render(
    <InspectorProvider>
      <MemoryRouter initialEntries={['/certificates']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="*" element={<p>page body <button type="button">outside</button></p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </InspectorProvider>
  )
  return user
}

const button = (id) => document.getElementById(id)
const expanded = (id) => () => button(id)?.getAttribute('aria-expanded') === 'true'
// Each panel: how it opens and how it reads open
const PANELS = {
  modules: { open: (u) => u.click(button('modules-button')), isOpen: expanded('modules-button') },
  language: { open: (u) => u.click(button('language-button')), isOpen: expanded('language-button') },
  theme: { open: (u) => u.click(button('theme-button')), isOpen: expanded('theme-button') },
  notifications: { open: (u) => u.click(button('notif-button')), isOpen: expanded('notif-button') },
  account: { open: (u) => u.click(button('user-button')), isOpen: expanded('user-button') },
  help: { open: (u) => u.click(document.querySelector('.help-button')), isOpen: () => !!screen.queryByTestId('help-dialog') },
  palette: { open: (u) => u.click(button('shell-search')), isOpen: () => screen.getByTestId('palette').dataset.open === 'true' },
}
const names = Object.keys(PANELS)
const pairs = names.flatMap((a) => names.filter((b) => b !== a).map((b) => [a, b]))
const POPOVERS = ['modules', 'language', 'theme', 'notifications', 'account']

describe('the panels of the shell', () => {
  it.each(pairs)('opening %s then %s leaves only the second open', async (a, b) => {
    const user = setup()
    await PANELS[a].open(user)
    await waitFor(() => expect(PANELS[a].isOpen()).toBe(true))
    await PANELS[b].open(user)
    await waitFor(() => expect(PANELS[b].isOpen()).toBe(true))
    expect(PANELS[a].isOpen()).toBe(false)
  })

  it.each(POPOVERS)('a click outside closes %s', async (name) => {
    const user = setup()
    await PANELS[name].open(user)
    expect(PANELS[name].isOpen()).toBe(true)
    fireEvent.mouseDown(screen.getByRole('button', { name: 'outside' }))
    expect(PANELS[name].isOpen()).toBe(false)
  })

  it.each(POPOVERS)('Escape closes %s', async (name) => {
    const user = setup()
    await PANELS[name].open(user)
    expect(PANELS[name].isOpen()).toBe(true)
    await user.keyboard('{Escape}')
    expect(PANELS[name].isOpen()).toBe(false)
  })

  it('a click inside the notifications keeps them open; the cross closes them after the theme menu was opened', async () => {
    const user = setup()
    await PANELS.notifications.open(user)
    fireEvent.mouseDown(document.getElementById('notif-title'))
    expect(PANELS.notifications.isOpen()).toBe(true)
    await PANELS.theme.open(user)
    expect(PANELS.notifications.isOpen()).toBe(false)
    await PANELS.notifications.open(user)
    expect(PANELS.theme.isOpen()).toBe(false)
    await user.click(button('notif-close'))
    expect(PANELS.notifications.isOpen()).toBe(false)
    expect(button('notif-button')).toHaveFocus()
  })
})
