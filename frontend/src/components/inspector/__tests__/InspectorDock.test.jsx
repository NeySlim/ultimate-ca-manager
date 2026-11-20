/**
 * The inspector dock: one bordered frame in the page flow for every object opened
 * for detail, with object tabs (overflow in a « +N » menu), a focus that goes in and
 * comes back, Escape, a keyboard-resizable grip, a fold, and a position kept as a
 * user preference.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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
  CertificateDetail: ({ cert, section }) => <div data-testid="panel">{`${cert.common_name}:${section}`}</div>,
}))

import { InspectorProvider, useInspector } from '../../../contexts/InspectorContext'
import { applyServerPreferences, setAuthenticated } from '../../../stores/userPreferencesStore'
import { InspectorDock } from '../InspectorDock'

const CERTS = Object.fromEntries([1, 2, 3, 4, 5, 6].map((i) => [i, { id: i, common_name: `c${i}.example.com` }]))

function Opener() {
  const { openEntity } = useInspector()
  return (
    <>
      {[1, 2, 3, 4, 5, 6].map((i) => <button key={i} onClick={() => openEntity('certificate', i)}>{`open-${i}`}</button>)}
    </>
  )
}

const renderDock = () => render(<InspectorProvider><Opener /><InspectorDock /></InspectorProvider>)
const open = async (i) => {
  fireEvent.click(screen.getByText(`open-${i}`))
  await screen.findByText(`c${i}.example.com:overview`)
}

describe('InspectorDock', () => {
  let widthSpy
  beforeEach(() => {
    vi.clearAllMocks()
    env.mobile = false
    env.authenticated = true
    window.innerWidth = 1600
    window.innerHeight = 1000
    localStorage.clear()
    setAuthenticated(false)
    mocks.certificatesService.getById.mockImplementation((id) => Promise.resolve({ data: CERTS[id] }))
    mocks.updatePreferences.mockResolvedValue({})
  })
  afterEach(() => widthSpy?.mockRestore())

  it('renders nothing until an object is opened', () => {
    renderDock()
    expect(screen.queryByTestId('inspector-dock')).toBeNull()
  })

  it('shows an opened object in a named region with an object tab and a tabpanel', async () => {
    renderDock()
    await open(1)
    const dock = screen.getByTestId('inspector-dock')
    // Certificates only: the region says so
    expect(dock).toHaveAttribute('aria-label', 'inspector.regionCertificate')
    expect(dock).toHaveAttribute('role', 'region')
    const objectTab = screen.getByRole('tab', { name: 'c1.example.com' })
    expect(objectTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel', { name: 'c1.example.com' })).toBeInTheDocument()
  })

  it('sits in the page flow, at the bottom by default, never fixed to the window', async () => {
    renderDock()
    await open(1)
    const dock = screen.getByTestId('inspector-dock')
    expect(dock).toHaveClass('ins-dock', 'is-bottom')
    expect(dock.className).not.toMatch(/fixed|inset-0|bottom-\[/)
    // The mockup band: 278 px high
    expect(dock.style.height).toBe('278px')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockRight' }))
    await waitFor(() => expect(dock).toHaveClass('is-right'))
    expect(dock.style.width).toBe('460px')
    expect(screen.getByTestId('inspector-grip')).toHaveAttribute('aria-orientation', 'vertical')
  })

  it('falls back to the bottom when the window is too narrow for the right dock', async () => {
    localStorage.setItem('ucm-inspector-prefs', JSON.stringify({ position: 'right' }))
    window.innerWidth = 1300
    renderDock()
    await open(1)
    expect(screen.getByTestId('inspector-dock')).toHaveClass('is-bottom')
    expect(screen.queryByRole('button', { name: 'inspector.dockRight' })).toBeNull()
  })

  it('moves the focus to the active tab, then gives it back to the opener on close', async () => {
    renderDock()
    const opener = screen.getByText('open-1')
    opener.focus()
    await open(1)
    await waitFor(() => expect(screen.getByRole('tab', { name: 'c1.example.com' })).toHaveFocus())
    fireEvent.keyDown(screen.getByRole('tab', { name: 'c1.example.com' }), { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('closes the whole inspector on Escape from anywhere on the page, and gives the focus back', async () => {
    renderDock()
    const opener = screen.getByText('open-1')
    opener.focus()
    await open(1)
    await open(2)
    expect(screen.getByRole('tab', { name: 'c2.example.com' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(document.body, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('leaves Escape to an open dialog or to a key already handled', async () => {
    renderDock()
    await open(1)
    const modal = document.createElement('div')
    modal.setAttribute('role', 'dialog')
    modal.setAttribute('aria-modal', 'true')
    document.body.appendChild(modal)
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(screen.getByTestId('inspector-dock')).toBeInTheDocument()
    modal.remove()
    const handled = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    handled.preventDefault()
    document.body.dispatchEvent(handled)
    expect(screen.getByTestId('inspector-dock')).toBeInTheDocument()
  })

  it('still closes on Escape while a closed menu of the shell stays mounted, hidden', async () => {
    renderDock()
    await open(1)
    const wrap = document.createElement('div')
    wrap.hidden = true
    wrap.innerHTML = '<div role="menu"></div>'
    const menu = document.createElement('div')
    menu.setAttribute('role', 'menu')
    menu.hidden = true
    document.body.append(menu, wrap)
    try {
      fireEvent.keyDown(document.body, { key: 'Escape' })
      await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    } finally {
      menu.remove()
      wrap.remove()
    }
  })

  it('closes the focused object tab with the Delete key', async () => {
    renderDock()
    await open(1)
    await open(2)
    const tab = screen.getByRole('tab', { name: 'c2.example.com' })
    fireEvent.keyDown(tab, { key: 'Delete' })
    await waitFor(() => expect(screen.queryByRole('tab', { name: 'c2.example.com' })).toBeNull())
    expect(screen.getByRole('tab', { name: 'c1.example.com' })).toHaveAttribute('aria-selected', 'true')
  })

  it('moves between object tabs with the arrow keys', async () => {
    renderDock()
    await open(1)
    await open(2)
    fireEvent.keyDown(screen.getByRole('tab', { name: 'c2.example.com' }), { key: 'ArrowLeft' })
    await screen.findByText('c1.example.com:overview')
    expect(screen.getByRole('tab', { name: 'c1.example.com' })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps the focus in the dock when one of two objects closes, then returns it to the opener', async () => {
    renderDock()
    const opener = screen.getByText('open-1')
    opener.focus()
    await open(1)
    const second = screen.getByText('open-2')
    second.focus()
    await open(2)
    await waitFor(() => expect(screen.getByRole('tab', { name: 'c2.example.com' })).toHaveFocus())
    fireEvent.keyDown(screen.getByRole('tab', { name: 'c2.example.com' }), { key: 'Delete' })
    await waitFor(() => expect(screen.getByRole('tab', { name: 'c1.example.com' })).toHaveFocus())
    fireEvent.keyDown(screen.getByRole('tab', { name: 'c1.example.com' }), { key: 'Delete' })
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('header close button returns focus to the opener', async () => {
    renderDock()
    const opener = screen.getByText('open-1')
    opener.focus()
    await open(1)
    const close = screen.getByRole('button', { name: 'inspector.close' })
    close.focus()
    fireEvent.click(close)
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('folds to its tab strip and unfolds, and a new opening unfolds it', async () => {
    renderDock()
    await open(1)
    const dock = screen.getByTestId('inspector-dock')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.collapse' }))
    expect(dock).toHaveClass('is-collapsed')
    expect(screen.getByTestId('panel').closest('.ins-body')).toHaveAttribute('hidden')
    expect(screen.queryByTestId('inspector-grip')).toBeNull()
    // The strip stays usable
    expect(screen.getByRole('tab', { name: 'c1.example.com' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'inspector.expand' }))
    expect(dock).not.toHaveClass('is-collapsed')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.collapse' }))
    await open(2)
    expect(dock).not.toHaveClass('is-collapsed')
  })

  it('grows to 420 px, then back to the band', async () => {
    renderDock()
    await open(1)
    const dock = screen.getByTestId('inspector-dock')
    const grow = screen.getByRole('button', { name: 'inspector.grow' })
    expect(grow).toHaveAttribute('title', 'inspector.changeHeight')
    fireEvent.click(grow)
    expect(dock.style.height).toBe('420px')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.shrink' }))
    expect(dock.style.height).toBe('278px')
  })

  it('never shows more than 60 % of a short window', async () => {
    window.innerHeight = 600
    renderDock()
    await open(1)
    fireEvent.click(screen.getByRole('button', { name: 'inspector.grow' }))
    expect(screen.getByTestId('inspector-dock').style.height).toBe('360px')
  })

  it('keeps the close-on-navigate switch out of its header', async () => {
    renderDock()
    await open(1)
    expect(screen.queryByRole('button', { name: 'inspector.closeOnNav' })).toBeNull()
  })

  it('closes an object from its own close button', async () => {
    renderDock()
    await open(1)
    fireEvent.click(screen.getByRole('button', { name: 'inspector.closeTab' }))
    expect(screen.queryByTestId('inspector-dock')).toBeNull()
  })

  it('keeps the focus in the dock when an inactive object closes from its own button', async () => {
    renderDock()
    await open(1)
    await open(2)
    await waitFor(() => expect(screen.getByRole('tab', { name: 'c2.example.com' })).toHaveFocus())
    const closeOne = screen.getAllByRole('button', { name: 'inspector.closeTab' })[0]
    closeOne.focus()
    fireEvent.click(closeOne)
    await waitFor(() => expect(screen.queryByRole('tab', { name: 'c1.example.com' })).toBeNull())
    await waitFor(() => expect(screen.getByRole('tab', { name: 'c2.example.com' })).toHaveFocus())
  })

  it('puts the tabs beyond the strip in a « +N » menu, the active one always shown', async () => {
    // 400 px for six tabs of at least 120 px: two fit beside the « +N » button
    widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function () {
      return this.classList?.contains('ins-tabs-zone') ? 400 : 0
    })
    renderDock()
    for (const i of [1, 2, 3, 4, 5, 6]) await open(i)
    const strip = screen.getByTestId('inspector-object-tabs')
    expect(within(strip).getAllByRole('tab')).toHaveLength(2)
    expect(within(strip).getByRole('tab', { name: 'c6.example.com' })).toHaveAttribute('aria-selected', 'true')
    const more = screen.getByTestId('inspector-tabs-more')
    expect(more).toHaveTextContent('+4')
    // Read out as the mockup: « +4 certificats ouverts non affichés »
    expect(more.querySelector('.sr-only')).toHaveTextContent('inspector.hiddenCertificatesCount')
    expect(more).toHaveAttribute('aria-haspopup', 'menu')
    fireEvent.click(more)
    const menu = screen.getByRole('menu', { name: 'inspector.hiddenCertificatesMenu' })
    // Each hidden certificate says its state beside its name, as in the mockup
    const item = within(menu).getByRole('menuitem', { name: /^c3\.example\.com/ })
    expect(item.querySelector('.lv-pill')).not.toBeNull()
    fireEvent.click(item)
    await screen.findByText('c3.example.com:overview')
    expect(within(strip).getByRole('tab', { name: 'c3.example.com' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('closes a hidden object from the « +N » menu and leaves it with Escape', async () => {
    widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function () {
      return this.classList?.contains('ins-tabs-zone') ? 400 : 0
    })
    renderDock()
    for (const i of [1, 2, 3, 4, 5]) await open(i)
    const more = screen.getByTestId('inspector-tabs-more')
    expect(more).toHaveTextContent('+3')
    fireEvent.click(more)
    fireEvent.click(within(screen.getByRole('menu')).getAllByRole('menuitem', { name: 'inspector.closeTab' })[0])
    await waitFor(() => expect(screen.getByTestId('inspector-tabs-more')).toHaveTextContent('+2'))
    // The menu stays open on the remaining objects
    expect(within(screen.getByRole('menu')).getAllByRole('menuitem', { name: 'inspector.closeTab' })).toHaveLength(2)
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
    // Escape in the menu closes the menu, not the active object
    expect(screen.getByTestId('inspector-dock')).toBeInTheDocument()
  })

  it('resizes from the keyboard within its limits and remembers the size', async () => {
    renderDock()
    await open(1)
    const grip = screen.getByTestId('inspector-grip')
    const before = Number(grip.getAttribute('aria-valuenow'))
    fireEvent.keyDown(grip, { key: 'ArrowUp' })
    expect(Number(grip.getAttribute('aria-valuenow'))).toBe(before + 20)
    expect(JSON.parse(localStorage.getItem('ucm-inspector-prefs')).height).toBe(before + 20)
    for (let i = 0; i < 100; i++) fireEvent.keyDown(grip, { key: 'ArrowDown' })
    expect(grip).toHaveAttribute('aria-valuemin', '210')
    expect(Number(grip.getAttribute('aria-valuenow'))).toBe(210)
    fireEvent.keyDown(grip, { key: 'End' })
    expect(Number(grip.getAttribute('aria-valuenow'))).toBe(450)
  })

  it('is a full-screen modal dialog on mobile', async () => {
    env.mobile = true
    renderDock()
    await open(1)
    const dock = screen.getByTestId('inspector-dock')
    expect(dock).toHaveAttribute('role', 'dialog')
    expect(dock).toHaveAttribute('aria-modal', 'true')
    expect(dock).toHaveClass('is-mobile')
    expect(screen.queryByTestId('inspector-grip')).toBeNull()
    expect(screen.queryByRole('button', { name: 'inspector.collapse' })).toBeNull()
  })

  it('reads the position from the server preference and saves a change', async () => {
    setAuthenticated(true)
    act(() => applyServerPreferences({ inspector: { position: 'right', width: 600 } }))
    renderDock()
    await open(1)
    const grip = screen.getByTestId('inspector-grip')
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
    await open(1)
    const grip = screen.getByTestId('inspector-grip')
    expect(grip).toHaveAttribute('aria-orientation', 'horizontal')
    expect(grip).toHaveAttribute('aria-valuenow', '278')
  })

  it('closes everything on sign-out', async () => {
    const { rerender } = renderDock()
    await open(1)
    env.authenticated = false
    rerender(<InspectorProvider><Opener /><InspectorDock /></InspectorProvider>)
    await waitFor(() => expect(screen.queryByTestId('inspector-dock')).toBeNull())
  })
})
