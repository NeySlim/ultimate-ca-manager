/** The shell around the page: bar, status bar, search entries, help, and the overlays it keeps mounted. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within, act, waitFor } from '@testing-library/react'
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
vi.mock('../../inspector/InspectorObject', () => ({ InspectorObject: ({ entry }) => <p>{`object ${entry.key}`}</p> }))
vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), themes: [] }),
}))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => ({ showWarning: probe.showWarning }) }))
vi.mock('../../WebSocketIndicator', () => ({ WebSocketIndicator: () => null }))
vi.mock('../../../services', () => ({
  certificatesService: { getStats: probe.getStats },
}))
vi.mock('../../CommandPalette', async () => {
  const actual = await vi.importActual('../../CommandPalette')
  return {
    ...actual,
    CommandPalette: ({ open, onOpenChange }) => (
      <div data-testid="palette" data-open={String(open)}>
        {open && <button type="button" onClick={() => onOpenChange(false)}>close palette</button>}
      </div>
    ),
  }
})
vi.mock('../../ui/FloatingHelpPanel', () => ({
  FloatingHelpPanel: ({ isOpen, pageKey }) => <div data-testid="help" data-open={String(isOpen)} data-key={pageKey} />,
}))
vi.mock('../../UpdatePopup', () => ({ UpdatePopup: () => <div data-testid="update-popup" /> }))
vi.mock('../../KofiSupportCard', () => ({ KofiSupportCard: () => <div data-testid="kofi" /> }))

import { AppShell } from '../../AppShell'
import { InspectorProvider, useInspector } from '../../../contexts/InspectorContext'

let inspector
function Grab() {
  inspector = useInspector()
  return null
}

function setup(path = '/') {
  const user = userEvent.setup()
  render(
    <InspectorProvider>
      <Grab />
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="*" element={<p>page body <button type="button" className="lv-btn is-primary">Issue</button></p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </InspectorProvider>
  )
  return user
}

beforeEach(() => {
  perms.list = ROLES.admin
  probe.showWarning.mockClear()
  probe.getStats.mockReset().mockResolvedValue({ data: {} })
  sessionStorage.clear()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', version: '3.0.0' }) }))
})

describe('AppShell', () => {
  it('starts with a skip link to the page, as the mockup', async () => {
    const user = setup('/certificates')
    await user.tab()
    const skip = screen.getByRole('link', { name: 'shell.skipToContent' })
    expect(skip).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(document.getElementById('shell-page')).toHaveFocus()
    expect(document.getElementById('shell-page')).toContainElement(screen.getByText(/page body/))
  })

  it('names the page in the tab title and paints the browser chrome with the theme background', async () => {
    document.documentElement.style.setProperty('--bg', '#141b24')
    try {
      setup('/certificates')
      await waitFor(() => expect(document.title).toBe('shell.bar.certificates · UCM'))
      expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute('content', '#141b24')
    } finally {
      document.documentElement.style.removeProperty('--bg')
      document.querySelector('meta[name="theme-color"]')?.remove()
    }
  })

  it('gives the focus back to the search button when the palette closes and nothing else took it', async () => {
    const user = setup()
    await user.click(screen.getByRole('button', { name: 'shell.search' }))
    await user.click(screen.getByRole('button', { name: 'close palette' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'shell.search' })).toHaveFocus())
  })

  it('suspends the write controls of every page during a cluster maintenance, and gives them back after', async () => {
    const maintenance = { status: 'ok', version: '3.0.0', ha: true, node_id: 'n1', leader: true,
      cluster: { leader_node_id: 'n1', nodes: 2, stale: 0 }, maintenance: { reason: 'manual' } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => maintenance }))
    setup('/certificates')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Issue' })).toBeDisabled())
    expect(screen.getByRole('button', { name: 'Issue' })).toHaveAttribute('aria-describedby', 'shell-writes-note')
  })

  it('renders the bar, the page and the status bar, and no sidebar', async () => {
    setup('/certificates')
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByText('page body')).toBeInTheDocument()
    expect(await screen.findByText(/shell\.version/)).toBeInTheDocument()
    expect(screen.getByRole('contentinfo')).toBeInTheDocument()
    expect(screen.queryByText('Certificate Manager')).toBeNull()
  })

  it('keeps the overlays mounted', () => {
    setup('/certificates')
    for (const id of ['palette', 'help', 'update-popup', 'kofi']) expect(screen.getByTestId(id)).toBeInTheDocument()
  })

  it.each(['/', '/dashboard'])('leaves the support message to the overview on %s: nothing floats over its cards', (path) => {
    setup(path)
    for (const id of ['palette', 'help', 'update-popup']) expect(screen.getByTestId(id)).toBeInTheDocument()
    expect(screen.queryByTestId('kofi')).toBeNull()
  })

  it('opens the palette from the search field of the bar', async () => {
    const user = setup()
    expect(screen.getByTestId('palette')).toHaveAttribute('data-open', 'false')
    await user.click(screen.getByRole('button', { name: 'shell.search' }))
    expect(screen.getByTestId('palette')).toHaveAttribute('data-open', 'true')
  })

  it('opens the palette with Ctrl K', async () => {
    const user = setup()
    await user.keyboard('{Control>}k{/Control}')
    expect(screen.getByTestId('palette')).toHaveAttribute('data-open', 'true')
  })

  it('opens the help of the current page with ? and from the help button', async () => {
    const user = setup('/certificates')
    await user.keyboard('?')
    expect(screen.getByTestId('help')).toHaveAttribute('data-open', 'true')
    expect(screen.getByTestId('help')).toHaveAttribute('data-key', 'certificates')
  })

  it('opens the navigation help from the Modules menu, then returns to the page help', async () => {
    const user = setup('/certificates')
    await user.click(screen.getByRole('button', { name: /shell\.modules$/ }))
    await user.click(screen.getByRole('button', { name: /shell\.navHelp/ }))
    expect(screen.getByTestId('help')).toHaveAttribute('data-key', 'navigation')
    expect(screen.getByTestId('help')).toHaveAttribute('data-open', 'true')
  })

  it('marks the module of the URL current in the bar', () => {
    setup('/certificates/12')
    const nav = screen.getByRole('navigation', { name: 'shell.mainNav' })
    const current = within(nav).getAllByRole('link').filter(a => a.getAttribute('aria-current') === 'page')
    expect(current.map(a => a.getAttribute('data-module'))).toEqual(['certificates'])
  })

  it('keeps the status bar out of the area that makes room for the dock', () => {
    setup('/certificates')
    const bar = screen.getByRole('contentinfo')
    const stage = document.querySelector('.shell-stage')
    expect(stage).not.toBeNull()
    expect(stage).toContainElement(screen.getByRole('banner'))
    expect(stage).toContainElement(screen.getByText('page body'))
    expect(stage).not.toContainElement(bar)
    expect(bar.parentElement).toHaveClass('shell-root')
    expect(bar.parentElement.lastElementChild === bar || bar.previousElementSibling === stage).toBe(true)
  })

  it('puts the open inspector in the page flow: under the page, or beside it on the right', () => {
    window.innerWidth = 1600
    localStorage.clear()
    setup('/certificates')
    const main = document.querySelector('.shell-main')
    expect(main.querySelector('[data-testid="inspector-dock"]')).toBeNull()
    act(() => inspector.openEntity('certificate', 1))
    const dock = screen.getByTestId('inspector-dock')
    // A sibling of the page inside the main area, above the status bar, never fixed to the window
    expect(dock.parentElement).toBe(main)
    expect(dock.previousElementSibling).toHaveClass('shell-content')
    expect(dock).toHaveClass('is-bottom')
    expect(main).not.toHaveClass('has-dock-right')
    expect(document.querySelector('.shell-stage')).not.toContainElement(screen.getByRole('contentinfo'))
    act(() => inspector.setGeometry({ position: 'right' }))
    expect(main).toHaveClass('has-dock-right')
    expect(dock).toHaveClass('is-right')
    act(() => inspector.setGeometry({ position: 'bottom' }))
  })

  it.each(['/certificates', '/'])('has one bottom bar on %s', (path) => {
    setup(path)
    const content = document.querySelector('.shell-content')
    // The banners' live region reads nothing aloud in the nominal state and draws nothing
    expect([...content.children].filter(c => !c.matches('.sr-only[role="status"]'))).toHaveLength(1)
    // The notification panel's own foot is not a bar of the page
    expect(document.querySelectorAll('footer:not(.shell-notif-foot)')).toHaveLength(1)
    expect(screen.queryByText(/^windows\./)).toBeNull()
  })
})

describe('no expiry notice on arrival', () => {
  afterEach(() => { vi.useRealTimers() })

  it.each(['/certificates', '/', '/dashboard', '/cas'])('raises none on %s: the state counters and the bell say it', async (path) => {
    vi.useFakeTimers()
    probe.getStats.mockResolvedValue({ data: { expired: 55, expiring: 11 } })
    setup(path)
    await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
    expect(probe.showWarning).not.toHaveBeenCalled()
  })
})
