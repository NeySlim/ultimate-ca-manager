/**
 * TSAPage: the strict mode is on unless the API says false, and picking a
 * signer never turns it off behind the operator's back (RFC 3161 §2.3).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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
  useAuth: () => ({ permissions: ['read:settings', 'write:settings', 'read:cas', 'write:certificates'] }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

const config = vi.hoisted(() => ({ current: {} }))

vi.mock('../../services/tsa.service', () => ({
  tsaService: {
    getConfig: vi.fn(() => Promise.resolve({ data: config.current })),
    updateConfig: vi.fn().mockResolvedValue({ data: {} }),
    getStats: vi.fn().mockResolvedValue({ data: { total: 0 } }),
    getSignerCandidates: vi.fn().mockResolvedValue({
      data: [{ refid: 'cert-ts-1', subject: 'CN=Signer', subject_cn: 'Signer', eku_critical_exclusive: true }],
    }),
  },
}))

vi.mock('../../services/cas.service', () => ({
  casService: {
    getAll: vi.fn().mockResolvedValue({ data: [{ id: 1, refid: 'ca-tsa-probe', name: 'TSA CA' }] }),
  },
}))

import TSAPage from '../TSAPage'
import { tsaService } from '../../services/tsa.service'

const STRICT_NO_SIGNER = {
  enabled: true, ca_refid: 'ca-tsa-probe', policy_oid: '1.3.6.1.4.1.55555.1',
  require_dedicated_cert: true, signer_cert_refid: '', signer: { configured: false },
}

async function openSettingsTab() {
  render(<MemoryRouter initialEntries={['/tsa-config?tab=config']}><TSAPage /></MemoryRouter>)
  await screen.findByText('tsa.signingCertDesc')
  await screen.findByText('tsa.signingCertDesc')
}

const strictToggle = () => screen.getByText('tsa.requireDedicatedCert')
  .closest('label').querySelector('input[type="checkbox"]')

describe('TSAPage strict mode by default', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows the strict mode on and offers to generate the missing signer', async () => {
    config.current = STRICT_NO_SIGNER
    await openSettingsTab()
    expect(strictToggle().checked).toBe(true)
    expect(screen.getByText('tsa.strictNoSigner')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /tsa.signerGenerate/ })).not.toBeDisabled()
  })

  it('reads a missing field as strict, the API default', async () => {
    const { require_dedicated_cert: _omitted, ...rest } = STRICT_NO_SIGNER
    config.current = rest
    await openSettingsTab()
    expect(strictToggle().checked).toBe(true)
  })

  it('keeps the strict mode on when a signer is picked', async () => {
    config.current = STRICT_NO_SIGNER
    await openSettingsTab()
    fireEvent.change(screen.getByRole('combobox', { name: 'tsa.signingCert' }), { target: { value: 'cert-ts-1' } })
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(tsaService.updateConfig).toHaveBeenCalled())
    expect(tsaService.updateConfig).toHaveBeenLastCalledWith(
      expect.objectContaining({ signer_cert_refid: 'cert-ts-1', require_dedicated_cert: true }))
  })
})
