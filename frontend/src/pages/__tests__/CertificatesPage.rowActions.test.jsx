/**
 * CertificatesPage — the row actions reach the same handlers, dialogs and
 * permission gates as the detail views (rename #286, revoke #334).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable across renders: t and showError are loadData dependencies
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key) => key,
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
  revoke: vi.fn(), delete: vi.fn(), export: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: () => {} }),
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

const titles = (row) => within(row).getAllByRole('button').map(b => b.getAttribute('title')).filter(Boolean)

describe('CertificatesPage row actions', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    perms.write = true
    perms.del = true
  })

  it('offers every action to a writer who may delete', async () => {
    const row = await renderWith(VALID)
    expect(titles(row)).toEqual([
      'common.details', 'export.title', 'certificates.rename', 'common.renew', 'common.revoke', 'common.delete',
    ])
  })

  it('keeps a read-only operator to details and export', async () => {
    perms.write = false
    perms.del = false
    const row = await renderWith(VALID)
    expect(titles(row)).toEqual(['common.details', 'export.title'])
  })

  it('gates delete on delete:certificates alone', async () => {
    perms.del = false
    const row = await renderWith(VALID)
    expect(titles(row)).not.toContain('common.delete')
    expect(titles(row)).toContain('common.revoke')
  })

  it('offers neither renew nor revoke on a revoked row, nor renew without a key', async () => {
    const revoked = await renderWith({ ...VALID, revoked: true, status: 'revoked' })
    expect(titles(revoked)).toEqual(['common.details', 'export.title', 'certificates.rename', 'common.delete'])
  })

  it('offers no renewal for a certificate whose key UCM does not hold', async () => {
    const row = await renderWith({ ...VALID, has_private_key: false })
    expect(titles(row)).not.toContain('common.renew')
    expect(titles(row)).toContain('common.revoke')
  })

  it('opens the detail window', async () => {
    const row = await renderWith(VALID)
    fireEvent.click(within(row).getByTitle('common.details'))
    expect(windows.openEntity).toHaveBeenCalledWith('certificate', 7)
  })

  it('opens the export dialog for that row', async () => {
    const row = await renderWith(VALID)
    fireEvent.click(within(row).getByTitle('export.title'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('web.example.com')).toBeInTheDocument()
  })

  it('renames through the service and reloads', async () => {
    notify.showPrompt.mockResolvedValueOnce('  Back door  ')
    svc.rename.mockResolvedValue({ data: { ...VALID, descr: 'Back door' } })
    const row = await renderWith(VALID)
    const loads = svc.getAll.mock.calls.length
    fireEvent.click(within(row).getByTitle('certificates.rename'))
    await waitFor(() => expect(svc.rename).toHaveBeenCalledWith(7, 'Back door'))
    expect(notify.showPrompt.mock.calls[0][1].defaultValue).toBe('Front door')
    expect(notify.showSuccess).toHaveBeenCalledWith('certificates.renameSuccess')
    await waitFor(() => expect(svc.getAll.mock.calls.length).toBeGreaterThan(loads))
  })

  it('renews through the shared renewal prompt', async () => {
    notify.showPrompt.mockResolvedValueOnce('')
    svc.renew.mockResolvedValue({ data: { id: 7 } })
    const row = await renderWith(VALID)
    fireEvent.click(within(row).getByTitle('common.renew'))
    await waitFor(() => expect(svc.renew).toHaveBeenCalledWith(7, {}))
    expect(notify.showPrompt.mock.calls[0][1].title).toBe('certificates.renewCertificate')
  })

  it('revokes through the reason dialog, with the hybrid pair question', async () => {
    svc.getById.mockResolvedValue({ data: { id: 8, related_certificate_id: 7, revoked: false } })
    svc.revoke.mockResolvedValue({ data: { related_not_revoked: 8 } })
    const row = await renderWith({ ...VALID, related_certificate_id: 8 })
    fireEvent.click(within(row).getByTitle('common.revoke'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByTestId('revoke-reason'), { target: { value: 'keyCompromise' } })
    const related = await within(dialog).findByLabelText('revocation.revokeRelated')
    expect(related).toBeChecked()
    fireEvent.click(related)
    fireEvent.submit(within(dialog).getByTestId('revoke-form'))
    await waitFor(() => expect(svc.revoke).toHaveBeenCalledWith(7, 'keyCompromise', { revokeRelated: false }))
    expect(notify.showWarning).toHaveBeenCalledWith('revocation.relatedRevokeFailed')
  })

  it('deletes an expired certificate after a confirmation', async () => {
    notify.showConfirm.mockResolvedValueOnce(true)
    svc.delete.mockResolvedValue({})
    const row = await renderWith({ ...VALID, status: 'expired' })
    fireEvent.click(within(row).getByTitle('common.delete'))
    await waitFor(() => expect(svc.delete).toHaveBeenCalledWith(7))
  })

  it('sends a still-valid certificate through the revocation dialog before deleting it', async () => {
    notify.showConfirm.mockResolvedValueOnce(true)
    const row = await renderWith(VALID)
    fireEvent.click(within(row).getByTitle('common.delete'))
    expect(await screen.findByTestId('revoke-form')).toBeInTheDocument()
    expect(notify.showConfirm.mock.calls[0][0]).toBe('certificates.deleteNeedsRevoke')
    expect(svc.delete).not.toHaveBeenCalled()
  })
})
