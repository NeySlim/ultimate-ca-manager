/**
 * AccountPage: enrolling an mTLS certificate asks the password first and sends it
 * with the request; cancelling the prompt sends nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))
const accountMocks = vi.hoisted(() => ({
  getMTLSCertificates: vi.fn(),
  downloadMTLSCertificate: vi.fn(),
  importMTLSCertificate: vi.fn(),
  showPrompt: vi.fn(),
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
  useNotification: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showConfirm: vi.fn(),
    showPrompt: accountMocks.showPrompt,
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
      data: { username: 'probe', email: 'probe@test.local', has_local_password: true },
    }),
    getApiKeys: vi.fn().mockResolvedValue({ data: [] }),
    getWebAuthnCredentials: vi.fn().mockResolvedValue({ data: [] }),
    getMTLSCertificates: accountMocks.getMTLSCertificates,
    getAvailableMTLSCertificates: vi.fn().mockResolvedValue({ data: [] }),
    createMTLSCertificate: vi.fn().mockResolvedValue({ data: {} }),
    downloadMTLSCertificate: accountMocks.downloadMTLSCertificate,
    importMTLSCertificate: accountMocks.importMTLSCertificate,
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

const PEM = '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----'

async function importWith(answer) {
  accountMocks.showPrompt.mockResolvedValue(answer)
  render(<MemoryRouter><AccountPage /></MemoryRouter>)
  fireEvent.click((await screen.findAllByText('common.security'))[0])
  fireEvent.click((await screen.findAllByText('account.addCertificate'))[0])
  await screen.findAllByText('account.mtlsImport')
  fireEvent.change(document.querySelector('#mtls-pem'), { target: { value: PEM } })
  fireEvent.click(screen.getByText('account.importCertificate'))
  await waitFor(() => expect(accountMocks.showPrompt).toHaveBeenCalled())
}

describe('AccountPage mTLS enrolment asks the password', () => {
  beforeEach(() => {
    authState.permissions = ['read:certificates']
    accountMocks.getMTLSCertificates.mockResolvedValue({ data: [] })
    accountMocks.importMTLSCertificate.mockReset().mockResolvedValue({ data: {} })
    accountMocks.showPrompt.mockReset()
  })

  it('sends the password typed in the prompt', async () => {
    await importWith('s3cret')
    await waitFor(() => expect(accountMocks.importMTLSCertificate).toHaveBeenCalledWith(PEM, '', { password: 's3cret' }))
    expect(accountMocks.showPrompt.mock.calls[0][1]).toMatchObject({ type: 'password' })
  })

  it('sends nothing once the prompt is cancelled', async () => {
    await importWith(null)
    await new Promise((r) => setTimeout(r, 20))
    expect(accountMocks.importMTLSCertificate).not.toHaveBeenCalled()
  })
})
