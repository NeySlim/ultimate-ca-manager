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

const SHOW_SYSTEM_KEY = 'ucm-templates-show-system'
const PRESETS_KEY = 'ucm-templates-presets'

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
  // The page's own `rowActions` were never passed to the table (true on dev
  // too, so long-standing dead code rather than a regression) and have since
  // been removed. The buttons a user actually reaches are the detail panel's,
  // opened by clicking the row, so that is what these assert on.
  const openPanelFor = async (name) => {
    fireEvent.click(await screen.findByText(name))
    return await screen.findByRole('button', { name: /common.export/i })
  }

  beforeEach(() => {
    reset()
    getAll.mockResolvedValue({ data: [SYSTEM_TEMPLATES[0], CUSTOM_TEMPLATE] })
  })

  it('disables Edit and Delete for a system template, leaving Copy and Export', async () => {
    renderPage()
    await openPanelFor('Email Certificate (S/MIME)')

    // The server answers 403 to both of these, and the button says so on
    // hover rather than disappearing, which reads as a rendering glitch.
    const edit = screen.getByRole('button', { name: /common.edit/i })
    const del = screen.getByRole('button', { name: /common.delete/i })
    expect(edit.disabled).toBe(true)
    expect(del.disabled).toBe(true)
    expect(edit.getAttribute('title')).toBe('templates.systemNotEditable')
    expect(del.getAttribute('title')).toBe('templates.systemNotDeletable')
    // Duplicating a system template is the supported way to base a custom
    // one on a built-in, so it must stay reachable.
    expect(screen.getByRole('button', { name: /common.copy/i }).disabled).toBe(false)
    expect(screen.getByRole('button', { name: /common.export/i }).disabled).toBe(false)
  })

  it('leaves a custom template fully actionable, and says why the other is not', async () => {
    renderPage()
    await openPanelFor(CUSTOM_TEMPLATE.name)

    const edit = screen.getByRole('button', { name: /common.edit/i })
    const del = screen.getByRole('button', { name: /common.delete/i })
    expect(edit.disabled).toBe(false)
    expect(del.disabled).toBe(false)
    // A custom template carries no refusal to explain, and the panel names
    // the source rather than the "Certificate Authority" it used to print.
    expect(edit.getAttribute('title')).toBeNull()
    expect(del.getAttribute('title')).toBeNull()
    expect(screen.getByText('templates.customDescription')).toBeTruthy()
    expect(screen.queryByText('common.certificateAuthority')).toBeNull()
  })

  it('offers template edit and duplicate only on write:templates', async () => {
    // PUT /api/v2/templates/<id> and the duplicate's POST both require
    // write:templates. Dropping the canWrite guard from the panel fails here,
    // which the source-reading test this replaced could never prove.
    perms.write = false
    getAll.mockResolvedValue({ data: [CUSTOM_TEMPLATE] })
    renderPage()
    await openPanelFor(CUSTOM_TEMPLATE.name)

    expect(screen.queryByRole('button', { name: /common.edit/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /common.copy/i })).toBeNull()
    // Export asks for nothing beyond read, and Delete has its own permission.
    expect(screen.getByRole('button', { name: /common.export/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /common.delete/i })).toBeTruthy()
  })

  it('withholds the panel delete without delete:templates', async () => {
    perms.delete = false
    getAll.mockResolvedValue({ data: [CUSTOM_TEMPLATE] })
    renderPage()
    await openPanelFor(CUSTOM_TEMPLATE.name)

    expect(screen.queryByRole('button', { name: /common.delete/i })).toBeNull()
    expect(screen.getByRole('button', { name: /common.edit/i })).toBeTruthy()
  })
})

