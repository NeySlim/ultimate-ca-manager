/**
 * AccountPage mTLS modal — mirrors the backend authorization gates (#253).
 *
 * POST /api/v2/mtls/certificates requires write:user_certificates, and an
 * explicit ca_id naming any CA other than the configured mTLS one
 * additionally requires write:cas. The Generate tab and the issuing-CA
 * dropdown must therefore only be offered to principals the backend will
 * accept — before this gate, a viewer saw a Generate button that could only
 * 403, and a group-granted issuer was offered every CA in the table.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))
const accountMocks = vi.hoisted(() => ({
  getMTLSCertificates: vi.fn(),
  downloadMTLSCertificate: vi.fn(),
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
    showPrompt: vi.fn(),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: ['light', 'dark'] }),
  useWindowManager: () => ({
    openWindow: vi.fn(),
    closeWindow: vi.fn(),
    windows: [],
    prefs: { sameWindow: true, closeOnNav: true },
    updatePrefs: vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
  ThemeProvider: ({ children }) => children,
  NotificationProvider: ({ children }) => children,
  MobileProvider: ({ children }) => children,
  WindowManagerProvider: ({ children }) => children,
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

// The viewer role's scopes, verbatim from backend/auth/permissions.py.
const VIEWER_PERMISSIONS = [
  'read:certificates', 'read:user_certificates', 'read:cas',
  'read:csrs', 'read:templates', 'read:truststore', 'read:ssh',
]

async function openMtlsModal() {
  render(<MemoryRouter><AccountPage /></MemoryRouter>)
  // findAll waits out the initial loading spinner, then switch to Security.
  const securityTabs = await screen.findAllByText('common.security')
  fireEvent.click(securityTabs[0])
  const addButtons = await screen.findAllByText('account.addCertificate')
  fireEvent.click(addButtons[0])
  // The Import tab is offered to every authenticated principal.
  await screen.findAllByText('account.mtlsImport')
}

describe('AccountPage mTLS modal — backend authorization gates', () => {
  beforeEach(() => {
    authState.permissions = []
    accountMocks.getMTLSCertificates.mockResolvedValue({ data: [] })
    accountMocks.downloadMTLSCertificate.mockResolvedValue(new Blob())
  })

  it('offers no Generate tab without write:user_certificates', async () => {
    authState.permissions = [...VIEWER_PERMISSIONS]
    await openMtlsModal()
    expect(screen.queryByText('account.mtlsGenerate')).not.toBeInTheDocument()
    expect(screen.queryByText('account.generateCertificate')).not.toBeInTheDocument()
    // The modal falls through to Import instead of an action that 403s.
    expect(screen.getByText('account.mtlsPemData')).toBeInTheDocument()
  })

  it('offers Generate but no issuing-CA choice with write:user_certificates alone', async () => {
    authState.permissions = [...VIEWER_PERMISSIONS, 'write:user_certificates']
    await openMtlsModal()
    expect(screen.getByText('account.mtlsGenerate')).toBeInTheDocument()
    expect(screen.getByText('account.generateCertificate')).toBeInTheDocument()
    // Any CA but the configured one 403s without write:cas, and the page
    // cannot know which is configured — so it offers no choice at all and
    // the backend issues from the configured mTLS CA.
    expect(screen.queryByText('account.mtlsIssuingCA')).not.toBeInTheDocument()
  })

  it('offers the issuing-CA choice to holders of write:cas', async () => {
    authState.permissions = [
      ...VIEWER_PERMISSIONS, 'write:user_certificates', 'write:cas',
    ]
    await openMtlsModal()
    expect(screen.getByText('account.mtlsGenerate')).toBeInTheDocument()
    expect(screen.getByText('account.mtlsIssuingCA')).toBeInTheDocument()
  })

  it('keeps the full generate flow for the admin wildcard', async () => {
    authState.permissions = ['*']
    await openMtlsModal()
    expect(screen.getByText('account.mtlsGenerate')).toBeInTheDocument()
    expect(screen.getByText('account.mtlsIssuingCA')).toBeInTheDocument()
  })

  it('passes the Root CA choice to the account PKCS#12 export', async () => {
    authState.permissions = ['*']
    accountMocks.getMTLSCertificates.mockResolvedValue({
      data: [{
        id: 42,
        name: 'Account mTLS certificate',
        enabled: true,
        valid_until: '2030-01-01T00:00:00Z',
      }],
    })
    render(<MemoryRouter><AccountPage /></MemoryRouter>)
    const securityTabs = await screen.findAllByText('common.security')
    fireEvent.click(securityTabs[0])
    await screen.findByText('Account mTLS certificate')
    fireEvent.click(screen.getByLabelText('common.export'))
    fireEvent.click(screen.getByText('P12 / PKCS#12'))
    fireEvent.click(screen.getByText('export.includeRoot'))
    fireEvent.change(screen.getByPlaceholderText('export.passwordLengthHint'), {
      target: { value: 'account-export-password' },
    })
    fireEvent.click(screen.getByText('export.download'))

    await vi.waitFor(() => expect(accountMocks.downloadMTLSCertificate).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        format: 'pkcs12',
        includeChain: true,
        includeRoot: true,
      }),
    ))
  })
})

describe('AccountPage mTLS export of a post-quantum certificate', () => {
  beforeEach(() => { authState.permissions = ['*'] })

  // Key fields as GET /mtls/certificates sends them (AuthCertificate.to_dict)
  const KEYS = {
    'ML-DSA-65': { key_type: 'ML-DSA-65', key_algorithm: 'ML-DSA-65', key_size: null, security_level: 3, post_quantum: true },
    RSA: { key_type: 'RSA 2048', key_algorithm: 'RSA', key_size: 2048, security_level: null, post_quantum: false },
  }
  it.each([
    ['ML-DSA-65', false],
    ['RSA', true],
  ])('a %s certificate is offered PKCS#12 and JKS: %s', async (keyAlgorithm, offered) => {
    accountMocks.getMTLSCertificates.mockResolvedValue({
      data: [{
        id: 43, name: 'Account mTLS certificate', enabled: true, cert_serial: '2b', cert_subject: 'CN=admin',
        valid_until: '2030-01-01T00:00:00Z', ...KEYS[keyAlgorithm],
      }],
    })
    render(<MemoryRouter><AccountPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByText('common.security'))[0])
    await screen.findByText('Account mTLS certificate')
    fireEvent.click(screen.getByLabelText('common.export'))
    expect(screen.getByText('P12 / PKCS#12').closest('button').disabled).toBe(!offered)
    expect(screen.getByText('JKS').closest('button').disabled).toBe(!offered)
    expect(screen.getByText('PEM').closest('button')).toBeEnabled()
  })
})
