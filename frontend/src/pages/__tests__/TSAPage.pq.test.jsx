/**
 * TSAPage signer key choices read the key registry: every offered key is sent the
 * way the issue API names it (the row's `issue` pair), and ML-DSA stays out of the
 * list while the timestamp CMS is signed in RSA or ECDSA only.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { GROUP_PQ, KEY_ALGORITHMS, TSA_LABELS, findAlgorithm } from '../../lib/keyAlgorithms'

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
    getStats: vi.fn().mockResolvedValue({ data: { total_requests: 0 } }),
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
    tsaService.getConfig.mockResolvedValue({
      data: { enabled: true, ca_refid: 'ca-tsa', signer_cert_refid: '', signer: { configured: false } },
    })
    tsaService.getStats.mockResolvedValue({ data: { total_requests: 0 } })
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

  it('offers no ML-DSA key while the timestamp is signed in RSA or ECDSA only', async () => {
    const pq = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ).map(a => a.label)
    expect(pq).toEqual(expect.arrayContaining(['ML-DSA-65', 'ML-DSA-87']))
    const select = await openGenerateModal()
    const offered = Array.from(select.options).map(o => o.value)
    expect(offered.filter(v => pq.includes(v))).toEqual([])
  })
})
