/**
 * CertificatesPage: the caption under the list follows the inspector preference.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(null),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

let mockIsMobile = false
const inspector = { closeOnNav: true }
const openEntity = vi.fn()
const create = vi.fn()

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: mockIsMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => ({ openEntity, closeOnNav: inspector.closeOnNav }),
}))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const getAll = vi.fn()
const getById = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: {
    getAll: (...args) => getAll(...args),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 3, expiring: 0, expired: 0, revoked: 1, total: 4 } }),
    revoke: vi.fn().mockResolvedValue({ data: {} }),
    create: (...args) => create(...args),
    getById: (...args) => getById(...args),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 1, refid: 'ca-1', descr: 'CA 1' }] }) },
  truststoreService: { addFromCA: vi.fn().mockResolvedValue({ data: {} }) },
}))


// The form itself is not under test: a stub that submits what the real one would
vi.mock('../certificates/IssueCertificateForm', () => ({
  IssueCertificateForm: ({ onSubmit, onSent }) => (
    <button type="button" onClick={async () => onSent(await onSubmit({ cn: 'new.example.com' }))}>submit-issue</button>
  ),
}))

// Stub Smart Import: a button that fires onImportComplete with a given result
let importResult = null
vi.mock('../../components/SmartImport', () => ({
  SmartImportModal: ({ isOpen, onImportComplete }) =>
    isOpen ? <button onClick={() => onImportComplete(importResult)}>fire-import-complete</button> : null,
}))

import CertificatesPage from '../CertificatesPage'

const caption = async () => {
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  return document.querySelector('.table-caption span').textContent
}

/** The legend under the list says what the "close on navigate" preference does (M:189 keeps them open). */
describe('CertificatesPage: legend of the open certificates', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  })

  it('kept across pages: the mockup legend', async () => {
    inspector.closeOnNav = false
    render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
    expect(await caption()).toBe('certificates.listNote')
  })

  it('closed on navigation: the legend says they close when the page changes', async () => {
    inspector.closeOnNav = true
    render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
    expect(await caption()).toBe('certificates.listNoteCloseOnNav')
  })
})
