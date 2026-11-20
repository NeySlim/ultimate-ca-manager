/**
 * CertificatesPage rows: one action (export) and a chevron; the row, its name and
 * the chevron open the detail, where rename, renew, revoke and delete live; the
 * checkbox selects without opening and feeds the batch bar.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable across renders: t and showError are loadData dependencies
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
}))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))
const perms = vi.hoisted(() => ({ write: true, del: true }))
const windows = vi.hoisted(() => ({ openEntity: vi.fn(), closeWindow: vi.fn() }))
const svc = vi.hoisted(() => ({
  getAll: vi.fn(), getById: vi.fn(), rename: vi.fn(), renew: vi.fn(),
  revoke: vi.fn(), delete: vi.fn(), export: vi.fn(), bulkExport: vi.fn(),
}))
const download = vi.hoisted(() => vi.fn())

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isDesktop: true, isTablet: false, sidebarOpen: true, setSidebarOpen: () => {} }),
  useInspector: () => ({
    ...windows, windows: [], prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: () => {},
  }),
}))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  const permission = {
    canWrite: () => perms.write, canDelete: () => perms.del,
    hasPermission: () => perms.write, canRead: () => true,
  }
  const history = { addToHistory: () => {}, history: [] }
  const favorites = { favorites: [], toggleFavorite: () => {}, isFavorite: () => false }
  const ws = { muteToasts: () => {}, subscribe: () => () => {}, isConnected: false }
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => permission,
    useRecentHistory: () => history,
    useFavorites: () => favorites,
    useWebSocket: () => ws,
  }
})

vi.mock('../../services', () => ({
  certificatesService: {
    ...svc,
    getAll: (...a) => svc.getAll(...a),
    getStats: () => Promise.resolve({ data: { valid: 1, expiring: 0, expired: 0, revoked: 0, total: 1 } }),
  },
  casService: { getAll: () => Promise.resolve({ data: [{ id: 1, refid: 'ca-1', descr: 'CA 1' }] }) },
  truststoreService: { addFromCA: () => Promise.resolve({ data: {} }) },
}))

vi.mock('../../lib/utils', async () => {
  const actual = await vi.importActual('../../lib/utils')
  return { ...actual, downloadBlob: download }
})

// The comparison dialog shows which certificates it was handed
vi.mock('../../components/CertificateCompareModal', () => ({
  CertificateCompareModal: ({ open, initialCert, secondCert }) => (open
    ? <div data-testid="compare">{`${initialCert?.id ?? '-'}|${secondCert?.id ?? '-'}`}</div> : null),
}))

import CertificatesPage from '../CertificatesPage'

const VALID = {
  id: 7, cn: 'web.example.com', common_name: 'web.example.com', descr: 'Front door',
  status: 'valid', caref: 'ca-1', has_private_key: true,
  valid_from: '2026-01-01T00:00:00Z', valid_to: '2027-01-01T00:00:00Z',
}

async function renderWith(cert) {
  svc.getAll.mockResolvedValue({ data: [cert], meta: { total: 1 } })
  render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
  return screen.findByRole('row', { name: new RegExp(cert.cn.replace(/\./g, '\\.')) })
}

const OTHER = { ...VALID, id: 8, cn: 'api.example.com', common_name: 'api.example.com', descr: 'API' }
const THIRD = { ...VALID, id: 9, cn: 'db.example.com', common_name: 'db.example.com', descr: 'Database' }

const titles = (row) => within(row).getAllByRole('button').map(b => b.getAttribute('title')).filter(Boolean)

async function renderRows(certs) {
  svc.getAll.mockResolvedValue({ data: certs, meta: { total: certs.length } })
  render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
  await screen.findByRole('row', { name: new RegExp(certs[0].cn.replace(/\./g, '\\.')) })
}
const rowBox = (cn) => within(screen.getByRole('row', { name: new RegExp(cn.replace(/\./g, '\\.')) })).getByRole('checkbox')

beforeEach(() => {
  window.localStorage.clear()
  vi.clearAllMocks()
  perms.write = true
  perms.del = true
})

describe('CertificatesPage row actions', () => {
  it('keeps one action on the row, and the chevron', async () => {
    const row = await renderWith(VALID)
    expect(titles(row)).toEqual(['export.title', 'table.open'])
  })

  it('shows the same row to a read-only operator: exporting needs no write right', async () => {
    perms.write = false
    perms.del = false
    const row = await renderWith(VALID)
    expect(titles(row)).toEqual(['export.title', 'table.open'])
  })

  it('names the row buttons after the certificate', async () => {
    const row = await renderWith(VALID)
    const names = within(row).getAllByRole('button').map((b) => b.getAttribute('aria-label')).filter(Boolean)
    expect(names).toEqual(['table.rowAction', 'table.openRow'])
    expect(within(row).getByRole('checkbox')).toHaveAttribute('aria-label', 'table.selectRow')
  })

  it.each([
    ['the chevron', (row) => within(row).getByTitle('table.open')],
    ['the name', (row) => within(row).getByRole('button', { name: 'web.example.com' })],
  ])('opens the detail from %s', async (_, target) => {
    const row = await renderWith(VALID)
    fireEvent.click(target(row))
    expect(windows.openEntity).toHaveBeenCalledTimes(1)
    expect(windows.openEntity).toHaveBeenCalledWith('certificate', 7)
  })

  it('opens nothing from the rest of the row: only the name and the chevron open', async () => {
    const row = await renderWith(VALID)
    fireEvent.click(row)
    fireEvent.click(within(row).getByText('Front door'))
    expect(windows.openEntity).not.toHaveBeenCalled()
  })

  it('opens the export dialog for that row, not the detail', async () => {
    const row = await renderWith(VALID)
    fireEvent.click(within(row).getByTitle('export.title'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('web.example.com')).toBeInTheDocument()
    expect(windows.openEntity).not.toHaveBeenCalled()
  })
})

describe('CertificatesPage selection and batch bar', () => {
  it('ticks a row without opening it and counts the selection', async () => {
    await renderRows([VALID, OTHER])
    expect(screen.queryByRole('group', { name: 'table.selection' })).toBeNull()
    fireEvent.click(rowBox('web.example.com'))
    const bar = screen.getByRole('group', { name: 'table.selection' })
    // Part of the page: the mockup's short count
    expect(bar).toHaveTextContent(/^table\.selectedCount:1/)
    expect(rowBox('web.example.com')).toBeChecked()
    expect(rowBox('api.example.com')).not.toBeChecked()
    expect(windows.openEntity).not.toHaveBeenCalled()
    fireEvent.click(within(bar).getByText('table.clearSelection'))
    expect(screen.queryByRole('group', { name: 'table.selection' })).toBeNull()
    expect(rowBox('web.example.com')).not.toBeChecked()
  })

  it('disables the names and the row actions while a selection is on, and gives them back after', async () => {
    await renderRows([VALID, OTHER])
    const row = () => screen.getByRole('row', { name: /web\.example\.com/ })
    fireEvent.click(rowBox('api.example.com'))
    expect(within(row()).getByRole('button', { name: 'web.example.com' })).toBeDisabled()
    expect(within(row()).getByTitle('export.title')).toBeDisabled()
    expect(within(row()).getByTitle('table.open')).toBeDisabled()
    expect(rowBox('web.example.com')).toBeEnabled()
    fireEvent.click(within(screen.getByRole('group', { name: 'table.selection' })).getByText('table.clearSelection'))
    expect(within(row()).getByRole('button', { name: 'web.example.com' })).toBeEnabled()
    fireEvent.click(within(row()).getByRole('button', { name: 'web.example.com' }))
    expect(windows.openEntity).toHaveBeenCalledWith('certificate', 7)
  })

  it('selects the page from the header checkbox', async () => {
    await renderRows([VALID, OTHER])
    fireEvent.click(screen.getByRole('checkbox', { name: 'table.selectPage' }))
    expect(rowBox('web.example.com')).toBeChecked()
    expect(rowBox('api.example.com')).toBeChecked()
    // The whole page: the count says so
    expect(screen.getByRole('group', { name: 'table.selection' })).toHaveTextContent(/^certificates\.selectedOnPage:2/)
  })

  it('hands the two ticked certificates to the comparison', async () => {
    await renderRows([VALID, OTHER, THIRD])
    fireEvent.click(rowBox('web.example.com'))
    fireEvent.click(rowBox('db.example.com'))
    // Two rows of three: the mockup's short count
    expect(within(screen.getByRole('group', { name: 'table.selection' })).getByText('table.selectedCount:2')).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('group', { name: 'table.selection' })).getByText('common.compare'))
    expect(screen.getByTestId('compare')).toHaveTextContent('7|9')
  })

  it('compares one ticked certificate with another to pick, and refuses three', async () => {
    await renderRows([VALID, OTHER, THIRD])
    fireEvent.click(rowBox('api.example.com'))
    const bar = screen.getByRole('group', { name: 'table.selection' })
    fireEvent.click(within(bar).getByText('common.compare'))
    expect(screen.getByTestId('compare')).toHaveTextContent('8|-')
    fireEvent.click(rowBox('web.example.com'))
    fireEvent.click(rowBox('db.example.com'))
    const compare = within(bar).getByText('common.compare').closest('button')
    expect(compare).toBeDisabled()
    expect(compare).toHaveAttribute('title', 'certificates.compareHint')
  })

  it('exports the ticked certificates as one PEM file and reports the skipped ones', async () => {
    const blob = Object.assign(new Blob(['pem']), { exportedCount: 1, skippedCount: 1, skipped: [{ id: 8 }] })
    svc.bulkExport.mockResolvedValue(blob)
    await renderRows([VALID, OTHER, THIRD])
    fireEvent.click(rowBox('web.example.com'))
    fireEvent.click(rowBox('db.example.com'))
    fireEvent.click(within(screen.getByRole('group', { name: 'table.selection' })).getByTitle('certificates.exportSelectedPem'))
    await waitFor(() => expect(svc.bulkExport).toHaveBeenCalledWith([7, 9], 'pem'))
    await waitFor(() => expect(download).toHaveBeenCalledWith(blob, 'certificates_export.pem'))
    expect(notify.showSuccess).toHaveBeenCalledWith('certificates.bulkExported:1')
    expect(notify.showWarning).toHaveBeenCalledWith('export.skippedUnreadable:1')
  })

  it('says why a batch export failed', async () => {
    svc.bulkExport.mockRejectedValue(Object.assign(new Error('refused by policy'), { status: 403 }))
    await renderRows([VALID])
    fireEvent.click(rowBox('web.example.com'))
    fireEvent.click(within(screen.getByRole('group', { name: 'table.selection' })).getByTitle('certificates.exportSelectedPem'))
    await waitFor(() => expect(notify.showError).toHaveBeenCalledWith('refused by policy'))
    expect(download).not.toHaveBeenCalled()
  })

  it('drops from the selection a row the list no longer shows', async () => {
    await renderRows([VALID, OTHER])
    fireEvent.click(rowBox('web.example.com'))
    fireEvent.click(rowBox('api.example.com'))
    svc.getAll.mockResolvedValue({ data: [OTHER], meta: { total: 1 } })
    await act(async () => {
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'certificate' } }))
    })
    await waitFor(() => expect(screen.queryByRole('row', { name: /web\.example\.com/ })).toBeNull())
    // The bar counts what is still on screen, the whole page now
    expect(screen.getByRole('group', { name: 'table.selection' })).toHaveTextContent('certificates.selectedOnPage:1')
    svc.bulkExport.mockResolvedValue(new Blob(['pem']))
    fireEvent.click(within(screen.getByRole('group', { name: 'table.selection' })).getByTitle('certificates.exportSelectedPem'))
    await waitFor(() => expect(svc.bulkExport).toHaveBeenCalledWith([8], 'pem'))
  })
})
