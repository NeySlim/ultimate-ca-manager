/**
 * TSAPage signer key choices read the key registry: every offered key is sent the
 * way the issue API names it (the row's `issue` pair), ML-DSA-65 and ML-DSA-87
 * included, and FIPS mode hides what the module does not approve.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// The page sees one more TSA label, a key the product reads but does not generate
vi.mock('../../lib/keyAlgorithms', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, TSA_LABELS: [...actual.TSA_LABELS, 'ED25519'] }
})
const { GROUP_PQ, KEY_ALGORITHMS, TSA_LABELS, findAlgorithm } = await vi.importActual('../../lib/keyAlgorithms')

let fipsMode = false
let mldsaBuild = true
vi.mock('../../lib/policyAlgorithms', async (importOriginal) => ({
  ...(await importOriginal()),
  useKeyPlatform: () => ({ fips: fipsMode, mldsa: mldsaBuild }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../components', async (importOriginal) => ({
  ...(await importOriginal()),
  Select: ({ label, value, onChange, options }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { id: 1, username: 'op', role: 'operator' } }),
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn() }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: ['light', 'dark'] }),
  useWindowManager: () => ({
    openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
  ThemeProvider: ({ children }) => children,
  NotificationProvider: ({ children }) => children,
  MobileProvider: ({ children }) => children,
  WindowManagerProvider: ({ children }) => children,
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: ['read:settings', 'write:settings', 'write:certificates', 'read:cas'] }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

vi.mock('../../services/cas.service', () => ({
  casService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 1, refid: 'ca-tsa', name: 'TSA CA' }] }) },
}))

vi.mock('../../services/tsa.service', () => ({
  tsaService: {
    getConfig: vi.fn(),
    updateConfig: vi.fn().mockResolvedValue({ data: {} }),
    getStats: vi.fn().mockResolvedValue({ data: { total: 0 } }),
    getSignerCandidates: vi.fn().mockResolvedValue({ data: [] }),
    issueSignerCertificate: vi.fn(),
  },
}))

import TSAPage from '../TSAPage'
import { tsaService } from '../../services/tsa.service'

async function openGenerateModal() {
  render(<MemoryRouter><TSAPage /></MemoryRouter>)
  const tabs = await screen.findAllByText('tsa.groups.settings')
  fireEvent.click(tabs[tabs.length - 1])
  fireEvent.click(await screen.findByText('tsa.signerGenerate'))
  await screen.findByText('tsa.signerGenerateModalDesc')
  return screen.getByLabelText('tsa.signerGenerateKeyType')
}

function submit() {
  const buttons = screen.getAllByText('tsa.signerGenerate')
  fireEvent.click(buttons[buttons.length - 1])
}

describe('TSAPage signer key, from the registry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fipsMode = false
    mldsaBuild = true
    tsaService.getConfig.mockResolvedValue({
      data: { enabled: true, ca_refid: 'ca-tsa', signer_cert_refid: '', signer: { configured: false } },
    })
    tsaService.getStats.mockResolvedValue({ data: { total: 0 } })
    tsaService.getSignerCandidates.mockResolvedValue({ data: [] })
    tsaService.issueSignerCertificate.mockResolvedValue({ data: { selected: true } })
  })

  it('starts on the first TSA key of the registry', async () => {
    const select = await openGenerateModal()
    expect(select.value).toBe(TSA_LABELS[0])
  })

  it.each(TSA_LABELS)('sends %s as the issue API names it', async (label) => {
    const select = await openGenerateModal()
    fireEvent.change(select, { target: { value: label } })
    submit()
    await waitFor(() => expect(tsaService.issueSignerCertificate).toHaveBeenCalled())
    const [keyType, keySize] = findAlgorithm(label).issue
    const payload = tsaService.issueSignerCertificate.mock.calls[0][0]
    expect(payload).toMatchObject({ key_type: keyType, key_size: keySize })
    expect(payload.curve).toBeUndefined()
  })

  it('offers only keys the product generates', async () => {
    expect(findAlgorithm('ED25519').generate).toBe(false)
    const select = await openGenerateModal()
    const offered = Array.from(select.options).map(o => o.value)
    expect(offered).toEqual(TSA_LABELS)
  })

  it('offers ML-DSA-65 and ML-DSA-87, not ML-DSA-44', async () => {
    const pq = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ).map(a => a.label)
    expect(TSA_LABELS.filter(l => pq.includes(l))).toEqual(['ML-DSA-65', 'ML-DSA-87'])
    const select = await openGenerateModal()
    const offered = Array.from(select.options).map(o => o.value)
    expect(offered).toEqual(expect.arrayContaining(['ML-DSA-65', 'ML-DSA-87']))
    expect(offered).not.toContain('ML-DSA-44')
  })

  it('says how ML-DSA tokens verify while an ML-DSA key is picked', async () => {
    const select = await openGenerateModal()
    fireEvent.change(select, { target: { value: 'RSA-2048' } })
    expect(screen.queryByText('tsa.signerMldsaVerifyNote')).toBeNull()
    fireEvent.change(select, { target: { value: 'ML-DSA-87' } })
    expect(screen.getByText('tsa.signerMldsaVerifyNote')).toBeTruthy()
  })

  it('hides ML-DSA in FIPS mode', async () => {
    fipsMode = true
    const select = await openGenerateModal()
    const offered = Array.from(select.options).map(o => o.value)
    expect(offered.length).toBeGreaterThan(0)
    expect(offered.filter(l => findAlgorithm(l)?.group === GROUP_PQ)).toEqual([])
    expect(offered).toEqual(TSA_LABELS.filter(l => findAlgorithm(l)?.fips))
  })

  it('hides ML-DSA on a build without it', async () => {
    mldsaBuild = false
    const select = await openGenerateModal()
    const offered = Array.from(select.options).map(o => o.value)
    expect(offered).toEqual(TSA_LABELS.filter(l => findAlgorithm(l)?.group !== GROUP_PQ && findAlgorithm(l)?.generate))
    expect(offered).toContain('EC-BP256')
  })
})
