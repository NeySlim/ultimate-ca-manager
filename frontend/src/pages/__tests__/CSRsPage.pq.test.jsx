/**
 * CSRsPage re-key keeps the key of the request: an ML-DSA CSR is re-keyed as
 * ML-DSA, as a CSR or as a certificate, and an EC curve is kept, never RSA.
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CSR_LABELS, GROUP_PQ, KEY_ALGORITHMS, findAlgorithm, isBrainpool } from '../../lib/keyAlgorithms'

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

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), create: vi.fn(), row: null, effective: {} }))

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
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
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
  policiesService: { getEffective: vi.fn(() => Promise.resolve({ data: mocks.effective })) },
}))
// A native select exposes the options the real one renders in a portal
vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import CSRsPage from '../CSRsPage'

const PQ_ROWS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)
// A CSR as the API lists it: a post-quantum key has its label and no size
const ML_DSA_CSR = {
  id: 21, cn: 'pq.example.test', common_name: 'pq.example.test',
  key_type: 'ML-DSA-87', key_algorithm: 'ML-DSA-87', key_size: null, security_level: 5,
}
const BRAINPOOL_CSR = {
  id: 23, cn: 'bp.example.test', common_name: 'bp.example.test',
  key_type: 'EC brainpoolP384r1', key_algorithm: 'EC', key_size: 384,
}
const RSA_3072_CSR = {
  id: 24, cn: 'rsa3072.example.test', common_name: 'rsa3072.example.test',
  key_type: 'RSA 3072', key_algorithm: 'RSA', key_size: 3072,
}
const EC_CSR = {
  id: 22, cn: 'ec.example.test', common_name: 'ec.example.test',
  key_type: 'EC secp384r1', key_algorithm: 'EC', key_size: 0,
}

// Key types the Generate CSR form offers, as the API spells them
const offeredKeys = () => [...screen.getByLabelText('common.keyType').querySelectorAll('option')].map(o => o.value)
const csrOf = (labels) => labels.map(l => findAlgorithm(l).csr)

async function openGenerate() {
  mocks.row = EC_CSR
  render(<MemoryRouter initialEntries={['/csrs']}><CSRsPage /></MemoryRouter>)
  await screen.findByText(EC_CSR.cn)
  fireEvent.click(screen.getAllByText('csrs.generateCSR')[0])
  await screen.findByLabelText('common.keyType')
}

async function submitGenerate() {
  const buttons = await screen.findAllByText('csrs.generateCSR')
  fireEvent.click(buttons[buttons.length - 1])
  await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1))
  return mocks.create.mock.calls[0][0]
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
    mocks.effective = {}
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

  it('re-keys an RSA 3072 CSR as a CSR with RSA 3072', async () => {
    await openRekey(RSA_3072_CSR)
    fireEvent.click(screen.getByText('csrs.rekeyAsCSR'))
    await waitFor(() => expect(screen.getByLabelText('common.keyType')).toHaveValue('RSA 3072'))
    expect((await submitGenerate()).key_type).toBe('RSA 3072')
  })

  it('re-keys a CSR with an unknown key on the server default, not a frontend literal', async () => {
    mocks.effective = { default_key_type: 'EC-P384' }
    await openRekey({ id: 25, cn: 'odd.example.test', common_name: 'odd.example.test', key_type: 'Falcon-512', key_algorithm: 'Falcon', key_size: null })
    fireEvent.click(screen.getByText('csrs.rekeyAsCSR'))
    const want = findAlgorithm('EC-P384').csr
    await waitFor(() => expect(screen.getByLabelText('common.keyType')).toHaveValue(want))
    expect((await submitGenerate()).key_type).toBe(want)
  })

  it('keeps the curve of an EC CSR re-keyed as a certificate', async () => {
    await openRekey(EC_CSR)
    fireEvent.click(screen.getByText('csrs.rekeyAsCert'))
    expect(mocks.navigate.mock.calls[0][1].state.prefill).toMatchObject({ key_type: 'ecdsa', key_size: '384' })
  })
})

describe('CSRsPage Generate CSR key types on this server', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.create.mockResolvedValue({ data: { id: 99 } })
  })

  it('offers every CSR key outside FIPS mode', async () => {
    mocks.effective = {}
    await openGenerate()
    expect(offeredKeys()).toEqual(csrOf(CSR_LABELS))
  })

  it('offers no ML-DSA or Brainpool key in FIPS mode', async () => {
    mocks.effective = { fips: true }
    await openGenerate()
    await waitFor(() => expect(offeredKeys()).toEqual(csrOf(CSR_LABELS.filter(l => findAlgorithm(l).fips))))
    expect(CSR_LABELS.some(isBrainpool)).toBe(true)
  })

  it('offers no ML-DSA key on a build without it', async () => {
    mocks.effective = { ml_dsa: false }
    await openGenerate()
    await waitFor(() => expect(offeredKeys()).toEqual(
      csrOf(CSR_LABELS.filter(l => findAlgorithm(l).group !== GROUP_PQ))))
  })

  it.each([['ML-DSA', ML_DSA_CSR], ['Brainpool', BRAINPOOL_CSR]])(
    're-keys a %s CSR in FIPS mode with the first key offered', async (_name, row) => {
      mocks.effective = { fips: true }
      await openRekey(row)
      fireEvent.click(screen.getByText('csrs.rekeyAsCSR'))
      const first = findAlgorithm(CSR_LABELS.find(l => findAlgorithm(l).fips)).csr
      await waitFor(() => expect(screen.getByLabelText('common.keyType')).toHaveValue(first))
      expect((await submitGenerate()).key_type).toBe(first)
    })
})

describe('CSRsPage Generate CSR starts on the server default key', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.create.mockResolvedValue({ data: { id: 99 } })
  })

  it('preselects the key the server issues when none is named', async () => {
    mocks.effective = { default_key_type: 'EC-P384' }
    await openGenerate()
    const want = findAlgorithm('EC-P384').csr
    await waitFor(() => expect(screen.getByLabelText('common.keyType')).toHaveValue(want))
    fireEvent.change(screen.getAllByPlaceholderText('example.com')[0], { target: { value: 'dflt.example.test' } })
    expect((await submitGenerate()).key_type).toBe(want)
  })

  it('keeps the key the user picked when the server answer arrives', async () => {
    mocks.effective = { default_key_type: 'EC-P384' }
    await openGenerate()
    const want = findAlgorithm('RSA-4096').csr
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: want } })
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.getByLabelText('common.keyType')).toHaveValue(want)
  })

  it('stays on the form default when the server names none', async () => {
    mocks.effective = { default_key_error: 'no default key type is allowed' }
    await openGenerate()
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.getByLabelText('common.keyType')).toHaveValue(findAlgorithm(CSR_LABELS[0]).csr)
  })
})
