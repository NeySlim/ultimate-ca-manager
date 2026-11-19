/**
 * The inspector dock: one frame in the flow of the page for every object opened for
 * detail, under the page or beside it, with object tabs, a focus that goes in and comes
 * back, Escape, a grip, a fold, two sizes and a position kept as a user preference.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const env = vi.hoisted(() => ({ mobile: false, authenticated: true }))
const mocks = vi.hoisted(() => ({
  certificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  updatePreferences: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() }),
  useMobile: () => ({ isMobile: env.mobile }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: env.mobile }) }))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: env.authenticated, permissions: ['read:certificates', 'write:certificates', 'delete:certificates'] }),
}))
vi.mock('../../../services', () => ({
  certificatesService: mocks.certificatesService,
  casService: { getById: vi.fn() },
  userCertificatesService: { getById: vi.fn() },
  truststoreService: { getById: vi.fn() },
}))
vi.mock('../../../services/account.service', () => ({ accountService: { updatePreferences: mocks.updatePreferences } }))
vi.mock('../certificate/CertificateDetail', () => ({
  CertificateDetail: ({ title, layout }) => <div data-testid="panel" data-layout={layout}>{`${title}:detail`}</div>,
}))

import { InspectorProvider, useInspector } from '../../../contexts/InspectorContext'
import { applyServerPreferences, setAuthenticated } from '../../../stores/userPreferencesStore'
import { InspectorDock, InspectorStage } from '../InspectorDock'

const CERTS = { 1: { id: 1, common_name: 'one.example.com' }, 2: { id: 2, common_name: 'two.example.com' } }

function Opener() {
  const { openEntity } = useInspector()
  return (
    <>
      <button onClick={() => openEntity('certificate', 1)}>open-1</button>
      <button onClick={() => openEntity('certificate', 2)}>open-2</button>
    </>
  )
}

const renderDock = () => render(<InspectorProvider><Opener /><InspectorDock /></InspectorProvider>)
const renderStage = () => render(
  <InspectorProvider><InspectorStage><main data-testid="page"><Opener /></main></InspectorStage></InspectorProvider>)

describe('InspectorDock', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    env.mobile = false
    env.authenticated = true
    window.innerWidth = 1600
    window.innerHeight = 900
    localStorage.clear()
    setAuthenticated(false)
    mocks.certificatesService.getById.mockImplementation((id) => Promise.resolve({ data: CERTS[id] }))
    mocks.updatePreferences.mockResolvedValue({})
  })

  it('renders nothing until an object is opened', () => {
    renderDock()
    expect(screen.queryByTestId('inspector-dock')).toBeNull()
  })

  it('shows an opened object in a named region with tabs and a tabpanel', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    const dock = await screen.findByTestId('inspector-dock')
    expect(dock).toHaveAttribute('aria-label', 'inspector.region')
    expect(await screen.findByText('one.example.com:detail')).toBeInTheDocument()
    expect(screen.getAllByRole('tablist')).toHaveLength(1)
    const objectTab = screen.getByRole('tab', { name: 'one.example.com' })
    expect(objectTab).toHaveAttribute('aria-selected', 'true')
  })

  it('moves the focus to the active tab, then gives it back to the opener on close', async () => {
    renderDock()
    const opener = screen.getByText('open-1')
    opener.focus()
    fireEvent.click(opener)
    await screen.findByText('one.example.com:detail')
    await waitFor(() => expect(screen.getByRole('tab', { name: 'one.example.com' })).toHaveFocus())
    fireEvent.keyDown(screen.getByRole('tab', { name: 'one.example.com' }), { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('closes only the active object on Escape and opens many', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:detail')
    fireEvent.click(screen.getByText('open-2'))
    await screen.findByText('two.example.com:detail')
    expect(await screen.findByRole('tab', { name: 'two.example.com' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'two.example.com' }), { key: 'Escape' })
    await screen.findByText('one.example.com:detail')
    expect(screen.queryByRole('tab', { name: 'two.example.com' })).toBeNull()
  })

  it('keeps the focus in the dock when one of two objects closes, then returns it to the opener', async () => {
    renderDock()
    const opener = screen.getByText('open-1')
    opener.focus()
    fireEvent.click(opener)
    await screen.findByText('one.example.com:detail')
    const second = screen.getByText('open-2')
    second.focus()
    fireEvent.click(second)
    await screen.findByText('two.example.com:detail')
    await waitFor(() => expect(screen.getByRole('tab', { name: 'two.example.com' })).toHaveFocus())
    fireEvent.keyDown(screen.getByRole('tab', { name: 'two.example.com' }), { key: 'Escape' })
    await waitFor(() => expect(screen.getByRole('tab', { name: 'one.example.com' })).toHaveFocus())
    fireEvent.keyDown(screen.getByRole('tab', { name: 'one.example.com' }), { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('header close button returns focus to the opener', async () => {
    renderDock()
    const opener = screen.getByText('open-1')
    opener.focus()
    fireEvent.click(opener)
    await screen.findByText('one.example.com:detail')
    const close = screen.getByRole('button', { name: 'inspector.close' })
    close.focus()
    fireEvent.click(close)
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('stands in the flow after the page, at the height it keeps, and reserves nothing on the root', async () => {
    renderStage()
    const stage = screen.getByTestId('page').parentElement
    expect(stage).toHaveClass('insp-stage')
    expect(stage.children).toHaveLength(1)
    fireEvent.click(screen.getByText('open-1'))
    const dock = await screen.findByTestId('inspector-dock')
    expect(dock.parentElement).toBe(stage)
    expect(dock.previousElementSibling).toBe(screen.getByTestId('page'))
    expect(dock).toHaveClass('insp', 'is-bottom')
    expect(dock.style.getPropertyValue('--insp-h')).toBe('278px')
    expect(stage).not.toHaveClass('is-right')
    expect(document.documentElement.style.getPropertyValue('--inspector-reserve-bottom')).toBe('')
  })

  it('goes beside the page when docked on the right, and back under it in a narrow window', async () => {
    renderStage()
    const stage = screen.getByTestId('page').parentElement
    fireEvent.click(screen.getByText('open-1'))
    const dock = await screen.findByTestId('inspector-dock')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockRight' }))
    await waitFor(() => expect(stage).toHaveClass('is-right'))
    expect(dock).toHaveClass('is-right')
    expect(dock.style.getPropertyValue('--insp-w')).toBe('460px')
    expect(screen.getByTestId('inspector-grip')).toHaveAttribute('aria-orientation', 'vertical')
    act(() => { window.innerWidth = 1300; window.dispatchEvent(new Event('resize')) })
    expect(stage).not.toHaveClass('is-right')
    expect(dock).toHaveClass('is-bottom')
    expect(screen.queryByRole('button', { name: 'inspector.dockRight' })).toBeNull()
  })

  it('lays the object out in columns under the page and in one column beside it', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    expect(await screen.findByTestId('panel')).toHaveAttribute('data-layout', 'columns')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockRight' }))
    await waitFor(() => expect(screen.getByTestId('panel')).toHaveAttribute('data-layout', 'column'))
  })

  it('folds to its strip of tabs and unfolds from the button, a tab or a new opening', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:detail')
    const dock = screen.getByTestId('inspector-dock')
    const fold = screen.getByRole('button', { name: 'inspector.fold' })
    expect(fold).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(fold)
    expect(dock).toHaveClass('is-collapsed')
    expect(screen.queryByTestId('panel')).toBeNull()
    expect(screen.getByRole('tab', { name: 'one.example.com' })).toBeInTheDocument()
    const unfold = screen.getByRole('button', { name: 'inspector.unfold' })
    expect(unfold).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(unfold)
    expect(dock).not.toHaveClass('is-collapsed')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.fold' }))
    fireEvent.click(screen.getByRole('tab', { name: 'one.example.com' }))
    expect(dock).not.toHaveClass('is-collapsed')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.fold' }))
    fireEvent.click(screen.getByText('open-2'))
    await screen.findByText('two.example.com:detail')
    expect(dock).not.toHaveClass('is-collapsed')
  })

  it('switches between its two sizes from the size button', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    const grip = await screen.findByTestId('inspector-grip')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.grow' }))
    expect(grip).toHaveAttribute('aria-valuenow', '420')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.shrink' }))
    expect(grip).toHaveAttribute('aria-valuenow', '278')
  })

  it('switches close on navigate from its header and remembers it', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:detail')
    const toggle = screen.getByRole('button', { name: 'inspector.closeOnNav' })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    expect(JSON.parse(localStorage.getItem('ucm-inspector-prefs')).closeOnNav).toBe(false)
    // The dock stays open and the focus stays on the switch
    expect(screen.getByTestId('inspector-dock')).toBeInTheDocument()
  })

  it('closes an object from its own close button', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:detail')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.closeTab' }))
    expect(screen.queryByTestId('inspector-dock')).toBeNull()
  })

  it('closes the tab under the focus with the Delete key', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:detail')
    fireEvent.click(screen.getByText('open-2'))
    await screen.findByText('two.example.com:detail')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'two.example.com' }), { key: 'Delete' })
    await waitFor(() => expect(screen.queryByRole('tab', { name: 'two.example.com' })).toBeNull())
    expect(screen.getByRole('tab', { name: 'one.example.com' })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps the focus in the dock when an inactive object closes from its own button', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:detail')
    fireEvent.click(screen.getByText('open-2'))
    await screen.findByText('two.example.com:detail')
    await waitFor(() => expect(screen.getByRole('tab', { name: 'two.example.com' })).toHaveFocus())
    const closeOne =screen.getAllByRole('button', { name: 'inspector.closeTab' })[0]
    closeOne.focus()
    fireEvent.click(closeOne)
    await waitFor(() => expect(screen.queryByRole('tab', { name: 'one.example.com' })).toBeNull())
    await waitFor(() => expect(screen.getByRole('tab', { name: 'two.example.com' })).toHaveFocus())
  })

  it('resizes from the keyboard within its limits and remembers the size', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    const grip = await screen.findByTestId('inspector-grip')
    const before = Number(grip.getAttribute('aria-valuenow'))
    fireEvent.keyDown(grip, { key: 'ArrowUp' })
    expect(Number(grip.getAttribute('aria-valuenow'))).toBe(before + 20)
    expect(JSON.parse(localStorage.getItem('ucm-inspector-prefs')).height).toBe(before + 20)
    for (let i = 0; i < 100; i++) fireEvent.keyDown(grip, { key: 'ArrowDown' })
    expect(Number(grip.getAttribute('aria-valuenow'))).toBe(Number(grip.getAttribute('aria-valuemin')))
    // Bounded like the frame: 210 px at least, 450 px or 60 % of the window at most
    expect(grip).toHaveAttribute('aria-valuemin', '210')
    expect(grip).toHaveAttribute('aria-valuemax', '450')
    fireEvent.keyDown(grip, { key: 'End' })
    expect(grip).toHaveAttribute('aria-valuenow', '450')
    fireEvent.keyDown(grip, { key: 'Home' })
    expect(grip).toHaveAttribute('aria-valuenow', '210')
  })

  it('is a full-screen modal dialog on mobile', async () => {
    env.mobile = true
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    const dock = await screen.findByTestId('inspector-dock')
    expect(dock).toHaveAttribute('role', 'dialog')
    expect(dock).toHaveAttribute('aria-modal', 'true')
    expect(dock).toHaveClass('is-mobile')
    expect(dock).not.toHaveClass('is-bottom')
    expect(screen.queryByTestId('inspector-grip')).toBeNull()
    expect(screen.queryByRole('button', { name: 'inspector.fold' })).toBeNull()
    expect(await screen.findByTestId('panel')).toHaveAttribute('data-layout', 'column')
  })

  it('reads the position from the server preference and saves a change', async () => {
    setAuthenticated(true)
    act(() => applyServerPreferences({ inspector: { position: 'right', width: 600 } }))
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    const grip = await screen.findByTestId('inspector-grip')
    expect(grip).toHaveAttribute('aria-orientation', 'vertical')
    expect(grip).toHaveAttribute('aria-valuenow', '600')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockBottom' }))
    await waitFor(() => expect(mocks.updatePreferences).toHaveBeenCalledWith(
      expect.objectContaining({ inspector: expect.objectContaining({ position: 'bottom' }) })))
    expect(screen.getByTestId('inspector-grip')).toHaveAttribute('aria-orientation', 'horizontal')
  })

  it('ignores an invalid stored geometry', async () => {
    localStorage.setItem('ucm-inspector-prefs', JSON.stringify({ position: 'left', height: 'tall', width: 5 }))
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    const grip = await screen.findByTestId('inspector-grip')
    expect(grip).toHaveAttribute('aria-orientation', 'horizontal')
    expect(grip).toHaveAttribute('aria-valuenow', '278')
  })

  it('closes everything on sign-out', async () => {
    const { rerender } = renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:detail')
    env.authenticated = false
    rerender(<InspectorProvider><Opener /><InspectorDock /></InspectorProvider>)
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
  })
})
