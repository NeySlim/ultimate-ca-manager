/**
 * TSAPage — one-click TSA signing certificate issuance (#312 follow-up).
 *
 * The generic issue path can't produce a certificate a strict RFC 3161 verifier
 * accepts (EKU always non-critical, never exclusive). This flow lets the
 * operator have UCM mint a purpose-built signer. The page must:
 *  - offer a pre-filled "Generate" modal from the signing-certificate section,
 *  - call tsaService.issueSignerCertificate with the chosen fields and reload,
 *  - surface eku_critical_exclusive on candidates and in the status box.
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
  casService: {
    getAll: vi.fn().mockResolvedValue({
      data: [{ id: 1, refid: 'ca-tsa', name: 'TSA CA' }],
    }),
  },
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
import { TSA_LABELS, findAlgorithm } from '../../lib/keyAlgorithms'
import { tsaService } from '../../services/tsa.service'

function setConfig(overrides = {}) {
  tsaService.getConfig.mockResolvedValue({
    data: {
      enabled: true, ca_refid: 'ca-tsa', policy_oid: '1.2.3.4.1',
      require_dedicated_cert: false, signer_cert_refid: '',
      signer: { configured: false },
      ...overrides,
    },
  })
}

async function openSettingsTab() {
  render(<MemoryRouter><TSAPage /></MemoryRouter>)
  const tabs = await screen.findAllByText('tsa.groups.settings')
  fireEvent.click(tabs[tabs.length - 1])
}

describe('TSAPage — one-click signer issuance (#312)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    tsaService.updateConfig.mockResolvedValue({ data: {} })
    tsaService.getStats.mockResolvedValue({ data: { total_requests: 0 } })
    tsaService.getSignerCandidates.mockResolvedValue({ data: [] })
    tsaService.issueSignerCertificate.mockResolvedValue({
      data: { selected: true, certificate: { refid: 'new-ts-1' }, signer: { configured: true, usable: true } },
    })
    setConfig()
  })

  it('offers the Generate action in the signing-certificate section', async () => {
    await openSettingsTab()
    expect(await screen.findByText('tsa.signerGenerate')).toBeInTheDocument()
  })

  it('opens a pre-filled modal and issues on confirm, then reloads', async () => {
    await openSettingsTab()
    fireEvent.click(await screen.findByText('tsa.signerGenerate'))

    // modal open
    expect(await screen.findByText('tsa.signerGenerateModalDesc')).toBeInTheDocument()

    // confirm — the submit button carries the same label
    const buttons = screen.getAllByText('tsa.signerGenerate')
    fireEvent.click(buttons[buttons.length - 1])

    await waitFor(() => expect(tsaService.issueSignerCertificate).toHaveBeenCalled())
    const payload = tsaService.issueSignerCertificate.mock.calls[0][0]
    expect(payload).toMatchObject({
      ca_refid: 'ca-tsa',
      cn: 'UCM Timestamping Authority',
      key_type: findAlgorithm(TSA_LABELS[0]).issue[0],
      key_size: findAlgorithm(TSA_LABELS[0]).issue[1],
    })
    // reloaded config + candidates after issuance
    await waitFor(() => expect(tsaService.getConfig).toHaveBeenCalledTimes(2))
  })

  it('shows the auto-renewal caveat in the Generate modal', async () => {
    await openSettingsTab()
    fireEvent.click(await screen.findByText('tsa.signerGenerate'))
    expect(await screen.findByText('tsa.signerGenerateRenewalNote')).toBeInTheDocument()
  })

  it('sends an explicit validity of 0 rather than swallowing it to the default', async () => {
    await openSettingsTab()
    fireEvent.click(await screen.findByText('tsa.signerGenerate'))
    await screen.findByText('tsa.signerGenerateModalDesc')

    const validity = screen.getByText('tsa.signerGenerateValidity')
      .closest('div').querySelector('input')
    fireEvent.change(validity, { target: { value: '0' } })

    const buttons = screen.getAllByText('tsa.signerGenerate')
    fireEvent.click(buttons[buttons.length - 1])

    await waitFor(() => expect(tsaService.issueSignerCertificate).toHaveBeenCalled())
    expect(tsaService.issueSignerCertificate.mock.calls[0][0].validity_days).toBe(0)
  })

  it('omits validity_days when the field is cleared', async () => {
    await openSettingsTab()
    fireEvent.click(await screen.findByText('tsa.signerGenerate'))
    await screen.findByText('tsa.signerGenerateModalDesc')

    const validity = screen.getByText('tsa.signerGenerateValidity')
      .closest('div').querySelector('input')
    fireEvent.change(validity, { target: { value: '' } })

    const buttons = screen.getAllByText('tsa.signerGenerate')
    fireEvent.click(buttons[buttons.length - 1])

    await waitFor(() => expect(tsaService.issueSignerCertificate).toHaveBeenCalled())
    expect(tsaService.issueSignerCertificate.mock.calls[0][0].validity_days).toBeUndefined()
  })

  it('renders the strict-EKU line in the status box for a critical/exclusive signer', async () => {
    setConfig({
      signer_cert_refid: 'cert-ts-1',
      signer: {
        configured: true, usable: true, refid: 'cert-ts-1',
        subject: 'CN=UCM Timestamping Authority', not_after: '2027-02-01T00:00:00+00:00',
        chain_len: 2, chain_to_root: true, eku_critical_exclusive: true,
      },
    })
    await openSettingsTab()
    expect(await screen.findByText('tsa.signerEkuStrict')).toBeInTheDocument()
  })

  it('flags a loose-EKU signer in the status box', async () => {
    setConfig({
      signer_cert_refid: 'cert-ts-2',
      signer: {
        configured: true, usable: true, refid: 'cert-ts-2',
        subject: 'CN=hand-rolled', not_after: '2027-02-01T00:00:00+00:00',
        chain_len: 1, chain_to_root: false, eku_critical_exclusive: false,
      },
    })
    await openSettingsTab()
    expect(await screen.findByText('tsa.signerEkuLoose')).toBeInTheDocument()
  })
})
