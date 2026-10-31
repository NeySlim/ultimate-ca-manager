/**
 * Bulk revocation of hybrid pair members (RFC 9763): the dialog asks whether to
 * revoke the other members too, ticked by default, only for a pair the server
 * would act on, and reports the other members revoked or renewed outside the
 * selection (the server's answer lists the selection only).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

// 1 and 2 form a pair, 3 stands alone, 4 names 1 one way, 5 names the revoked 6,
// 7 names 8, which is not listed and is read on demand
const mocks = vi.hoisted(() => ({
  bulkRevoke: vi.fn(), bulkRenew: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn(), getById: vi.fn(),
  selection: [1],
  certs: [
    { id: 1, cn: 'pair.example.com', related_certificate_id: 2 },
    { id: 2, cn: 'pair.example.com', related_certificate_id: 1 },
    { id: 3, cn: 'web.example.com', related_certificate_id: null },
    { id: 4, cn: 'pair.example.com', related_certificate_id: 1 },
    { id: 5, cn: 'old.example.com', related_certificate_id: 6 },
    { id: 6, cn: 'old.example.com', related_certificate_id: 5, revoked: true },
    { id: 7, cn: 'far.example.com', related_certificate_id: 8 },
  ],
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: mocks.showInfo, showWarning: mocks.showWarning,
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({
    isMobile: false, isTablet: false, isDesktop: true, isTouch: false,
    isLargeScreen: true, screenWidth: 1440, sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
  useWindowManager: () => ({
    openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../hooks', () => ({
  usePermission: () => ({
    canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    isAdmin: () => true,
  }),
}))

vi.mock('../../services', () => ({
  opnsenseService: { test: vi.fn(), import: vi.fn() },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }), bulkDelete: vi.fn() },
  certificatesService: {
    getAll: vi.fn(() => Promise.resolve({ data: mocks.certs, meta: { total: 3 } })),
    bulkRevoke: (...args) => mocks.bulkRevoke(...args),
    bulkRenew: (...args) => mocks.bulkRenew(...args),
    getById: (...args) => mocks.getById(...args),
  },
  csrsService: { getAll: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }), bulkSign: vi.fn() },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  usersService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

vi.mock('../../components/SmartImport', () => ({ SmartImportWidget: () => null }))

vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  ResponsiveLayout: ({ tabs = [], onTabChange, children }) => (
    <div>
      {tabs.map((tab) => <button key={tab.id} onClick={() => onTabChange(tab.id)}>{`tab-${tab.id}`}</button>)}
      {children}
    </div>
  ),
  ResponsiveDataTable: ({ onSelectionChange, bulkActions }) => (
    <div>
      <button onClick={() => onSelectionChange(new Set(mocks.selection))}>select-certs</button>
      {bulkActions}
    </div>
  ),
}))

import OperationsPage from '../OperationsPage'

const openBulk = async (action) => {
  render(<MemoryRouter><OperationsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('tab-bulk'))
  fireEvent.click(await screen.findByText('select-certs'))
  fireEvent.click(await screen.findByText(action))
  return screen.findByRole('dialog')
}
const confirm = (dialog) => fireEvent.click(within(dialog).getByRole('button', { name: 'common.confirm' }))

describe('OperationsPage bulk revocation of hybrid pair members', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('ucm-ops-resource-type', 'certificates')
    mocks.selection = [1]
    mocks.bulkRevoke.mockResolvedValue({ data: { success: [1], failed: [] } })
    mocks.bulkRenew.mockResolvedValue({ data: { success: [1, 2], failed: [] } })
    mocks.getById.mockResolvedValue({ data: { id: 8, related_certificate_id: 7, revoked: false } })
  })

  it('revokes the other members unless unticked', async () => {
    const dialog = await openBulk('common.revoke')
    const box = within(dialog).getByLabelText('revocation.revokeRelatedBulk')
    expect(box).toBeChecked()
    fireEvent.click(box)
    confirm(dialog)
    await waitFor(() => expect(mocks.bulkRevoke).toHaveBeenCalled())
    const [ids, reason, options] = mocks.bulkRevoke.mock.calls[0]
    expect(ids).toEqual([1])
    expect(reason).toBe('unspecified')
    expect(options.revokeRelated).toBe(false)
    expect(options.relatedOf(1)).toBe(2)
  })

  it('sends the default answer when left ticked', async () => {
    const dialog = await openBulk('common.revoke')
    confirm(dialog)
    await waitFor(() => expect(mocks.bulkRevoke).toHaveBeenCalled())
    expect(mocks.bulkRevoke.mock.calls[0][2].revokeRelated).toBe(true)
  })

  it('asks nothing when no selected certificate belongs to a pair', async () => {
    mocks.selection = [3]
    const dialog = await openBulk('common.revoke')
    expect(within(dialog).queryByLabelText('revocation.revokeRelatedBulk')).toBeNull()
    confirm(dialog)
    await waitFor(() => expect(mocks.bulkRevoke).toHaveBeenCalled())
    expect(mocks.bulkRevoke.mock.calls[0][2]).not.toHaveProperty('revokeRelated')
  })

  // The server's answer names the selection only: { success: [1], failed: [] }
  it('reports the other members revoked outside the selection', async () => {
    const dialog = await openBulk('common.revoke')
    confirm(dialog)
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith('revocation.bulkRelatedRevoked:1'))
  })

  it('reports nothing more when the box is unticked', async () => {
    const dialog = await openBulk('common.revoke')
    fireEvent.click(within(dialog).getByLabelText('revocation.revokeRelatedBulk'))
    confirm(dialog)
    await waitFor(() => expect(mocks.bulkRevoke).toHaveBeenCalled())
    expect(mocks.showWarning).not.toHaveBeenCalledWith(expect.stringMatching(/bulkRelatedRevoked/))
  })

  it.each([
    ['names it one way', 4],
    ['is already revoked', 5],
  ])('asks nothing when the other certificate %s', async (_case, id) => {
    mocks.selection = [id]
    mocks.bulkRevoke.mockResolvedValue({ data: { success: [id], failed: [] } })
    const dialog = await openBulk('common.revoke')
    expect(within(dialog).queryByLabelText('revocation.revokeRelatedBulk')).toBeNull()
    confirm(dialog)
    await waitFor(() => expect(mocks.bulkRevoke).toHaveBeenCalled())
    expect(mocks.showWarning).not.toHaveBeenCalledWith(expect.stringMatching(/bulkRelatedRevoked/))
  })

  it('reads an unlisted other member before asking', async () => {
    mocks.selection = [7]
    mocks.bulkRevoke.mockResolvedValue({ data: { success: [7], failed: [] } })
    const dialog = await openBulk('common.revoke')
    expect(await within(dialog).findByLabelText('revocation.revokeRelatedBulk')).toBeChecked()
    expect(mocks.getById).toHaveBeenCalledWith(8)
    confirm(dialog)
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith('revocation.bulkRelatedRevoked:1'))
  })

  it('reports the other members renewed outside the selection', async () => {
    mocks.bulkRenew.mockResolvedValue({ data: { success: [1], failed: [] } })
    const dialog = await openBulk('common.renew')
    confirm(dialog)
    await waitFor(() => expect(mocks.showInfo).toHaveBeenCalledWith('certificates.hybrid.bulkRelatedRenewed:1'))
  })

  it('reports no renewal outside a selection holding both members', async () => {
    mocks.selection = [1, 2]
    const dialog = await openBulk('common.renew')
    confirm(dialog)
    await waitFor(() => expect(mocks.bulkRenew).toHaveBeenCalled())
    expect(mocks.showInfo).not.toHaveBeenCalledWith(expect.stringMatching(/bulkRelatedRenewed/))
  })

  it('hands the pairs to the bulk renewal so a pair stays in one request', async () => {
    mocks.selection = [1, 2]
    const dialog = await openBulk('common.renew')
    confirm(dialog)
    await waitFor(() => expect(mocks.bulkRenew).toHaveBeenCalled())
    const [ids, options] = mocks.bulkRenew.mock.calls[0]
    expect(ids).toEqual([1, 2])
    expect(options.relatedOf(2)).toBe(1)
  })
})
