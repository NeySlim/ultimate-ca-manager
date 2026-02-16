/**
 * Page Rendering Tests
 * Verifies every page renders without crashing when wrapped in required providers.
 * Uses minimal mocks for services — focuses on "does it mount?" not "does it work?"
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Fix ResizeObserver to be constructable (setup.js mock isn't a proper class)
beforeAll(() => {
  global.ResizeObserver = class ResizeObserver {
    constructor(cb) { this._cb = cb }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

// ── Mock all services (prevent real API calls) ─────────────────────
vi.mock('../../services/apiClient', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    upload: vi.fn().mockResolvedValue({ data: {} }),
    request: vi.fn().mockResolvedValue({ data: {} }),
    setCsrfToken: vi.fn(),
    clearCsrfToken: vi.fn(),
  }
}))

// Mock i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: {
      language: 'en',
      changeLanguage: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
    }
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

// Mock react-grid-layout (DashboardPage uses it)
vi.mock('react-grid-layout', () => ({
  Responsive: ({ children }) => <div data-testid="grid-layout">{children}</div>,
  WidthProvider: (Component) => Component,
  verticalCompactor: vi.fn(),
}))
vi.mock('react-grid-layout/css/styles.css', () => ({}))
vi.mock('react-resizable/css/styles.css', () => ({}))

// Mock recharts
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  AreaChart: ({ children }) => <div>{children}</div>,
  Area: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  PieChart: ({ children }) => <div>{children}</div>,
  Pie: () => null,
  Cell: () => null,
  Legend: () => null,
  BarChart: ({ children }) => <div>{children}</div>,
  Bar: () => null,
}))

// Mock WebSocket hook
vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    subscribe: vi.fn(() => vi.fn()),
    isConnected: false,
    connectionState: 'disconnected',
  }),
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
  default: () => ({
    subscribe: vi.fn(() => vi.fn()),
    isConnected: false,
  }),
}))

// Mock services that fetch data on mount — inline values (vi.mock is hoisted)
vi.mock('../../services/certificates.service', () => ({
  certificatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    create: vi.fn().mockResolvedValue({ data: {} }),
    revoke: vi.fn().mockResolvedValue({ data: {} }),
    download: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/cas.service', () => ({
  casService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    getHierarchy: vi.fn().mockResolvedValue({ data: [] }),
    create: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/csrs.service', () => ({
  csrsService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    sign: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/dashboard.service', () => ({
  dashboardService: {
    getStats: vi.fn().mockResolvedValue({ data: { total_certificates: 0, total_cas: 0, total_csrs: 0, expiring_soon: 0, expired: 0 } }),
    getRecentActivity: vi.fn().mockResolvedValue({ data: [] }),
    getExpiringCerts: vi.fn().mockResolvedValue({ data: [] }),
    getCertTrend: vi.fn().mockResolvedValue({ data: [] }),
    getStatusDistribution: vi.fn().mockResolvedValue({ data: [] }),
    getSystemHealth: vi.fn().mockResolvedValue({ data: { status: 'healthy', checks: {} } }),
  }
}))
vi.mock('../../services/acme.service', () => ({
  acmeService: {
    getAccounts: vi.fn().mockResolvedValue({ data: [] }),
    getOrders: vi.fn().mockResolvedValue({ data: [] }),
    getConfig: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/templates.service', () => ({
  templatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/settings.service', () => ({
  settingsService: {
    getGeneral: vi.fn().mockResolvedValue({ data: {} }),
    getEmail: vi.fn().mockResolvedValue({ data: {} }),
    getSecurity: vi.fn().mockResolvedValue({ data: {} }),
    getAppearance: vi.fn().mockResolvedValue({ data: {} }),
    getBackup: vi.fn().mockResolvedValue({ data: {} }),
    getAudit: vi.fn().mockResolvedValue({ data: {} }),
    getHttps: vi.fn().mockResolvedValue({ data: {} }),
    getDatabase: vi.fn().mockResolvedValue({ data: {} }),
    updateGeneral: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/users.service', () => ({
  usersService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    getGroups: vi.fn().mockResolvedValue({ data: [] }),
    getRoles: vi.fn().mockResolvedValue({ data: [] }),
  }
}))
vi.mock('../../services/audit.service', () => ({
  default: {
    getLogs: vi.fn().mockResolvedValue({ data: [] }),
    getStats: vi.fn().mockResolvedValue({ data: {} }),
    getActions: vi.fn().mockResolvedValue({ data: [] }),
    exportLogs: vi.fn().mockResolvedValue({ data: '' }),
  }
}))
vi.mock('../../services/scep.service', () => ({
  scepService: {
    getConfig: vi.fn().mockResolvedValue({ data: {} }),
    getInfo: vi.fn().mockResolvedValue({ data: {} }),
    getChallenges: vi.fn().mockResolvedValue({ data: [] }),
  }
}))
vi.mock('../../services/crl.service', () => ({
  crlService: {
    getCRLs: vi.fn().mockResolvedValue({ data: [] }),
    getOCSP: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/system.service', () => ({
  systemService: {
    getVersion: vi.fn().mockResolvedValue({ data: { version: '2.0.4' } }),
    getHealth: vi.fn().mockResolvedValue({ data: {} }),
    getInfo: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/account.service', () => ({
  accountService: {
    getProfile: vi.fn().mockResolvedValue({ data: { username: 'admin', email: 'admin@test.com' } }),
    getApiKeys: vi.fn().mockResolvedValue({ data: [] }),
    getSessions: vi.fn().mockResolvedValue({ data: [] }),
  }
}))
vi.mock('../../services/auth.service', () => ({
  authService: {
    login: vi.fn().mockResolvedValue({ data: {} }),
    logout: vi.fn().mockResolvedValue({ data: {} }),
    verify: vi.fn().mockResolvedValue({ data: { authenticated: true, user: { username: 'admin' } } }),
  }
}))
vi.mock('../../services/authMethods.service', () => ({
  authMethodsService: {
    getAvailableMethods: vi.fn().mockResolvedValue({ data: { methods: ['password'] } }),
    checkUsername: vi.fn().mockResolvedValue({ data: { methods: ['password'] } }),
  }
}))
vi.mock('../../services/opnsense.service', () => ({
  opnsenseService: {
    getConfig: vi.fn().mockResolvedValue({ data: {} }),
    sync: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/truststore.service', () => ({
  truststoreService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
  }
}))
vi.mock('../../services/search.service', () => ({
  searchService: {
    search: vi.fn().mockResolvedValue({ data: [] }),
  }
}))


// Mock contexts — all values inline (vi.mock is hoisted)
vi.mock('../../contexts', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'admin', email: 'admin@test.com', role: 'admin' },
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    checkAuth: vi.fn(),
  }),
  useNotification: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showWarning: vi.fn(),
    showInfo: vi.fn(),
    notifications: [],
    removeNotification: vi.fn(),
  }),
  useTheme: () => ({
    theme: 'dark',
    setTheme: vi.fn(),
    resolvedTheme: 'dark',
    themes: ['light', 'dark'],
  }),
  useMobile: () => ({
    isMobile: false,
    isTablet: false,
    sidebarOpen: true,
    setSidebarOpen: vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
  ThemeProvider: ({ children }) => children,
  NotificationProvider: ({ children }) => children,
  MobileProvider: ({ children }) => children,
  useWindowManager: () => ({
    openWindow: vi.fn(),
    closeWindow: vi.fn(),
    windows: [],
    prefs: { sameWindow: true, closeOnNav: true },
    updatePrefs: vi.fn(),
  }),
  WindowManagerProvider: ({ children }) => children,
}))

vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({
    theme: 'dark',
    setTheme: vi.fn(),
    resolvedTheme: 'dark',
    themes: ['light', 'dark'],
    colors: {},
  }),
  ThemeProvider: ({ children }) => children,
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'admin', email: 'admin@test.com', role: 'admin' },
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    checkAuth: vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
}))

vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showWarning: vi.fn(),
    showInfo: vi.fn(),
    notifications: [],
    removeNotification: vi.fn(),
  }),
  NotificationProvider: ({ children }) => children,
}))

vi.mock('../../contexts/MobileContext', () => ({
  useMobile: () => ({
    isMobile: false,
    isTablet: false,
    sidebarOpen: true,
    setSidebarOpen: vi.fn(),
  }),
  MobileProvider: ({ children }) => children,
}))

vi.mock('../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({
    openWindow: vi.fn(),
    closeWindow: vi.fn(),
    windows: [],
    prefs: { sameWindow: true, closeOnNav: true },
    updatePrefs: vi.fn(),
  }),
  WindowManagerProvider: ({ children }) => children,
}))

// ── Test wrapper component ─────────────────────────────────────────
function TestWrapper({ children, route = '/' }) {
  return (
    <MemoryRouter initialEntries={[route]}>
      {children}
    </MemoryRouter>
  )
}

// ── Page imports ───────────────────────────────────────────────────
import LoginPage from '../LoginPage'
import DashboardPage from '../DashboardPage'
import CertificatesPage from '../CertificatesPage'
import CAsPage from '../CAsPage'
import CSRsPage from '../CSRsPage'
import ACMEPage from '../ACMEPage'
import TemplatesPage from '../TemplatesPage'
import SettingsPage from '../SettingsPage'
import UsersGroupsPage from '../UsersGroupsPage'
import AuditLogsPage from '../AuditLogsPage'
import SCEPPage from '../SCEPPage'
import CRLOCSPPage from '../CRLOCSPPage'
import TrustStorePage from '../TrustStorePage'
import ImportExportPage from '../ImportExportPage'
import CertificateToolsPage from '../CertificateToolsPage'
import AccountPage from '../AccountPage'
import ForgotPasswordPage from '../ForgotPasswordPage'
import ResetPasswordPage from '../ResetPasswordPage'
import PoliciesPage from '../PoliciesPage'
import ApprovalsPage from '../ApprovalsPage'
import ReportsPage from '../ReportsPage'


// ════════════════════════════════════════════════════════════════════
// Tests
// ════════════════════════════════════════════════════════════════════

describe('Page Rendering — smoke tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Auth pages (no auth required) ──────────────────────────────
  describe('Auth pages', () => {
    it('LoginPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/login">
          <LoginPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('ForgotPasswordPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/forgot-password">
          <ForgotPasswordPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('ResetPasswordPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/reset-password?token=abc123">
          <ResetPasswordPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })
  })

  // ── Dashboard ──────────────────────────────────────────────────
  describe('Dashboard', () => {
    it('DashboardPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/dashboard">
          <DashboardPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })
  })

  // ── PKI pages ──────────────────────────────────────────────────
  describe('PKI pages', () => {
    it('CertificatesPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/certificates">
          <CertificatesPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('CAsPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/cas">
          <CAsPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('CSRsPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/csrs">
          <CSRsPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('TemplatesPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/templates">
          <TemplatesPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('TrustStorePage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/truststore">
          <TrustStorePage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })
  })

  // ── Protocol pages ─────────────────────────────────────────────
  describe('Protocol pages', () => {
    it('ACMEPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/acme">
          <ACMEPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('SCEPPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/scep">
          <SCEPPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('CRLOCSPPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/crl-ocsp">
          <CRLOCSPPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })
  })

  // ── Admin pages ────────────────────────────────────────────────
  describe('Admin pages', () => {
    it('SettingsPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/settings">
          <SettingsPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('UsersGroupsPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/users">
          <UsersGroupsPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('AuditLogsPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/audit-logs">
          <AuditLogsPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })
  })

  // ── Utility pages ─────────────────────────────────────────────
  describe('Utility pages', () => {
    it('ImportExportPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/import-export">
          <ImportExportPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('CertificateToolsPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/tools">
          <CertificateToolsPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('AccountPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/account">
          <AccountPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })
  })

  // ── Governance pages ─────────────────────────────────────────
  describe('Governance pages', () => {
    it('PoliciesPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/policies">
          <PoliciesPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('ApprovalsPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/approvals">
          <ApprovalsPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })

    it('ReportsPage renders without crashing', () => {
      const { container } = render(
        <TestWrapper route="/reports">
          <ReportsPage />
        </TestWrapper>
      )
      expect(container.firstChild).toBeTruthy()
    })
  })
})
