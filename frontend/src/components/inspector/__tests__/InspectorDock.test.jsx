/**
 * The inspector dock: one region for every object opened for detail, with
 * object tabs, section tabs, a focus that goes in and comes back, Escape, a
 * keyboard-resizable grip and a position kept as a user preference.
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
vi.mock('../../detail/CertificatePanel', () => ({
  CertificatePanel: ({ certificate, section }) => <div data-testid="panel">{`${certificate.common_name}:${section}`}</div>,
}))

import { InspectorProvider, useInspector } from '../../../contexts/InspectorContext'
import { applyServerPreferences, setAuthenticated } from '../../../stores/userPreferencesStore'
import { InspectorDock } from '../InspectorDock'

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
    expect(await screen.findByText('one.example.com:overview')).toBeInTheDocument()
    expect(screen.getAllByRole('tablist')).toHaveLength(2)
    const objectTab = screen.getByRole('tab', { name: 'one.example.com' })
    expect(objectTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('tabpanel').length).toBeGreaterThan(0)
  })

  it('maps the section tabs onto the panel section', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:overview')
    fireEvent.click(screen.getByRole('tab', { name: 'inspector.sections.chain' }))
    expect(screen.getByText('one.example.com:chain')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'inspector.sections.chain' })).toHaveAttribute('aria-selected', 'true')
    // No history tab: the API has no history to show
    expect(screen.queryByRole('tab', { name: /history/i })).toBeNull()
  })

  it('moves the focus to the active tab, then gives it back to the opener on close', async () => {
    renderDock()
    const opener = screen.getByText('open-1')
    opener.focus()
    fireEvent.click(opener)
    await screen.findByText('one.example.com:overview')
    await waitFor(() => expect(screen.getByRole('tab', { name: 'one.example.com' })).toHaveFocus())
    fireEvent.keyDown(screen.getByRole('tab', { name: 'one.example.com' }), { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('closes only the active object on Escape and opens many', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:overview')
    fireEvent.click(screen.getByText('open-2'))
    await screen.findByText('two.example.com:overview')
    expect(await screen.findByRole('tab', { name: 'two.example.com' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'two.example.com' }), { key: 'Escape' })
    await screen.findByText('one.example.com:overview')
    expect(screen.queryByRole('tab', { name: 'two.example.com' })).toBeNull()
  })

  it('keeps the focus in the dock when one of two objects closes, then returns it to the opener', async () => {
    renderDock()
    const opener = screen.getByText('open-1')
    opener.focus()
    fireEvent.click(opener)
    await screen.findByText('one.example.com:overview')
    const second = screen.getByText('open-2')
    second.focus()
    fireEvent.click(second)
    await screen.findByText('two.example.com:overview')
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
    await screen.findByText('one.example.com:overview')
    const close = screen.getByRole('button', { name: 'inspector.close' })
    close.focus()
    fireEvent.click(close)
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('reserves its room on the root while open, bottom then right, and releases it', async () => {
    const root = document.documentElement.style
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByTestId('inspector-dock')
    expect(root.getPropertyValue('--inspector-reserve-bottom')).toBe('380px')
    expect(root.getPropertyValue('--inspector-reserve-right')).toBe('0px')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockRight' }))
    await waitFor(() => expect(root.getPropertyValue('--inspector-reserve-right')).toBe('520px'))
    expect(root.getPropertyValue('--inspector-reserve-bottom')).toBe('0px')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.close' }))
    await waitFor(() => expect(root.getPropertyValue('--inspector-reserve-right')).toBe(''))
    expect(root.getPropertyValue('--inspector-reserve-bottom')).toBe('')
  })

  it('closes an object from its own close button', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:overview')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.closeTab' }))
    expect(screen.queryByTestId('inspector-dock')).toBeNull()
  })

  it('keeps the focus in the dock when an inactive object closes from its own button', async () => {
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:overview')
    fireEvent.click(screen.getByText('open-2'))
    await screen.findByText('two.example.com:overview')
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
    expect(Number(grip.getAttribute('aria-valuenow'))).toBe(before + 24)
    expect(JSON.parse(localStorage.getItem('ucm-inspector-prefs')).height).toBe(before + 24)
    for (let i = 0; i < 100; i++) fireEvent.keyDown(grip, { key: 'ArrowDown' })
    expect(Number(grip.getAttribute('aria-valuenow'))).toBe(Number(grip.getAttribute('aria-valuemin')))
  })

  it('is a full-screen modal dialog on mobile', async () => {
    env.mobile = true
    renderDock()
    fireEvent.click(screen.getByText('open-1'))
    const dock = await screen.findByTestId('inspector-dock')
    expect(dock).toHaveAttribute('role', 'dialog')
    expect(dock).toHaveAttribute('aria-modal', 'true')
    expect(screen.queryByTestId('inspector-grip')).toBeNull()
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
    expect(grip).toHaveAttribute('aria-valuenow', '380')
  })

  it('closes everything on sign-out', async () => {
    const { rerender } = renderDock()
    fireEvent.click(screen.getByText('open-1'))
    await screen.findByText('one.example.com:overview')
    env.authenticated = false
    rerender(<InspectorProvider><Opener /><InspectorDock /></InspectorProvider>)
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
  })
})
