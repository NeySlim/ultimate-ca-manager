/**
 * Removing one's own mTLS enrolment revokes its certificate first: when the ACME CA
 * that issued it was not told, the page says so as the user certificates page does.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))
const accountMocks = vi.hoisted(() => ({
  getMTLSCertificates: vi.fn(),
  downloadMTLSCertificate: vi.fn(),
  deleteMTLSCertificate: vi.fn(),
}))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { id: 7, username: 'probe', role: 'viewer' } }),
  useNotification: () => notify,
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

// usePermission reads `permissions` from AuthContext directly.
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

vi.mock('../../services/account.service', () => ({
  accountService: {
    getProfile: vi.fn().mockResolvedValue({
      data: { username: 'probe', email: 'probe@test.local' },
    }),
    getApiKeys: vi.fn().mockResolvedValue({ data: [] }),
    getWebAuthnCredentials: vi.fn().mockResolvedValue({ data: [] }),
    getMTLSCertificates: accountMocks.getMTLSCertificates,
    getAvailableMTLSCertificates: vi.fn().mockResolvedValue({ data: [] }),
    createMTLSCertificate: vi.fn().mockResolvedValue({ data: {} }),
    downloadMTLSCertificate: accountMocks.downloadMTLSCertificate,
    deleteMTLSCertificate: accountMocks.deleteMTLSCertificate,
  },
}))

vi.mock('../../services/cas.service', () => ({
  casService: {
    getAll: vi.fn().mockResolvedValue({
      data: [
        { id: 1, refid: 'ca-mtls-probe', descr: 'Configured mTLS CA', has_private_key: true },
        { id: 2, refid: 'ca-root-probe', descr: 'Root CA', has_private_key: true },
      ],
    }),
  },
}))

vi.mock('../../services/user-certificates.service', () => ({
  userCertificatesService: { export: vi.fn() },
}))

import AccountPage from '../AccountPage'

const OWED = {
  message: 'Certificate revoked in UCM, but the ACME CA did not confirm the revocation (HTTP 503); it is sent again automatically until the CA does. Certificate deleted.',
  meta: { acme_local_only: true, acme_upstream_pending: true, acme_ca_error: 'HTTP 503' },
}

async function deleteTheCertificate() {
  render(<MemoryRouter><AccountPage /></MemoryRouter>)
  const securityTabs = await screen.findAllByText('common.security')
  fireEvent.click(securityTabs[0])
  await screen.findByText('Account mTLS certificate')
  fireEvent.click(screen.getByLabelText('common.delete'))
}

describe('Removing an own mTLS certificate the ACME CA was not told of', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.permissions = ['*']
    notify.showConfirm.mockResolvedValue(true)
    accountMocks.getMTLSCertificates.mockResolvedValue({
      data: [{ id: 42, name: 'Account mTLS certificate', enabled: true, valid_until: '2030-01-01T00:00:00Z' }],
    })
  })

  it('says so instead of a plain success', async () => {
    accountMocks.deleteMTLSCertificate.mockResolvedValue(OWED)
    await deleteTheCertificate()
    await waitFor(() => expect(notify.showWarning).toHaveBeenCalledWith(OWED.message))
    expect(accountMocks.deleteMTLSCertificate).toHaveBeenCalledWith(42)
    expect(notify.showSuccess).not.toHaveBeenCalled()
  })

  it('reports a plain success when nothing was left to the CA', async () => {
    accountMocks.deleteMTLSCertificate.mockResolvedValue(null)
    await deleteTheCertificate()
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith('account.certificateDeleted'))
    expect(notify.showWarning).not.toHaveBeenCalled()
  })
})