describe('TemplatesPage: the Show system toggle', () => {
  beforeEach(reset)

  const toggle = () => screen.getByRole('switch', { name: /templates.showSystem/i })

  it('hides system templates when switched off, and remembers it', async () => {
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()
    await screen.findByText('Smartcard Logon')

    fireEvent.click(toggle())

    await expectOnlyCustomRows()
    expect(window.localStorage.getItem(SHOW_SYSTEM_KEY)).toBe('false')
  })

  it('closes the detail panel on a template it has just hidden', async () => {
    // Otherwise the panel goes on describing a row that left the list.
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()
    fireEvent.click(await screen.findByText('Smartcard Logon'))
    await screen.findByRole('button', { name: /common.export/i })

    fireEvent.click(toggle())

    await waitFor(() => {
      expect(within(screen.getByRole('table')).getByText(CUSTOM_TEMPLATE.name)).toBeTruthy()
      expect(screen.queryByRole('button', { name: /common.export/i })).toBeNull()
    })
  })

  it('leaves the panel open on a custom template when system rows are hidden', async () => {
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()
    fireEvent.click(await screen.findByText(CUSTOM_TEMPLATE.name))
    await screen.findByRole('button', { name: /common.export/i })

    fireEvent.click(toggle())

    await expectOnlyCustomRows()
    expect(screen.getByRole('button', { name: /common.export/i })).toBeTruthy()
  })

  it('starts off when that is the stored preference', async () => {
    window.localStorage.setItem(SHOW_SYSTEM_KEY, 'false')
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()

    await screen.findByText(CUSTOM_TEMPLATE.name)
    expect(screen.queryByText('Smartcard Logon')).toBeNull()
  })

  it('forces itself on and disables when no custom template exists', async () => {
    // Hiding the only templates there are would leave an empty table that
    // reads as a broken page rather than an applied filter.
    window.localStorage.setItem(SHOW_SYSTEM_KEY, 'false')
    getAll.mockResolvedValue({ data: SYSTEM_TEMPLATES })
    renderPage()

    await screen.findByText('Smartcard Logon')
    expect(toggle().getAttribute('aria-checked')).toBe('true')
    expect(toggle().disabled).toBe(true)
  })

  it('does not overwrite the stored preference when it forces itself on', async () => {
    // The whole point of the override being applied on top rather than
    // written back: once a custom template exists, the user's own choice is
    // still there and still hides the system rows.
    window.localStorage.setItem(SHOW_SYSTEM_KEY, 'false')
    getAll.mockResolvedValue({ data: SYSTEM_TEMPLATES })
    const { unmount } = renderPage()

    await screen.findByText('Smartcard Logon')
    expect(window.localStorage.getItem(SHOW_SYSTEM_KEY)).toBe('false')
    unmount()

    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()

    await screen.findByText(CUSTOM_TEMPLATE.name)
    expect(screen.queryByText('Smartcard Logon')).toBeNull()
  })
})

describe('TemplatesPage: saved filter presets', () => {
  beforeEach(reset)

  const applyPreset = async (name) => {
    fireEvent.click(screen.getByTitle('table.filterPresets'))
    fireEvent.click(await screen.findByText(name))
  }

  it('applies a preset saved on the Source filter', async () => {
    // The filter key is `source`; a preset read under the old `type` key
    // silently did nothing.
    window.localStorage.setItem(PRESETS_KEY, JSON.stringify([
      { id: 1, name: 'Mine only', filters: { source: ['custom'] } },
    ]))
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()
    await screen.findByText('Smartcard Logon')

    await applyPreset('Mine only')

    await expectOnlyCustomRows()
  })

  it('clears the filter for a preset saved before the column became Source', async () => {
    // {type: ['ca']} matches no row now, so applying it must show everything
    // rather than empty the table. Applied over a narrower preset, so that a
    // handler which ignored it would leave the table filtered and be caught.
    window.localStorage.setItem(PRESETS_KEY, JSON.stringify([
      { id: 1, name: 'Mine only', filters: { source: ['custom'] } },
      { id: 2, name: 'Old CA preset', filters: { type: ['ca'] } },
    ]))
    getAll.mockResolvedValue({ data: [...SYSTEM_TEMPLATES, CUSTOM_TEMPLATE] })
    renderPage()
    await screen.findByText('Smartcard Logon')

    await applyPreset('Mine only')
    await expectOnlyCustomRows()

    await applyPreset('Old CA preset')

    expect(await screen.findByText('Smartcard Logon')).toBeTruthy()
    expect(screen.getByText(CUSTOM_TEMPLATE.name)).toBeTruthy()
  })
})
