/** The shell around the page: bar, status bar, search entries, help, and the overlays it keeps mounted. */
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { lazy, Suspense } from 'react'
import { render, screen, within, act, waitFor, cleanup } from '@testing-library/react'
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
import { helpContent } from '../../../data/helpContent'
import { Zone } from '../../atelier/Zone'
import { resetHealthForTests } from '../health'
import { InspectorProvider, useInspector } from '../../../contexts/InspectorContext'
import { loadEnglishHelp } from '../../../data/helpData'

// The English help is a chunk of its own: loaded once, the dialog opens at once
beforeAll(async () => { await loadEnglishHelp() })

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
            <Route path="/zone" element={<Zone><h1>zone body</h1></Zone>} />
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
    // A page drawn outside the mockup's zones has no #main: the skip link falls back to the page slot
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

  // The mockup's stateBanners() open the page content of a zone; the shell holds them above other pages
  it.each([['/zone', true], ['/certificates', false]])('puts the state banners where the page draws them: %s', async (path, zone) => {
    resetHealthForTests()
    let online = true
    const spy = vi.spyOn(navigator, 'onLine', 'get').mockImplementation(() => online)
    try {
      setup(path)
      act(() => { online = false; window.dispatchEvent(new Event('offline')) })
      const banner = await screen.findByText('shell.offline.title')
      const box = banner.closest('#offline-banner')
      if (zone) {
        expect(box.parentElement).toHaveClass('page-content')
        expect(box.nextElementSibling).toHaveTextContent('zone body')
        expect(document.querySelector('.shell-banners')).toBeNull()
      } else {
        expect(box.closest('.shell-banners')).not.toBeNull()
        expect(box.closest('.atl')).not.toBeNull()
      }
    } finally {
      act(() => { online = true; window.dispatchEvent(new Event('online')) })
      spy.mockRestore()
    }
  })

  it('opens the notification panel after the masthead, as the mockup, not inside it', async () => {
    const user = setup('/certificates')
    await user.click(screen.getByRole('button', { name: /shell\.bell\.label/ }))
    const panel = document.getElementById('notif-panel')
    expect(panel.parentElement).toBe(document.getElementById('notif-slot'))
    expect(document.querySelector('header.masthead')).not.toContainElement(panel)
  })

  it('suspends the write controls of every page during a cluster maintenance, and gives them back after', async () => {
    const maintenance = { status: 'ok', version: '3.0.0', ha: true, node_id: 'n1', leader: true,
      cluster: { leader_node_id: 'n1', nodes: 2, stale: 0 }, maintenance: { reason: 'manual' } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => maintenance }))
    setup('/certificates')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Issue' })).toBeDisabled())
    expect(screen.getByRole('button', { name: 'Issue' })).toHaveAttribute('aria-describedby', 'failover-note')
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
    for (const id of ['palette', 'update-popup', 'kofi']) expect(screen.getByTestId(id)).toBeInTheDocument()
  })

  it.each(['/', '/dashboard'])('leaves the support message to the overview on %s: nothing floats over its cards', (path) => {
    setup(path)
    for (const id of ['palette', 'update-popup']) expect(screen.getByTestId(id)).toBeInTheDocument()
    expect(screen.queryByTestId('kofi')).toBeNull()
  })

  it('opens the palette from the search field of the bar', async () => {
    const user = setup()
    expect(screen.getByTestId('palette')).toHaveAttribute('data-open', 'false')
    await user.click(screen.getByRole('button', { name: 'shell.search' }))
    expect(screen.getByTestId('palette')).toHaveAttribute('data-open', 'true')
  })

  it('hands the account\'s rights to the palette, which lists only what it may open', () => {
    perms.list = ['read:certificates']
    setup()
    expect(screen.getByTestId('palette')).toHaveAttribute('data-read-logs', 'false')
    expect(screen.getByTestId('palette')).toHaveAttribute('data-write-certs', 'false')
    cleanup()
    perms.list = ['*']
    setup()
    expect(screen.getByTestId('palette')).toHaveAttribute('data-read-logs', 'true')
    expect(screen.getByTestId('palette')).toHaveAttribute('data-write-certs', 'true')
  })

  it('opens the palette with Ctrl K', async () => {
    const user = setup()
    await user.keyboard('{Control>}k{/Control}')
    expect(screen.getByTestId('palette')).toHaveAttribute('data-open', 'true')
  })

  // The mockup's help(): its wide modal() with the sections in a .help-grid, not a floating window
  const helpDialog = () => screen.queryByTestId('help-dialog')
  it('opens the help of the current page in the wide dialog with ?, closes it with ? and Back to the console', async () => {
    const user = setup('/certificates')
    expect(helpDialog()).toBeNull()
    await user.keyboard('?')
    const dialog = helpDialog()
    expect(dialog.tagName).toBe('DIALOG')
    expect(dialog).toHaveClass('wide')
    expect(within(dialog).getByRole('heading', { level: 2 })).toHaveTextContent(helpContent.certificates.title)
    expect(dialog.querySelector('.help-grid section h3')).toBeTruthy()
    expect(document.querySelector('.fixed')).toBeNull()
    await user.keyboard('?')
    expect(helpDialog()).toBeNull()
    await user.click(screen.getByRole('button', { name: 'common.help' }))
    await user.click(within(helpDialog()).getByRole('button', { name: 'help.back' }))
    expect(helpDialog()).toBeNull()
  })

  it('opens the navigation help from the Modules menu, then returns to the page help', async () => {
    const user = setup('/certificates')
    await user.click(screen.getByRole('button', { name: /shell\.modules$/ }))
    await user.click(screen.getByRole('button', { name: /shell\.navHelp/ }))
    expect(within(helpDialog()).getByRole('heading', { level: 2 })).toHaveTextContent(helpContent.navigation.title)
    await user.keyboard('?')
    expect(helpDialog()).toBeNull()
    await user.keyboard('?')
    expect(within(helpDialog()).getByRole('heading', { level: 2 })).toHaveTextContent(helpContent.certificates.title)
  })

  it('opens the help of the page from the palette, the way to it on a phone', async () => {
    const user = setup('/certificates')
    await user.click(screen.getByRole('button', { name: 'shell.search' }))
    await user.click(screen.getByRole('button', { name: 'palette help' }))
    expect(screen.getByTestId('palette')).toHaveAttribute('data-open', 'false')
    expect(within(helpDialog()).getByRole('heading', { level: 2 })).toHaveTextContent(helpContent.certificates.title)
  })

  it('marks the module of the URL current in the bar', () => {
    setup('/certificates/12')
    const nav = screen.getByRole('navigation', { name: 'shell.mainNav' })
    const current = within(nav).getAllByRole('link').filter(a => a.getAttribute('aria-current') === 'page')
    expect(current.map(a => a.getAttribute('data-module'))).toEqual(['certificates'])
  })

  it('is the mockup\'s frame: the masthead, the stage, the status bar, the bars under the scope of its rules', () => {
    setup('/certificates')
    const app = document.querySelector('.shell-app')
    const bar = screen.getByRole('contentinfo')
    const masthead = screen.getByRole('banner')
    const main = document.querySelector('.shell-main')
    expect(masthead).toHaveClass('masthead')
    expect(bar).toHaveClass('statusbar')
    // Each bar in a scope of no box of its own; the page slot outside any scope (a page brings its own)
    for (const el of [masthead, bar]) expect(el.parentElement).toHaveClass('atl', 'atl-island')
    expect(main.parentElement).toBe(app)
    expect(main.closest('.atl')).toBeNull()
    expect(main).toContainElement(screen.getByText('page body'))
    expect(main).not.toContainElement(bar)
    // The order of the mockup: masthead, its session banner and notification panel slots, the stage, the status bar
    const order = [masthead, document.getElementById('session-banner-slot'), document.getElementById('notif-slot'), main, bar]
    for (let i = 1; i < order.length; i++) expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('draws no dock of its own: an open object belongs to the dock its zone draws', () => {
    window.innerWidth = 1600
    setup('/certificates')
    act(() => inspector.openEntity('certificate', 1))
    expect(inspector.opened).toHaveLength(1)
    const main = document.querySelector('.shell-main')
    expect([...main.children].map((c) => c.className)).toEqual(['shell-content'])
    expect(document.querySelector('#inspector, [data-testid="inspector-dock"]')).toBeNull()
    act(() => inspector.closeAll())
  })

  it.each(['/certificates', '/'])('has one bottom bar on %s', (path) => {
    setup(path)
    const content = document.querySelector('.shell-content')
    // The banners' place draws nothing in the nominal state: an empty stage, then the page
    expect([...content.children].map(c => c.className)).toEqual(['atl atl-island', 'shell-page'])
    expect(content.querySelector('.shell-banners').textContent).toBe('')
    // The notification panel's own foot is not a bar of the page
    expect(document.querySelectorAll('footer:not(.notif-foot)')).toHaveLength(1)
    expect(screen.queryByText(/^windows\./)).toBeNull()
  })
})

