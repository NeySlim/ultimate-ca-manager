/**
 * TSAPage — dedicated TSA signer certificate (#312).
 *
 * tsa_signer_cert_refid points the timestamp signer at an already-issued
 * certificate that carries the timeStamping EKU. The page must:
 *  - fetch and offer only the server-supplied candidates,
 *  - carry signer_cert_refid in the PATCH payload,
 *  - keep the strict require_dedicated_cert toggle inoperable until a usable
 *    dedicated signer is saved (otherwise every timestamp request 503s).
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
  useAuth: () => ({ permissions: ['read:settings', 'write:settings', 'read:cas'] }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

vi.mock('../../services/cas.service', () => ({
  casService: {
    getAll: vi.fn().mockResolvedValue({ data: [{ id: 1, refid: 'ca-tsa', name: 'TSA CA' }] }),
  },
}))

vi.mock('../../services/tsa.service', () => ({
  tsaService: {
    getConfig: vi.fn(),
    updateConfig: vi.fn().mockResolvedValue({ data: {} }),
    getStats: vi.fn().mockResolvedValue({ data: { total_requests: 0 } }),
    getSignerCandidates: vi.fn(),
  },
}))

import TSAPage from '../TSAPage'
import { tsaService } from '../../services/tsa.service'

const CANDIDATES = [
  {
    refid: 'cert-ts-1', descr: 'UCM Timestamp Signer', subject_cn: 'UCM Timestamp Signer',
    serial_number: '7', key_type: 'RSA 2048', valid_to: '2027-02-01T00:00:00+00:00',
    eku_critical_exclusive: true,
  },
]

const USABLE_SIGNER = {
  configured: true, usable: true, refid: 'cert-ts-1', subject: 'CN=UCM Timestamp Signer',
  not_after: '2027-02-01T00:00:00+00:00', chain_len: 2, chain_to_root: true,
}

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
  const settingsTabs = await screen.findAllByText('tsa.groups.settings')
  fireEvent.click(settingsTabs[settingsTabs.length - 1])
}

describe('TSAPage — dedicated signer certificate (#312)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    tsaService.updateConfig.mockResolvedValue({ data: {} })
    tsaService.getStats.mockResolvedValue({ data: { total_requests: 0 } })
    tsaService.getSignerCandidates.mockResolvedValue({ data: CANDIDATES })
    setConfig()
  })

  it('fetches signer candidates and renders the signing-certificate section', async () => {
    await openSettingsTab()
    expect(await screen.findByText('tsa.signingCertDesc')).toBeInTheDocument()
    await waitFor(() => expect(tsaService.getSignerCandidates).toHaveBeenCalled())
  })

  it('names the signer by its CN with the description alongside (#365)', async () => {
    tsaService.getSignerCandidates.mockResolvedValue({ data: [
      { ...CANDIDATES[0], subject_cn: 'ts.example.com', descr: 'Renamed signer', eku_critical_exclusive: false },
    ] })
    setConfig({ signer_cert_refid: 'cert-ts-1' })
    await openSettingsTab()
    expect(await screen.findByText('ts.example.com · Renamed signer (RSA 2048)')).toBeInTheDocument()
  })

  it('keeps the strict toggle disabled until a usable signer is saved', async () => {
    await openSettingsTab()
    const label = await screen.findByText('tsa.requireDedicatedCert')
    const toggle = label.closest('label').querySelector('button[role="switch"]')
    expect(toggle).toBeDisabled()
  })

  it('shows a save-to-validate hint when the selection is not yet resolved', async () => {
    // signer_cert_refid is set but config.signer still describes the old state
    setConfig({ signer_cert_refid: 'cert-ts-1', signer: { configured: false } })
    await openSettingsTab()
    expect(await screen.findByText('tsa.signerUnsaved')).toBeInTheDocument()
    const label = screen.getByText('tsa.requireDedicatedCert')
    const toggle = label.closest('label').querySelector('button[role="switch"]')
    expect(toggle).toBeDisabled()
  })

  it('enables the strict toggle once a usable dedicated signer is present', async () => {
    setConfig({ signer_cert_refid: 'cert-ts-1', signer: USABLE_SIGNER })
    await openSettingsTab()
    const label = await screen.findByText('tsa.requireDedicatedCert')
    const toggle = label.closest('label').querySelector('button[role="switch"]')
    expect(toggle).not.toBeDisabled()
  })

  it('leaves the strict toggle operable to switch OFF when it is on with no usable signer', async () => {
    // Recovery path: strict mode is stuck on but the signer is gone.
    setConfig({ signer_cert_refid: '', require_dedicated_cert: true, signer: { configured: false } })
    await openSettingsTab()
    const label = await screen.findByText('tsa.requireDedicatedCert')
    const toggle = label.closest('label').querySelector('button[role="switch"]')
    expect(toggle).not.toBeDisabled()
    expect(screen.getByText('tsa.requireDedicatedCertBlocked')).toBeInTheDocument()
  })

  it('sends signer_cert_refid in the PATCH payload on save', async () => {
    setConfig({ signer_cert_refid: 'cert-ts-1', signer: USABLE_SIGNER })
    await openSettingsTab()
    fireEvent.click(await screen.findByText('common.saveConfiguration'))
    await waitFor(() => expect(tsaService.updateConfig).toHaveBeenCalled())
    expect(tsaService.updateConfig).toHaveBeenCalledWith(
      expect.objectContaining({ signer_cert_refid: 'cert-ts-1' })
    )
  })
})
