/**
 * CSRsPage: every subject field of the generate form reaches the API (#449).
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
const openEntity = vi.fn()
const showWarning = vi.fn()
const navigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  // The page's own moves are observed; the dock's URL writes (a location object, a step back) go through
  return { ...actual, useNavigate: () => { const real = actual.useNavigate(); return (to, o) => (typeof to === 'string' ? navigate(to, o) : real(to, o)) } }
})

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning,
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
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
  }
})

const getAll = vi.fn()
const getHistory = vi.fn()
const getById = vi.fn()
const upload = vi.fn()
const create = vi.fn()
const sign = vi.fn()
const signCSR = vi.fn()

vi.mock('../../services', () => ({
  csrsService: {
    getAll: (...a) => getAll(...a),
    getHistory: (...a) => getHistory(...a),
    getById: (...a) => getById(...a),
    upload: (...a) => upload(...a),
    create: (...a) => create(...a),
    sign: (...a) => sign(...a),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    download: vi.fn(),
    downloadKey: vi.fn(),
    uploadKey: vi.fn(),
  },
  casService: {
    getAll: vi.fn().mockResolvedValue({ data: [
      { id: 1, refid: 'ca-1', descr: 'CA 1', has_private_key: true },
    ] }),
  },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  mscaService: {
    getEnabled: vi.fn().mockResolvedValue({ data: [] }),
    getTemplates: vi.fn().mockResolvedValue({ data: ['WebServer'] }),
    signCSR: (...a) => signCSR(...a),
    getPendingRequests: vi.fn().mockResolvedValue({ data: [] }),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

vi.mock('../../components/SmartImport', () => ({
  SmartImportModal: ({ isOpen, onImportComplete }) =>
    isOpen ? <button onClick={() => onImportComplete(window.__importResult)}>do-import</button> : null,
}))

import CSRsPage from '../CSRsPage'

const renderPage = () => render(<MemoryRouter initialEntries={['/csrs']}><CSRsPage /></MemoryRouter>)

describe('CSRsPage generate form sends the whole subject (#449)', () => {
  beforeEach(() => {
    mockIsMobile = false
    getAll.mockReset().mockResolvedValue({ data: [] })
    getHistory.mockReset().mockResolvedValue({ data: [] })
    getById.mockReset().mockResolvedValue({ data: { id: 101 } })
    create.mockReset().mockResolvedValue({ data: { id: 101 } })
  })

  it('sends state, locality and email with the other fields', async () => {
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(screen.getAllByText('csrs.generateCSR')[0])
    const cn = await screen.findAllByPlaceholderText('example.com')
    fireEvent.change(cn[0], { target: { value: 'host.example.com' } })
    fireEvent.change(screen.getByPlaceholderText('certificates.statePlaceholder'), { target: { value: 'Ile-de-France' } })
    fireEvent.change(screen.getByPlaceholderText('certificates.localityPlaceholder'), { target: { value: 'Paris' } })
    fireEvent.change(screen.getByPlaceholderText('certificates.emailPlaceholder'), { target: { value: 'ops@example.com' } })
    const buttons = screen.getAllByText('csrs.generateCSR')
    fireEvent.click(buttons[buttons.length - 1])

    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0]).toMatchObject({
      cn: 'host.example.com', state: 'Ile-de-France', locality: 'Paris', email: 'ops@example.com',
    })
  })
})
