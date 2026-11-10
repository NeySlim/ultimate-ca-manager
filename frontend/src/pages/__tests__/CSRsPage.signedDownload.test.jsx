/**
 * CSRsPage: the history tab downloads the issued certificate, not the request.
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
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
  URL.createObjectURL = URL.createObjectURL || (() => 'blob:x')
  URL.revokeObjectURL = URL.revokeObjectURL || (() => {})
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mobile = vi.hoisted(() => ({
  isMobile: false, isTablet: false, isDesktop: true, isTouch: false,
  isLargeScreen: true, screenWidth: 1440, sidebarOpen: true, setSidebarOpen: () => {},
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => mobile,
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => mobile }))

let permissions = []
vi.mock('../../hooks', async () => {
  const common = await vi.importActual('../../hooks/useCommon')
  return {
    useModals: common.useModals,
    usePermission: () => ({
      canWrite: () => mockCanWrite, canDelete: () => false, canRead: () => true,
      hasPermission: (p) => permissions.includes(p),
    }),
  }
})

const SIGNED = { id: 42, common_name: 'signed.example.com', cn: 'signed.example.com', signed_by: 'CA 1', days_remaining: 300 }
const csrDownload = vi.fn()
const resubmit = vi.fn()
let mockCanWrite = false
const certExport = vi.fn()

vi.mock('../../services', () => ({
  csrsService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getHistory: () => Promise.resolve({ data: [SIGNED] }),
    getById: () => Promise.resolve({ data: SIGNED }),
    download: (...a) => csrDownload(...a),
    downloadKey: vi.fn(),
    resubmit: (...a) => resubmit(...a),
  },
  certificatesService: { export: (...a) => certExport(...a) },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  mscaService: { getEnabled: vi.fn().mockResolvedValue({ data: [] }) },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import CSRsPage from '../CSRsPage'

const openSigned = async () => {
  render(<MemoryRouter initialEntries={['/csrs?tab=history']}><CSRsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('signed.example.com'))
  await screen.findByText('csrs.downloadCSR')
}

describe('CSRsPage history: downloads', () => {
  beforeEach(() => {
    permissions = ['read:certificates']
    csrDownload.mockReset().mockResolvedValue(new Blob(['csr']))
    certExport.mockReset().mockResolvedValue(new Blob(['crt']))
  })

  it('"Download certificate" exports the certificate', async () => {
    await openSigned()
    fireEvent.click(screen.getByRole('button', { name: /common\.downloadCertificate/ }))
    await waitFor(() => expect(certExport).toHaveBeenCalledWith(42, 'pem'))
    expect(csrDownload).not.toHaveBeenCalled()
  })

  it('the request itself stays downloadable', async () => {
    await openSigned()
    fireEvent.click(screen.getByRole('button', { name: /csrs\.downloadCSR/ }))
    await waitFor(() => expect(csrDownload).toHaveBeenCalledWith(42))
    expect(certExport).not.toHaveBeenCalled()
  })

  it('"Sign again" puts the request back in the pending list (#389)', async () => {
    mockCanWrite = true
    resubmit.mockReset().mockResolvedValue({ data: { id: 77 } })
    await openSigned()
    fireEvent.click(screen.getByRole('button', { name: /csrs\.signAgain/ }))
    await waitFor(() => expect(resubmit).toHaveBeenCalledWith(42))
    mockCanWrite = false
  })

  it('offers no "Sign again" without write:csrs', async () => {
    await openSigned()
    expect(screen.queryByRole('button', { name: /csrs\.signAgain/ })).toBeNull()
  })

  it('offers no certificate download without read:certificates', async () => {
    permissions = []
    await openSigned()
    expect(screen.queryByRole('button', { name: /common\.downloadCertificate/ })).toBeNull()
  })
})
