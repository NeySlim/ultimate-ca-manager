/**
 * TemplatesPage: an import that lands nothing warns with the counts and the
 * skipped templates, and the Email field accepts the {email} placeholder.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

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
      canWrite: () => true, canDelete: () => true,
      hasPermission: () => true, canRead: () => true,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const svc = vi.hoisted(() => ({
  getAll: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  import: vi.fn(),
}))
vi.mock('../../services', () => ({
  templatesService: {
    getAll: (...a) => svc.getAll(...a),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    create: (...a) => svc.create(...a),
    update: (...a) => svc.update(...a),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    import: (...a) => svc.import(...a),
    duplicate: vi.fn().mockResolvedValue({ data: {} }),
    export: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock('../../services/eku.service', () => ({
  ekuService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }),
  },
}))

import TemplatesPage from '../TemplatesPage'

const renderPage = () => render(<MemoryRouter><TemplatesPage /></MemoryRouter>)

const openImportModal = async () => {
  fireEvent.click(await screen.findByRole('button', { name: 'common.import' }))
  return screen.getByRole('button', { name: 'templates.importTemplate' })
}

const selectImportFile = (contents = '[]') => {
  const input = document.querySelector('input[type="file"]')
  const file = new File([contents], 'templates.json', { type: 'application/json' })
  fireEvent.change(input, { target: { files: [file] } })
}

beforeEach(() => {
  window.localStorage.clear()
  svc.getAll.mockReset().mockResolvedValue({ data: [] })
  svc.create.mockReset().mockResolvedValue({ data: {} })
  svc.update.mockReset().mockResolvedValue({ data: {} })
  svc.import.mockReset()
  notification.showSuccess.mockClear()
  notification.showWarning.mockClear()
  notification.showError.mockClear()
})

describe('TemplatesPage import: warns on skip or on nothing imported/updated', () => {
  it('case 1: 1 imported / 0 skipped shows success and closes the modal', async () => {
    svc.import.mockResolvedValue({ data: { imported: 1, updated: 0, skipped: 0 } })
    renderPage()

    const importBtn = await openImportModal()
    selectImportFile()
    fireEvent.click(importBtn)

    await waitFor(() => expect(notification.showSuccess).toHaveBeenCalledWith('messages.success.import.template'))
    expect(notification.showWarning).not.toHaveBeenCalled()
    expect(svc.import).toHaveBeenCalledTimes(1)
    expect(svc.import.mock.calls[0][0]).toBeInstanceOf(FormData)
    expect(svc.create).not.toHaveBeenCalled()
    await waitFor(() => expect(document.querySelector('input[type="file"]')).toBeNull())
  })

  it('case 2: a skip warns with the summary key and the skipped item name, modal stays open', async () => {
    svc.import.mockResolvedValue({
      data: { imported: 0, updated: 0, skipped: 1, skipped_items: ['A (already exists)'] },
    })
    renderPage()

    const importBtn = await openImportModal()
    selectImportFile()
    fireEvent.click(importBtn)

    await waitFor(() => expect(notification.showWarning).toHaveBeenCalledTimes(1))
    const [message] = notification.showWarning.mock.calls[0]
    expect(message).toContain('templates.importSummary')
    expect(message).toContain('A (already exists)')
    expect(notification.showSuccess).not.toHaveBeenCalled()
    // Nothing landed, so the modal is still there for the user to retry.
    expect(document.querySelector('input[type="file"]')).not.toBeNull()
  })

  it('case 3: an empty-array import warns instead of reporting success', async () => {
    svc.import.mockResolvedValue({ data: { imported: 0, updated: 0, skipped: 0 } })
    renderPage()

    const importBtn = await openImportModal()
    selectImportFile('[]')
    fireEvent.click(importBtn)

    await waitFor(() => expect(notification.showWarning).toHaveBeenCalledTimes(1))
    expect(notification.showWarning.mock.calls[0][0]).toContain('templates.importSummary')
    expect(notification.showSuccess).not.toHaveBeenCalled()
  })
})

describe('TemplatesPage Email field: not type="email" (built-in copies carry {email})', () => {
  const PLACEHOLDER_TEMPLATE = {
    id: 10, name: 'Copied Email Cert', template_type: 'email', is_system: false,
    validity_days: 397, dn_template: { emailAddress: '{email}' }, extensions_template: {},
  }

  it('case 4: editing a template whose emailAddress is {email} still submits to update', async () => {
    svc.getAll.mockResolvedValue({ data: [PLACEHOLDER_TEMPLATE] })
    renderPage()

    fireEvent.click(await screen.findByText(PLACEHOLDER_TEMPLATE.name))
    fireEvent.click(await screen.findByRole('button', { name: 'common.edit' }))

    const emailInput = await screen.findByPlaceholderText('certificates.emailPlaceholder')
    expect(emailInput.value).toBe('{email}')
    expect(emailInput.type).toBe('text')
    expect(emailInput.closest('form').checkValidity()).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: 'common.update' }))

    await waitFor(() => expect(svc.update).toHaveBeenCalledTimes(1))
    const [, payload] = svc.update.mock.calls[0]
    expect(payload.dn_template.emailAddress).toBe('{email}')
  })

  it('case 5: creating a template with a real Email keeps it in the payload', async () => {
    svc.getAll.mockResolvedValue({ data: [] })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'templates.new' }))
    fireEvent.change(await screen.findByPlaceholderText('templates.namePlaceholder'), {
      target: { value: 'Fresh Template' },
    })
    fireEvent.change(screen.getByPlaceholderText('certificates.emailPlaceholder'), {
      target: { value: 'pki@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'common.create' }))

    await waitFor(() => expect(svc.create).toHaveBeenCalledTimes(1))
    expect(svc.create.mock.calls[0][0].dn_template.emailAddress).toBe('pki@example.com')
  })
})
