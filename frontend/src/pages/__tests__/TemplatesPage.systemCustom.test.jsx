/**
 * TemplatesPage — Source is read, not guessed.
 *
 * The list used to label a template "Certificate" or "CA" from a substring
 * match on its name: `name.includes('ca')`. Because "certificate",
 * "smartcard" and "authentication" all contain those two letters, ordinary
 * leaf templates were shown as certificate authorities, with the authority
 * icon and a detail pane that spelled out "Certificate Authority". Nothing
 * in the database ever said so.
 *
 * What replaced it is `is_system`, which the API already returns. These
 * tests pin that contract: if `is_system` stops arriving, or stops driving
 * the column, every row silently reads Custom and every system template
 * gets its Edit and Delete buttons back — which the server answers 403 to.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({ isMobile: false, isDesktop: true, isTouch: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useWindowManager: () => ({
    openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  return {
    usePersistedState: persisted.usePersistedState,
    useCRUDPage: crud.useCRUDPage,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const getAll = vi.fn()
vi.mock('../../services', () => ({
  templatesService: {
    getAll: (...args) => getAll(...args),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    create: vi.fn().mockResolvedValue({ data: {} }),
    update: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}))
vi.mock('../../services/eku.service', () => ({
  ekuService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

import TemplatesPage from '../TemplatesPage'

// The names here are the point: every one of them contains the letters
// "ca", and every one of them is an ordinary leaf template.
const SYSTEM_TEMPLATES = [
  { id: 1, name: 'Web Server Certificate', template_type: 'web_server', is_system: true, validity_days: 397 },
  { id: 2, name: 'Smartcard Logon', template_type: 'smartcard_logon', is_system: true, validity_days: 397 },
  { id: 3, name: 'Client Certificate', template_type: 'client_auth', is_system: true, validity_days: 365 },
]
const CUSTOM_TEMPLATE = { id: 4, name: 'Test Certificate 123', template_type: 'web_server', is_system: false, validity_days: 397 }

const SHOW_SYSTEM_KEY = 'ucm-templates-show-system'

const renderPage = () => render(<MemoryRouter><TemplatesPage /></MemoryRouter>)

const rowFor = async (name) => {
  const cell = await screen.findByText(name)
  return cell.closest('tr')
}

describe('TemplatesPage — Source comes from is_system', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
  })

  it('does not call a leaf template a CA because its name contains "ca"', async () => {
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()

    // The old classifier turned all four of these into "CA".
    for (const tpl of SYSTEM_TEMPLATES) {
      const row = await rowFor(tpl.name)
      expect(within(row).getByText('templates.system')).toBeTruthy()
      expect(within(row).queryByText('common.ca')).toBeNull()
    }
    const custom = await rowFor(CUSTOM_TEMPLATE.name)
    expect(within(custom).getByText('templates.custom')).toBeTruthy()
    expect(within(custom).queryByText('common.ca')).toBeNull()
  })

  it('reads is_system rather than the name: same name, both verdicts', async () => {
    // One name, two rows, differing only by the flag. Nothing about the
    // text can decide this — only the field can.
    getAll.mockResolvedValue({ data: [
      { id: 1, name: 'Identical Certificate A', is_system: true, template_type: 'web_server', validity_days: 365 },
      { id: 2, name: 'Identical Certificate B', is_system: false, template_type: 'web_server', validity_days: 365 },
    ] })
    renderPage()

    expect(within(await rowFor('Identical Certificate A')).getByText('templates.system')).toBeTruthy()
    expect(within(await rowFor('Identical Certificate B')).getByText('templates.custom')).toBeTruthy()
  })
})

describe('TemplatesPage — system templates cannot be edited or deleted', () => {
  // The page's own `rowActions` are never passed to the table (true on dev
  // too, so it is long-standing dead code rather than a regression). The
  // buttons a user actually reaches are the detail panel's, opened by
  // clicking the row, so that is what these assert on.
  const openPanelFor = async (name) => {
    fireEvent.click(await screen.findByText(name))
    return await screen.findByRole('button', { name: /common.delete/i })
  }

  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [SYSTEM_TEMPLATES[0], CUSTOM_TEMPLATE] })
  })

  it('disables Edit and Delete for a system template, leaving Copy and Export', async () => {
    renderPage()
    await openPanelFor('Web Server Certificate')

    // The server answers 403 to both of these.
    expect(screen.getByRole('button', { name: /common.edit/i }).disabled).toBe(true)
    expect(screen.getByRole('button', { name: /common.delete/i }).disabled).toBe(true)
    // Duplicating a system template is the supported way to base a custom
    // one on a built-in, so it must stay reachable.
    expect(screen.getByRole('button', { name: /common.copy/i }).disabled).toBe(false)
    expect(screen.getByRole('button', { name: /common.export/i }).disabled).toBe(false)
  })

  it('leaves a custom template fully actionable', async () => {
    renderPage()
    await openPanelFor('Test Certificate 123')

    expect(screen.getByRole('button', { name: /common.edit/i }).disabled).toBe(false)
    expect(screen.getByRole('button', { name: /common.delete/i }).disabled).toBe(false)
  })
})

describe('TemplatesPage — the Show system toggle', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
  })

  it('hides system templates when switched off, and remembers it', async () => {
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()
    await screen.findByText('Web Server Certificate')

    fireEvent.click(screen.getByRole('switch', { name: /templates.showSystem/i }))

    await waitFor(() => expect(screen.queryByText('Web Server Certificate')).toBeNull())
    expect(screen.getByText('Test Certificate 123')).toBeTruthy()
    expect(window.localStorage.getItem(SHOW_SYSTEM_KEY)).toBe('false')
  })

  it('starts off when that is the stored preference', async () => {
    window.localStorage.setItem(SHOW_SYSTEM_KEY, 'false')
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()

    await screen.findByText('Test Certificate 123')
    expect(screen.queryByText('Web Server Certificate')).toBeNull()
  })

  it('forces itself on and disables when no custom template exists', async () => {
    // Hiding the only templates there are would leave an empty table that
    // reads as a broken page rather than an applied filter.
    window.localStorage.setItem(SHOW_SYSTEM_KEY, 'false')
    getAll.mockResolvedValue({ data: SYSTEM_TEMPLATES })
    renderPage()

    await screen.findByText('Web Server Certificate')
    const toggle = screen.getByRole('switch', { name: /templates.showSystem/i })
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    expect(toggle.disabled).toBe(true)
  })

  it('does not overwrite the stored preference when it forces itself on', async () => {
    // The whole point of the override being applied on top rather than
    // written back: create a custom template again and the user's own
    // choice is still there.
    window.localStorage.setItem(SHOW_SYSTEM_KEY, 'false')
    getAll.mockResolvedValue({ data: SYSTEM_TEMPLATES })
    renderPage()

    await screen.findByText('Web Server Certificate')
    expect(window.localStorage.getItem(SHOW_SYSTEM_KEY)).toBe('false')
  })
})
