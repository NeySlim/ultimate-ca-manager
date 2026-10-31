/**
 * CSRsPage re-key keeps the key of the request: an ML-DSA CSR is re-keyed as
 * ML-DSA, as a CSR or as a certificate, and an EC curve is kept, never RSA.
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CSR_LABELS, GROUP_PQ, KEY_ALGORITHMS } from '../../lib/keyAlgorithms'

beforeAll(() => {
  global.ResizeObserver = global.ResizeObserver || class { observe() {} unobserve() {} disconnect() {} }
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
  Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {})
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {})
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), create: vi.fn(), row: null }))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mocks.navigate }
})

const mobile = {
  isMobile: false, isTablet: false, isDesktop: true, isTouch: false,
  isLargeScreen: true, screenWidth: 1440, sidebarOpen: true, setSidebarOpen: () => {},
}
vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => mobile,
  useWindowManager: () => ({
    openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => mobile }))
vi.mock('../../hooks', async () => {
  const common = await vi.importActual('../../hooks/useCommon')
  return {
    useModals: common.useModals,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => false, canRead: () => true, hasPermission: () => true,
    }),
  }
})

vi.mock('../../services', () => ({
  csrsService: {
    getAll: () => Promise.resolve({ data: [mocks.row] }),
    getHistory: () => Promise.resolve({ data: [] }),
    getById: () => Promise.resolve({ data: mocks.row }),
    create: (...a) => mocks.create(...a),
    download: vi.fn(), downloadKey: vi.fn(), uploadKey: vi.fn(),
  },
  certificatesService: { export: vi.fn() },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  mscaService: { getEnabled: vi.fn().mockResolvedValue({ data: [] }) },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: vi.fn().mockResolvedValue({ data: {} }) },
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import CSRsPage from '../CSRsPage'

const PQ_ROWS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)
// A CSR as the API lists it: a post-quantum key has its label and no size
const ML_DSA_CSR = {
  id: 21, cn: 'pq.example.test', common_name: 'pq.example.test',
  key_type: 'ML-DSA-87', key_algorithm: 'ML-DSA-87', key_size: null, security_level: 5,
}
const EC_CSR = {
  id: 22, cn: 'ec.example.test', common_name: 'ec.example.test',
  key_type: 'EC secp384r1', key_algorithm: 'EC', key_size: 0,
}

async function openRekey(row) {
  mocks.row = row
  render(<MemoryRouter initialEntries={['/csrs']}><CSRsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText(row.cn))
  const buttons = await screen.findAllByText('csrs.rekey')
  fireEvent.click(buttons[buttons.length - 1])
  await screen.findByText('csrs.rekeyAsCSR')
}

describe('CSRsPage re-key key type', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.create.mockResolvedValue({ data: { id: 99 } })
  })

  it('lists the ML-DSA levels among the CSR key types', () => {
    expect(PQ_ROWS).toHaveLength(3)
    for (const a of PQ_ROWS) expect(CSR_LABELS).toContain(a.label)
  })

  it('re-keys an ML-DSA CSR as a certificate with key_type=ml-dsa', async () => {
    await openRekey(ML_DSA_CSR)
    fireEvent.click(screen.getByText('csrs.rekeyAsCert'))
    expect(mocks.navigate).toHaveBeenCalledTimes(1)
    expect(mocks.navigate.mock.calls[0][1].state.prefill).toMatchObject({ key_type: 'ml-dsa', key_size: '87' })
  })

  it('re-keys an ML-DSA CSR as a CSR with the same key type', async () => {
    await openRekey(ML_DSA_CSR)
    fireEvent.click(screen.getByText('csrs.rekeyAsCSR'))
    const buttons = await screen.findAllByText('csrs.generateCSR')
    fireEvent.click(buttons[buttons.length - 1])
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1))
    expect(mocks.create.mock.calls[0][0]).toMatchObject({ key_type: 'ML-DSA-87' })
  })

  it('keeps the curve of an EC CSR re-keyed as a certificate', async () => {
    await openRekey(EC_CSR)
    fireEvent.click(screen.getByText('csrs.rekeyAsCert'))
    expect(mocks.navigate.mock.calls[0][1].state.prefill).toMatchObject({ key_type: 'ecdsa', key_size: '384' })
  })
})