describe('a page whose code is still loading', () => {
  it('waits inside the page area: the bars stay on screen, the application loader does not replace them', async () => {
    let arrive
    const Slow = lazy(() => new Promise((resolve) => { arrive = () => resolve({ default: () => <p>slow page</p> }) }))
    render(
      <InspectorProvider>
        <MemoryRouter initialEntries={['/certificates']}>
          <Suspense fallback={<p>application loader</p>}>
            <Routes>
              <Route element={<AppShell />}>
                <Route path="*" element={<Slow />} />
              </Route>
            </Routes>
          </Suspense>
        </MemoryRouter>
      </InspectorProvider>
    )
    expect(screen.queryByText('application loader')).toBeNull()
    expect(screen.getByRole('banner')).toBeVisible()
    expect(screen.getByRole('contentinfo')).toBeVisible()
    const wait = within(document.getElementById('shell-page')).getByRole('status', { name: 'common.loading' })
    expect(wait).toBeVisible()
    await act(async () => { arrive() })
    expect(await screen.findByText('slow page')).toBeVisible()
    expect(screen.queryByRole('status', { name: 'common.loading' })).toBeNull()
  })
})

describe('following a link to a page whose code is still loading', () => {
  it('marks the link asked for and shows the wait in the page area at once, the bars kept', async () => {
    let arrive
    const Slow = lazy(() => new Promise((resolve) => { arrive = () => resolve({ default: () => <p>activity page</p> }) }))
    const user = userEvent.setup()
    render(
      <InspectorProvider>
        <MemoryRouter initialEntries={['/certificates']}>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/audit" element={<Slow />} />
              <Route path="*" element={<p>certificates page</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </InspectorProvider>
    )
    expect(await screen.findByText('certificates page')).toBeVisible()
    const activity = () => document.querySelector('.main-nav a[data-module="audit"]')
    const before = document.title
    await user.click(activity())
    await waitFor(() => expect(activity()).toHaveAttribute('aria-current', 'page'))
    expect(document.title).not.toBe(before)
    const wait = within(document.getElementById('shell-page')).getByRole('status', { name: 'common.loading' })
    expect(wait).toBeVisible()
    expect(screen.queryByText('certificates page')).toBeNull()
    expect(screen.getByRole('banner')).toBeVisible()
    expect(screen.getByRole('contentinfo')).toBeVisible()
    await act(async () => { arrive() })
    expect(await screen.findByText('activity page')).toBeVisible()
    expect(screen.queryByRole('status', { name: 'common.loading' })).toBeNull()
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
