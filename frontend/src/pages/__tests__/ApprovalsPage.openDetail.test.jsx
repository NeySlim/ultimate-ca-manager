/**
 * ApprovalsPage: approving a request opens what it issued (certificate or CA).
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

let mockCanRead = true
const openWindow = vi.fn()

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useWindowManager: () => ({
    openWindow, closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../hooks', () => ({
  usePermission: () => ({
    canWrite: () => true, canDelete: () => true, hasPermission: () => true,
    canRead: (resource) => (resource === 'certificates' || resource === 'cas') ? mockCanRead : true,
  }),
}))

const list = vi.fn()
const getStats = vi.fn()
const approve = vi.fn()
const reject = vi.fn()
vi.mock('../../services', () => ({
  approvalsService: {
    list: (...args) => list(...args),
    getStats: (...args) => getStats(...args),
    approve: (...args) => approve(...args),
    reject: (...args) => reject(...args),
  },
}))

import ApprovalsPage from '../ApprovalsPage'

const REQUEST = { id: 1, request_type: 'certificate', status: 'pending', requester_username: 'alice', created_at: '2026-01-01T00:00:00Z' }

const renderPage = () => render(<MemoryRouter><ApprovalsPage /></MemoryRouter>)

const clickApproveOrReject = async (label) => {
  await waitFor(() => expect(list).toHaveBeenCalled())
  fireEvent.click(await screen.findByTitle(`approvals.${label}`))
  if (label === 'reject') {
    fireEvent.change(document.querySelector('textarea'), { target: { value: 'no' } })
  }
  const dialogButtons = screen.getAllByText(`approvals.${label}`).map(el => el.closest('button')).filter(Boolean)
  fireEvent.click(dialogButtons[dialogButtons.length - 1])
}

describe('ApprovalsPage — opening what an approval issued', () => {
  beforeEach(() => {
    mockCanRead = true
    openWindow.mockReset()
    list.mockReset(); getStats.mockReset(); approve.mockReset(); reject.mockReset()
    list.mockResolvedValue({ data: [REQUEST] })
    getStats.mockResolvedValue({ data: { pending: 1, approved: 0, rejected: 0, total: 1 } })
  })

  it('opens the issued certificate', async () => {
    approve.mockResolvedValue({ data: { certificate_issued: true, certificate: { id: 7 } } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('certificate', 7))
  })

  it('opens the issued intermediate CA', async () => {
    approve.mockResolvedValue({ data: { certificate_issued: true, certificate: { id: null, ca_id: 9 } } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    await waitFor(() => expect(openWindow).toHaveBeenCalledWith('ca', 9))
  })

  it('opens nothing when the certificate was not issued', async () => {
    approve.mockResolvedValue({ data: { certificate_issued: false, issue_error: 'x' } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    expect(openWindow).not.toHaveBeenCalled()
  })

  it('opens nothing when the request was closed instead of issued', async () => {
    approve.mockResolvedValue({ data: { request_closed: true, issue_error: 'x' } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    expect(openWindow).not.toHaveBeenCalled()
  })

  it('opens nothing on reject', async () => {
    reject.mockResolvedValue({ data: {} })
    renderPage()
    await clickApproveOrReject('reject')
    await waitFor(() => expect(reject).toHaveBeenCalled())
    expect(openWindow).not.toHaveBeenCalled()
  })

  it('opens nothing when the approver lacks read:certificates', async () => {
    mockCanRead = false
    approve.mockResolvedValue({ data: { certificate_issued: true, certificate: { id: 7 } } })
    renderPage()
    await clickApproveOrReject('approve')
    await waitFor(() => expect(approve).toHaveBeenCalled())
    expect(openWindow).not.toHaveBeenCalled()
  })
})
