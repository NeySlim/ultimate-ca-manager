/**
 * Shared mocks for Page Rendering smoke tests.
 * Import this file at the top of each split test file.
 */
import { vi, beforeAll } from 'vitest'

// Fix ResizeObserver to be constructable
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

// Mock services that fetch data on mount
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
    getServiceStatus: vi.fn().mockResolvedValue({ data: { is_docker: false } }),
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
vi.mock('../../services/auth-methods.service', () => ({
  authMethodsService: {
    getAvailableMethods: vi.fn().mockResolvedValue({ data: { methods: ['password'] } }),
    checkUsername: vi.fn().mockResolvedValue({ data: { methods: ['password'] } }),
    detectMethods: vi.fn().mockResolvedValue({ password: true, mtls: false, webauthn: false, sso_providers: [] }),
    loginPassword: vi.fn().mockResolvedValue({}),
    login2FA: vi.fn().mockResolvedValue({}),
    loginMTLS: vi.fn().mockResolvedValue({}),
    authenticateWebAuthn: vi.fn().mockResolvedValue({}),
    isWebAuthnSupported: vi.fn().mockReturnValue(false),
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

// Mock contexts
vi.mock('../../contexts', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'admin', email: 'admin@test.com', role: 'admin' },
    isAuthenticated: true,
    isLoading: false,
    loading: false,
    sessionChecked: true,
    login: vi.fn(),
    logout: vi.fn(),
    checkAuth: vi.fn(),
    checkSession: vi.fn(),
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
    loading: false,
    sessionChecked: true,
    login: vi.fn(),
    logout: vi.fn(),
    checkAuth: vi.fn(),
    checkSession: vi.fn(),
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

// ── Shared test wrapper ────────────────────────────────────────────
export function TestWrapper({ children, route = '/' }) {
  const { MemoryRouter } = require('react-router-dom')
  return (
    <MemoryRouter initialEntries={[route]}>
      {children}
    </MemoryRouter>
  )
}
