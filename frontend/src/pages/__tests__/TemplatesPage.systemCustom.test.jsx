/**
 * TemplatesPage: Source is read, not guessed.
 *
 * The list used to label a template "Certificate" or "CA" from a substring
 * match on its name: `name.includes('ca')`. Three of the eight seeded
 * templates contain those two letters ("Email Certificate (S/MIME)",
 * "Client Authentication" and "Smartcard Logon"), so three ordinary leaf
 * templates were shown as certificate authorities, with the authority icon
 * and a detail pane that spelled out "Certificate Authority". Nothing in the
 * database ever said so.
 *
 * What replaced it is `is_system`, which the API already returns. These
 * tests pin that contract: if `is_system` stops arriving, or stops driving
 * the column, every row silently reads Custom and every system template
 * gets its Edit and Delete buttons back, which the server answers 403 to.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Permissions are a variable so a test can render the page as a reader.
const perms = vi.hoisted(() => ({ write: true, delete: true }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

// The real NotificationContext memoises what it hands out, so `showError`
// keeps its identity across renders. Returning fresh spies instead would give
// useCRUDPage's `loadData` a new identity every render, its effect would
// refetch in a loop, and the table would keep dropping back to its "Loading..."
// state, where every row is absent for reasons that have nothing to do with a
// filter.
const notification = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notification,
  useMobile: () => ({ isMobile: false, isDesktop: true, isTouch: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
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
      canWrite: () => perms.write, canDelete: () => perms.delete,
      hasPermission: () => true, canRead: () => true,
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

// These are the seeded names the bug actually hit: every one of them contains
// the letters "ca", and every one of them is an ordinary leaf template.
const SYSTEM_TEMPLATES = [
  { id: 1, name: 'Email Certificate (S/MIME)', template_type: 'email', is_system: true, validity_days: 397 },
  { id: 2, name: 'Smartcard Logon', template_type: 'smartcard_logon', is_system: true, validity_days: 397 },
  { id: 3, name: 'Client Authentication', template_type: 'client_auth', is_system: true, validity_days: 365 },
]
const CUSTOM_TEMPLATE = { id: 4, name: 'Wi-Fi Client Certificate', template_type: 'client_auth', is_system: false, validity_days: 397 }


const renderPage = () => render(<MemoryRouter><TemplatesPage /></MemoryRouter>)

const rowFor = async (name) => {
  const cell = await screen.findByText(name)
  return cell.closest('tr')
}

// A row's absence is only evidence in a render that has rows in it: a table
// that is loading draws "Loading..." and no rows at all, which satisfies a
// bare `queryByText(...)` null check on the first tick, before the filtered
// rows are back. So every assertion that the system rows were hidden waits for
// the custom row and reads the system one out of that same render. Both
// queries are scoped to the table, which is what a filter acts on, and where
// the open detail panel would otherwise be a second match for the name.
const expectOnlyCustomRows = () => waitFor(() => {
  const table = screen.getByRole('table')
  expect(within(table).getByText(CUSTOM_TEMPLATE.name)).toBeTruthy()
  expect(within(table).queryByText('Smartcard Logon')).toBeNull()
})

const reset = () => {
  window.localStorage.clear()
  getAll.mockReset()
  perms.write = true
  perms.delete = true
}

describe('TemplatesPage: Source comes from is_system', () => {
  beforeEach(reset)

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
    // text can decide this, only the field can.
    getAll.mockResolvedValue({ data: [
      { id: 1, name: 'Identical Certificate A', is_system: true, template_type: 'web_server', validity_days: 365 },
      { id: 2, name: 'Identical Certificate B', is_system: false, template_type: 'web_server', validity_days: 365 },
    ] })
    renderPage()

    expect(within(await rowFor('Identical Certificate A')).getByText('templates.system')).toBeTruthy()
    expect(within(await rowFor('Identical Certificate B')).getByText('templates.custom')).toBeTruthy()
  })
})

describe('TemplatesPage: system templates cannot be edited or deleted', () => {
  // The dock's heading: Exporter, Modifier (disabled with its reason on a system template),
  // then the « ⋯ » menu (Aperçu détaillé, Dupliquer, Activer/Désactiver, Supprimer).
  const openDockFor = async (name) => {
    fireEvent.click(await screen.findByText(name))
    return await screen.findByRole('button', { name: /common.export/i })
  }
  const openMenu = async () => {
    fireEvent.click(screen.getByRole('button', { name: 'templates.module.moreActions' }))
    return await screen.findByTestId('inspector-actions-dialog')
  }

  beforeEach(() => {
    reset()
    getAll.mockResolvedValue({ data: [SYSTEM_TEMPLATES[0], CUSTOM_TEMPLATE] })
  })

  it('disables Edit and offers no Delete for a system template, leaving Duplicate and Export', async () => {
    renderPage()
    await openDockFor('Email Certificate (S/MIME)')

    // The server answers 403 to an edit: the button says why rather than disappearing
    const edit = screen.getByRole('button', { name: /common.edit/i })
    expect(edit.disabled).toBe(true)
    expect(edit.getAttribute('title')).toBe('templates.systemNotEditable')
    expect(screen.getByRole('button', { name: /common.export/i }).disabled).toBe(false)
    // Duplicating a system template is the supported way to base a custom one on a built-in
    const menu = await openMenu()
    expect(within(menu).getByRole('button', { name: /templates.module.duplicate/ })).toBeTruthy()
    expect(within(menu).queryByRole('button', { name: /common.delete/ })).toBeNull()
  })

  it('leaves a custom template fully actionable and names its source', async () => {
    renderPage()
    await openDockFor(CUSTOM_TEMPLATE.name)

    const edit = screen.getByRole('button', { name: /common.edit/i })
    expect(edit.disabled).toBe(false)
    expect(edit.getAttribute('title')).toBeNull()
    const dock = document.querySelector('#inspector')
    expect(within(dock).getAllByText('templates.custom').length).toBeGreaterThan(0)
    expect(screen.queryByText('common.certificateAuthority')).toBeNull()
    const menu = await openMenu()
    expect(within(menu).getByRole('button', { name: /common.delete/ })).toBeTruthy()
  })

  it('offers template edit, duplicate and activation only on write:templates', async () => {
    // PUT /api/v2/templates/<id> and the duplicate's POST both require write:templates
    perms.write = false
    getAll.mockResolvedValue({ data: [CUSTOM_TEMPLATE] })
    renderPage()
    await openDockFor(CUSTOM_TEMPLATE.name)

    expect(screen.queryByRole('button', { name: /common.edit/i })).toBeNull()
    const menu = await openMenu()
    expect(within(menu).queryByRole('button', { name: /templates.module.duplicate/ })).toBeNull()
    expect(within(menu).queryByRole('button', { name: /common.deactivate/ })).toBeNull()
    // Export asks for nothing beyond read, and Delete has its own permission
    expect(screen.getByRole('button', { name: /common.export/i })).toBeTruthy()
    expect(within(menu).getByRole('button', { name: /common.delete/ })).toBeTruthy()
  })

  it('withholds the delete without delete:templates', async () => {
    perms.delete = false
    getAll.mockResolvedValue({ data: [CUSTOM_TEMPLATE] })
    renderPage()
    await openDockFor(CUSTOM_TEMPLATE.name)

    const menu = await openMenu()
    expect(within(menu).queryByRole('button', { name: /common.delete/ })).toBeNull()
    expect(screen.getByRole('button', { name: /common.edit/i })).toBeTruthy()
  })
})

describe('TemplatesPage: the source filter', () => {
  beforeEach(reset)

  const SOURCE_KEY = 'ucm-templates-source'
  const source = () => screen.getByRole('combobox', { name: 'templates.source' })

  it('hides system templates when Custom is chosen, and remembers it', async () => {
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()
    await screen.findByText('Smartcard Logon')

    fireEvent.change(source(), { target: { value: 'custom' } })

    await expectOnlyCustomRows()
    await waitFor(() => expect(window.localStorage.getItem(SOURCE_KEY)).toBe('"custom"'))
  })

  it('closes the dock on a template it has just hidden', async () => {
    // Otherwise the dock goes on describing a row that left the list
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()
    fireEvent.click(await screen.findByText('Smartcard Logon'))
    await screen.findByRole('button', { name: /common.export/i })

    fireEvent.change(source(), { target: { value: 'custom' } })

    await waitFor(() => {
      expect(within(screen.getByRole('table')).getByText(CUSTOM_TEMPLATE.name)).toBeTruthy()
      expect(screen.queryByRole('button', { name: /common.export/i })).toBeNull()
    })
  })

  it('leaves the dock open on a custom template when system rows are hidden', async () => {
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()
    fireEvent.click(await screen.findByText(CUSTOM_TEMPLATE.name))
    await screen.findByRole('button', { name: /common.export/i })

    fireEvent.change(source(), { target: { value: 'custom' } })

    await expectOnlyCustomRows()
    expect(screen.getByRole('button', { name: /common.export/i })).toBeTruthy()
  })

  it('starts on the stored choice', async () => {
    window.localStorage.setItem(SOURCE_KEY, '"custom"')
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()

    await screen.findByText(CUSTOM_TEMPLATE.name)
    expect(screen.queryByText('Smartcard Logon')).toBeNull()
  })

  it('says why the list is empty when only system templates exist, and puts them back', async () => {
    // Hiding the only templates there are must not read as a broken page
    window.localStorage.setItem(SOURCE_KEY, '"custom"')
    getAll.mockResolvedValue({ data: SYSTEM_TEMPLATES })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'table.clearFilters' }))
    expect(await screen.findByText('Smartcard Logon')).toBeTruthy()
  })
})
