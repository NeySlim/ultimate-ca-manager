/**
 * AuditLogsPage: the export sends the filters the list shows, not only the dates.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, params) => (params ? `${key} ${JSON.stringify(params)}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useAuth: () => ({ user: { id: 1, username: 'probe' }, permissions: ['*'] }),
  useMobile: () => ({ isMobile: false, isTablet: false, isDesktop: true, isTouch: false, isLargeScreen: true, screenWidth: 1440, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: ['light', 'dark'] }),
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))

vi.mock('../../contexts/MobileContext', () => ({
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: ['*'] }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

vi.mock('../../services/audit.service', () => ({
  default: {
    getLogs: vi.fn().mockResolvedValue({ data: [], meta: { total: 0 } }),
    getStats: vi.fn().mockResolvedValue({ data: {} }),
    getActions: vi.fn().mockResolvedValue({ data: [] }),
    verifyIntegrity: vi.fn(),
    exportLogs: vi.fn().mockResolvedValue('[]'),
  },
}))

vi.mock('../../services/jobs.service', async (importOriginal) => {
  const real = await importOriginal()
  return { ...real, default: { get: vi.fn(), list: vi.fn(), cancel: vi.fn() } }
})

vi.mock('../../lib/utils', async (importOriginal) => ({
  ...(await importOriginal()), downloadBlob: vi.fn(),
}))

import auditService from '../../services/audit.service'
import jobsService from '../../services/jobs.service'
import AuditLogsPage from '../AuditLogsPage'

beforeEach(() => {
  vi.clearAllMocks()
  jobsService.list.mockResolvedValue({ data: [] })
  localStorage.clear()
})

describe('AuditLogsPage export', () => {
  it('sends the username, action and success filters of the list', async () => {
    localStorage.setItem('ucm-filter-audit-username', JSON.stringify('alice'))
    localStorage.setItem('ucm-filter-audit-action', JSON.stringify(['login']))
    localStorage.setItem('ucm-filter-audit-success', JSON.stringify('false'))
    render(<MemoryRouter><AuditLogsPage /></MemoryRouter>)
    await waitFor(() => expect(auditService.getLogs).toHaveBeenCalled())
    fireEvent.click((await screen.findAllByText('common.date'))[0])
    fireEvent.click((await screen.findAllByText('CSV'))[0])
    await waitFor(() => expect(auditService.exportLogs).toHaveBeenCalled())
    expect(auditService.exportLogs.mock.calls[0][0]).toMatchObject({
      format: 'csv', username: 'alice', action: ['login'], success: 'false',
    })
  })
})
