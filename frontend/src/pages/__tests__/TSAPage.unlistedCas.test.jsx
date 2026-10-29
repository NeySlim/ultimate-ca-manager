/**
 * Both signing-CA pickers of the TSA page (settings and signer generation)
 * list the CAs able to sign, keep the chosen one visible and count the others (#426).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
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
    getAll: vi.fn().mockResolvedValue({ data: [
      { id: 1, refid: 'ca-sign', name: 'Signing CA', has_private_key: true },
      { id: 2, refid: 'ca-keyless', name: 'Keyless root', certificate_only: true, has_private_key: false },
      { id: 3, refid: 'ca-offline', name: 'Offline CA', has_private_key: true, offline: true },
    ] }),
  },
}))

vi.mock('../../services/tsa.service', () => ({
  tsaService: {
    getConfig: vi.fn(),
    updateConfig: vi.fn().mockResolvedValue({ data: {} }),
    getStats: vi.fn().mockResolvedValue({ data: { total_requests: 0 } }),
    getSignerCandidates: vi.fn().mockResolvedValue({ data: [] }),
  },
}))

// A native select exposes the options and the helper text that the real one hides in a portal.
// The extra button picks a CA the way a saved value would, even one no longer listed.
vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, onChange, helperText }) => (
    <div data-testid={`field-${label}`}>
      <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
        <option value="">-</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <button onClick={() => onChange?.('ca-keyless')}>choose-keyless</button>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
}))

import TSAPage from '../TSAPage'
import { tsaService } from '../../services/tsa.service'

async function openSettings(ca_refid) {
  tsaService.getConfig.mockResolvedValue({
    data: { enabled: true, ca_refid, policy_oid: '1.2.3.4.1', signer_cert_refid: '', signer: { configured: false } },
  })
  render(<MemoryRouter><TSAPage /></MemoryRouter>)
  const tabs = await screen.findAllByText('tsa.groups.settings')
  fireEvent.click(tabs[tabs.length - 1])
  return screen.findByTestId('field-tsa.signingCA')
}

const labels = (field) => within(field).getAllByRole('option').filter((o) => o.value !== '').map((o) => o.textContent)

describe('TSAPage signing CA pickers (#426)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    tsaService.getStats.mockResolvedValue({ data: { total_requests: 0 } })
    tsaService.getSignerCandidates.mockResolvedValue({ data: [] })
  })

  it('settings picker offers only the CA that can sign and counts the others', async () => {
    const field = await openSettings('ca-sign')
    expect(labels(field)).toEqual(['Signing CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
  })

  it('settings picker keeps the saved CA without a key listed and counts one less', async () => {
    const field = await openSettings('ca-keyless')
    expect(labels(field)).toEqual(['Signing CA', 'Keyless root'])
    expect(field).toHaveTextContent('cas.notListedForSigning:1')
  })

  it('generation picker follows its own selection, not the saved setting', async () => {
    await openSettings('ca-sign')
    fireEvent.click(await screen.findByText('tsa.signerGenerate'))
    await screen.findByText('tsa.signerGenerateModalDesc')
    const [, field] = screen.getAllByTestId('field-tsa.signingCA')
    expect(labels(field)).toEqual(['Signing CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
    fireEvent.click(within(field).getByText('choose-keyless'))
    expect(labels(field)).toEqual(['Signing CA', 'Keyless root'])
    expect(field).toHaveTextContent('cas.notListedForSigning:1')
  })
})
