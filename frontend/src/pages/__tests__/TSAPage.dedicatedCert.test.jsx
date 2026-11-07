/**
 * TSAPage — the tsa_require_dedicated_cert switch is operable from the UI.
 *
 * The #246 review flagged that the switch existed only as a hand-inserted
 * SystemConfig row: GET/PATCH /api/v2/tsa/config never carried it and the
 * TSA page had no control for it. The page must render the toggle wired to
 * config.require_dedicated_cert and include it in the PATCH payload.
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

vi.mock('../../services/tsa.service', () => ({
  tsaService: {
    getConfig: vi.fn().mockResolvedValue({
      data: {
        enabled: true,
        ca_refid: 'ca-tsa-probe',
        policy_oid: '1.2.3.4.1',
        require_dedicated_cert: false,
        // A usable dedicated signer is saved, so the strict-mode toggle is
        // operable (it is gated on one being present, #312).
        signer_cert_refid: 'cert-tsa-signer',
        signer: {
          configured: true,
          usable: true,
          refid: 'cert-tsa-signer',
          subject: 'CN=UCM Timestamp Signer',
          not_after: '2027-01-01T00:00:00+00:00',
          chain_len: 2,
          chain_to_root: true,
        },
      },
    }),
    updateConfig: vi.fn().mockResolvedValue({ data: {} }),
    getStats: vi.fn().mockResolvedValue({ data: { total: 0 } }),
    getSignerCandidates: vi.fn().mockResolvedValue({
      data: [
        {
          refid: 'cert-tsa-signer',
          descr: 'UCM Timestamp Signer',
          subject_cn: 'UCM Timestamp Signer',
          serial_number: '42',
          valid_to: '2027-01-01T00:00:00+00:00',
          eku_critical_exclusive: true,
        },
      ],
    }),
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
import { tsaService } from '../../services/tsa.service'

/** Render the page and open the Settings tab (the layout starts on the
 *  mobile tab menu under jsdom's matchMedia mock). */
async function openSettingsTab() {
  render(<MemoryRouter><TSAPage /></MemoryRouter>)
  const settingsTabs = await screen.findAllByText('tsa.groups.settings')
  fireEvent.click(settingsTabs[settingsTabs.length - 1])
}

describe('TSAPage — require_dedicated_cert toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the toggle for the dedicated-certificate requirement', async () => {
    await openSettingsTab()
    expect(await screen.findByText('tsa.requireDedicatedCert')).toBeInTheDocument()
    expect(screen.getByText('tsa.requireDedicatedCertDesc')).toBeInTheDocument()
  })

  it('sends require_dedicated_cert in the PATCH payload after toggling', async () => {
    await openSettingsTab()
    const label = await screen.findByText('tsa.requireDedicatedCert')
    fireEvent.click(label)

    fireEvent.click(screen.getByText('common.saveConfiguration'))

    await waitFor(() => expect(tsaService.updateConfig).toHaveBeenCalled())
    expect(tsaService.updateConfig).toHaveBeenCalledWith(
      expect.objectContaining({ require_dedicated_cert: true })
    )
  })
})
