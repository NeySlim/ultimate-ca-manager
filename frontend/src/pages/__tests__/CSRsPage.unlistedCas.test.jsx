/**
 * The CA picker of the CSR signing dialog lists the CAs able to sign and
 * counts the others (#426).
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
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
const openWindow = vi.fn()
const showWarning = vi.fn()
const navigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
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
  useWindowManager: () => ({
    openWindow, closeWindow: vi.fn(), windows: [],
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
      { id: 1, descr: 'Signing CA', has_private_key: true },
      { id: 2, descr: 'Keyless root', certificate_only: true, has_private_key: false },
      { id: 3, descr: 'Offline CA', has_private_key: true, offline: true },
    ] }),
  },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  mscaService: {
    getEnabled: vi.fn().mockResolvedValue({ data: [] }),
    getTemplates: vi.fn().mockResolvedValue({ data: ['WebServer'] }),
    signCSR: (...a) => signCSR(...a),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

// A native select exposes the options and the helper text that the real one hides in a portal.
vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, onChange, helperText }) => (
    <div data-testid={`field-${label}`}>
      <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
        <option value="">-</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
}))

import CSRsPage from '../CSRsPage'

const PENDING_CSR = { id: 11, common_name: 'pending.example.com', cn: 'pending.example.com', has_private_key: false }

describe('CSRsPage signing CA picker (#426)', () => {
  beforeEach(() => {
    mockIsMobile = false
    getAll.mockReset().mockResolvedValue({ data: [PENDING_CSR] })
    getHistory.mockReset().mockResolvedValue({ data: [] })
    getById.mockReset().mockResolvedValue({ data: { ...PENDING_CSR } })
  })

  it('offers only the CA that can sign and counts the others', async () => {
    render(<MemoryRouter initialEntries={['/csrs']}><CSRsPage /></MemoryRouter>)
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByText('pending.example.com'))
    fireEvent.click(await screen.findByText('csrs.sign'))
    const field = await screen.findByTestId('field-common.certificateAuthority')
    expect(within(field).getAllByRole('option').filter((o) => o.value !== '').map((o) => o.textContent)).toEqual(['Signing CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
  })
})
