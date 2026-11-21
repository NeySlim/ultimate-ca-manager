/**
 * A CSR waiting on a Microsoft CA offers Check status: issued and imported,
 * still pending, denied, signed elsewhere, or an error.
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

beforeAll(() => {
  global.ResizeObserver = global.ResizeObserver || class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
  Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {})
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {})
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

let mockIsMobile = false
let mockWritable = () => true
const openEntity = vi.fn()
const showWarning = vi.fn()
const showSuccess = vi.fn()
const showError = vi.fn()
const showInfo = vi.fn()
const navigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess, showError, showInfo, showWarning,
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => ({
    isMobile: mockIsMobile, isTablet: false, isDesktop: !mockIsMobile, isTouch: false,
    isLargeScreen: !mockIsMobile, screenWidth: mockIsMobile ? 375 : 1440,
    sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
  useInspector: () => ({
    openEntity, closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../contexts/MobileContext', () => ({
  useMobile: () => ({
    isMobile: mockIsMobile, isTablet: false, isDesktop: !mockIsMobile, isTouch: false,
    isLargeScreen: !mockIsMobile, screenWidth: mockIsMobile ? 375 : 1440,
    sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
}))

vi.mock('../../hooks', async () => {
  const common = await vi.importActual('../../hooks/useCommon')
  return {
    useModals: common.useModals,
    usePermission: () => ({
      canWrite: (r) => mockWritable(r), canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
  }
})

const getAll = vi.fn()
const getHistory = vi.fn()
const getById = vi.fn()
const getPendingRequests = vi.fn()
const checkRequest = vi.fn()

vi.mock('../../services', () => ({
  csrsService: {
    getAll: (...a) => getAll(...a),
    getHistory: (...a) => getHistory(...a),
    getById: (...a) => getById(...a),
    upload: vi.fn(), create: vi.fn(), sign: vi.fn(),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    download: vi.fn(), downloadKey: vi.fn(), uploadKey: vi.fn(),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  mscaService: {
    getEnabled: vi.fn().mockResolvedValue({ data: [] }),
    getTemplates: vi.fn().mockResolvedValue({ data: [] }),
    signCSR: vi.fn(),
    getPendingRequests: (...a) => getPendingRequests(...a),
    checkRequest: (...a) => checkRequest(...a),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

import CSRsPage from '../CSRsPage'
import { openRow } from '../../test/atelierRows'

const CSR = { id: 11, common_name: 'pending.example.com', cn: 'pending.example.com', has_private_key: false }

// The check sits in the dock's « ⋯ » menu once the Microsoft CA request is known
const openMenu = async () => fireEvent.click(await screen.findByRole('button', { name: 'csrs.module.moreActions' }))

async function openCSR() {
  render(<MemoryRouter initialEntries={['/csrs']}><CSRsPage /></MemoryRouter>)
  await waitFor(() => expect(getAll).toHaveBeenCalled())
  await openRow('pending.example.com')
  await waitFor(() => expect(getPendingRequests).toHaveBeenCalled())
  await openMenu()
  return screen.findByText('msca.checkStatus')
}

describe('CSRsPage Microsoft CA status check', () => {
  beforeEach(() => {
    mockIsMobile = false
    mockWritable = () => true
    for (const f of [showSuccess, showError, showInfo, showWarning, openEntity]) f.mockReset()
    getAll.mockReset().mockResolvedValue({ data: [CSR] })
    getHistory.mockReset().mockResolvedValue({ data: [] })
    getById.mockReset().mockResolvedValue({ data: { ...CSR } })
    getPendingRequests.mockReset().mockResolvedValue({ data: [{ id: 5, msca_id: 2, csr_id: 11, status: 'pending' }] })
    checkRequest.mockReset()
  })

  it('imports an issued certificate and opens it', async () => {
    checkRequest.mockResolvedValue({ data: { status: 'issued', cert_id: 11 } })
    fireEvent.click(await openCSR())
    await waitFor(() => expect(checkRequest).toHaveBeenCalledWith(2, 5))
    await waitFor(() => expect(showSuccess).toHaveBeenCalledWith('msca.checkIssued'))
    expect(openEntity).toHaveBeenCalledWith('certificate', 11)
  })

  it('says the request is still pending', async () => {
    checkRequest.mockResolvedValue({ data: { status: 'pending' } })
    fireEvent.click(await openCSR())
    await waitFor(() => expect(showInfo).toHaveBeenCalledWith('msca.checkStillPending'))
    expect(openEntity).not.toHaveBeenCalled()
  })

  it('reports a denied request', async () => {
    checkRequest.mockResolvedValue({ data: { status: 'denied' } })
    fireEvent.click(await openCSR())
    await waitFor(() => expect(showError).toHaveBeenCalledWith('msca.checkDenied'))
  })

  it('says the CSR was signed elsewhere', async () => {
    checkRequest.mockResolvedValue({ data: { status: 'superseded' } })
    fireEvent.click(await openCSR())
    await waitFor(() => expect(showInfo).toHaveBeenCalledWith('msca.checkSuperseded'))
    expect(openEntity).not.toHaveBeenCalled()
    await openMenu()
    await screen.findByText('csrs.rekey')
    expect(screen.queryByText('msca.checkStatus')).toBeNull()
  })

  it('reports an error', async () => {
    checkRequest.mockRejectedValue(new Error('boom'))
    fireEvent.click(await openCSR())
    await waitFor(() => expect(showError).toHaveBeenCalledWith('boom'))
  })

  it('is not offered without write:certificates, which the route requires', async () => {
    mockWritable = (r) => r === 'csrs'
    render(<MemoryRouter initialEntries={['/csrs']}><CSRsPage /></MemoryRouter>)
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await openRow('pending.example.com')
    await screen.findByText('csrs.sign')
    await openMenu()
    await screen.findByText('csrs.rekey')
    expect(screen.queryByText('msca.checkStatus')).toBeNull()
    expect(getPendingRequests).not.toHaveBeenCalled()
  })

  it('offers nothing for a CSR no Microsoft CA holds', async () => {
    getPendingRequests.mockResolvedValue({ data: [{ id: 6, msca_id: 2, csr_id: 99, status: 'pending' }] })
    render(<MemoryRouter initialEntries={['/csrs']}><CSRsPage /></MemoryRouter>)
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await openRow('pending.example.com')
    await screen.findByText('csrs.sign')
    await waitFor(() => expect(getPendingRequests).toHaveBeenCalled())
    await openMenu()
    await screen.findByText('csrs.rekey')
    expect(screen.queryByText('msca.checkStatus')).toBeNull()
  })
})
