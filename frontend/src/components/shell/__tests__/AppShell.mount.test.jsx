/** The shell around the page: bar, status bar, search entries, help, and the overlays it keeps mounted. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ROLES, tStub } from './shellTestUtils'

const perms = vi.hoisted(() => ({ list: ['*'] }))

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
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => ({ showWarning: vi.fn() }) }))
vi.mock('../../WebSocketIndicator', () => ({ WebSocketIndicator: () => null }))
vi.mock('../../../services', () => ({
  certificatesService: { getStats: vi.fn().mockResolvedValue({ data: {} }) },
}))
vi.mock('../../CommandPalette', async () => {
  const actual = await vi.importActual('../../CommandPalette')
  return {
    ...actual,
    CommandPalette: ({ open }) => <div data-testid="palette" data-open={String(open)} />,
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
            <Route path="*" element={<p>page body</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </InspectorProvider>
  )
  return user
}

beforeEach(() => {
  perms.list = ROLES.admin
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', version: '3.0.0' }) }))
})

describe('AppShell', () => {
  it('renders the bar, the page and the status bar, and no sidebar', async () => {
    setup('/certificates')
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByText('page body')).toBeInTheDocument()
    expect(await screen.findByText('shell.version')).toBeInTheDocument()
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
    expect(content.children).toHaveLength(1)
    expect(document.querySelectorAll('footer')).toHaveLength(1)
    expect(screen.queryByText(/^windows\./)).toBeNull()
  })
})
