/**
 * TSAPage: the page says when the CA certificate signs (strict verifiers refuse
 * those tokens) and when the policy OID is still OpenSSL's example, and shows
 * the request total the stats API returns.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { id: 1, username: 'op', role: 'operator' } }),
  useNotification: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showInfo: vi.fn(),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: ['light', 'dark'] }),
  useInspector: () => ({
    openEntity: vi.fn(),
    closeWindow: vi.fn(),
    windows: [],
    prefs: { sameWindow: true, closeOnNav: true },
    updatePrefs: vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
  ThemeProvider: ({ children }) => children,
  NotificationProvider: ({ children }) => children,
  MobileProvider: ({ children }) => children,
  InspectorProvider: ({ children }) => children,
}))

// usePermission reads `permissions` from AuthContext; write:settings guards
// the save button, exactly as the sibling settings on this page.
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: ['read:settings', 'write:settings', 'read:cas'] }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

const config = vi.hoisted(() => ({ current: {} }))

vi.mock('../../services/tsa.service', () => ({
  tsaService: {
    getConfig: vi.fn(() => Promise.resolve({ data: config.current })),
    updateConfig: vi.fn().mockResolvedValue({ data: {} }),
    getStats: vi.fn().mockResolvedValue({ data: { total: 17, successful: 15, failed: 2 } }),
    getSignerCandidates: vi.fn().mockResolvedValue({ data: [] }),
  },
}))

vi.mock('../../services/cas.service', () => ({
  casService: {
    getAll: vi.fn().mockResolvedValue({
      data: [{ id: 1, refid: 'ca-tsa-probe', name: 'TSA CA' }],
    }),
  },
}))

import TSAPage from '../TSAPage'

const CA_SIGNS = {
  enabled: true, ca_refid: 'ca-tsa-probe', policy_oid: '1.2.3.4.1',
  require_dedicated_cert: false, signer_cert_refid: '', signer: { configured: false },
}
const DEDICATED = {
  enabled: true, ca_refid: 'ca-tsa-probe', policy_oid: '1.3.6.1.4.1.55555.1',
  require_dedicated_cert: false, signer_cert_refid: 'cert-tsa-signer',
  signer: {
    configured: true, usable: true, refid: 'cert-tsa-signer', subject: 'CN=Signer',
    not_after: '2027-01-01T00:00:00+00:00', chain_len: 2, chain_to_root: true,
  },
}

async function openSettingsTab() {
  render(<MemoryRouter><TSAPage /></MemoryRouter>)
  const settingsTabs = await screen.findAllByText('tsa.groups.settings')
  fireEvent.click(settingsTabs[settingsTabs.length - 1])
  await screen.findByText('tsa.signingCertDesc')
}

describe('TSAPage warnings and stats', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('warns while the CA certificate signs and the policy is the example OID', async () => {
    config.current = CA_SIGNS
    await openSettingsTab()
    expect(screen.getByText('tsa.caSignerWarning')).toBeInTheDocument()
    expect(screen.getByText('tsa.policyPlaceholderWarning')).toBeInTheDocument()
  })

  it('drops both warnings with a dedicated signer and an own policy OID', async () => {
    config.current = DEDICATED
    await openSettingsTab()
    expect(screen.queryByText('tsa.caSignerWarning')).not.toBeInTheDocument()
    expect(screen.queryByText('tsa.policyPlaceholderWarning')).not.toBeInTheDocument()
  })

  it('shows the total the stats API returns', async () => {
    config.current = DEDICATED
    await openSettingsTab()
    expect(screen.getAllByText('17').length).toBeGreaterThan(0)
  })
})
