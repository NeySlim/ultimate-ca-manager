/**
 * AuditLogsPage — a verification that outlasts the request answers 202 with a job: the
 * page follows it, shows its progress, offers to cancel it, and picks it up after a reload.
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
  },
}))

vi.mock('../../services/jobs.service', async (importOriginal) => {
  const real = await importOriginal()
  return { ...real, default: { get: vi.fn(), list: vi.fn(), cancel: vi.fn() } }
})

import auditService from '../../services/audit.service'
import jobsService from '../../services/jobs.service'
import AuditLogsPage from '../AuditLogsPage'

const intact = { valid: true, status: 'intact', checked: 3, protection: { key_available: true } }
const running = { id: 'j1', kind: 'audit_verify', state: 'running', progress: { done: 2000, total: 9000 } }

beforeEach(() => {
  vi.clearAllMocks()
  jobsService.list.mockResolvedValue({ data: [] })
})

const renderPage = () => render(<MemoryRouter><AuditLogsPage /></MemoryRouter>)
// The check lives in the journal's actions (the page head's « ⋯ »)
const startVerification = async () => {
  fireEvent.click(await screen.findByRole('button', { name: 'audit.moreActions' }))
  fireEvent.click(await screen.findByText('audit.verifyIntegrity'))
}

describe('AuditLogsPage verification job', () => {
  it('shows a result answered within the wait as before', async () => {
    auditService.verifyIntegrity.mockResolvedValueOnce({ data: intact })
    renderPage()
    await startVerification()
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalled())
    expect(jobsService.get).not.toHaveBeenCalled()
  })

  it('follows a 202 job, shows its progress and its result', async () => {
    auditService.verifyIntegrity.mockResolvedValueOnce({ data: { job: running } })
    jobsService.get.mockResolvedValueOnce({ data: { ...running, state: 'succeeded', result: { code: 200, data: intact } } })
    renderPage()
    await startVerification()
    expect(await screen.findByText(/audit\.verifyProgress.*"done":2000.*"total":9000/)).toBeInTheDocument()
    expect(screen.getByTestId('audit-verify-cancel')).toBeInTheDocument()
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalled(), { timeout: 3000 })
    expect(screen.queryByTestId('audit-verify-cancel')).not.toBeInTheDocument()
  })

  it('cancels the job it follows and says so', async () => {
    auditService.verifyIntegrity.mockResolvedValueOnce({ data: { job: running } })
    jobsService.cancel.mockResolvedValueOnce({ data: { ...running, cancel_requested: true } })
    jobsService.get.mockResolvedValue({ data: { ...running, state: 'cancelled', reason: 'cancelled' } })
    renderPage()
    await startVerification()
    fireEvent.click(await screen.findByTestId('audit-verify-cancel'))
    await waitFor(() => expect(jobsService.cancel).toHaveBeenCalledWith('j1'))
    await waitFor(() => expect(notify.showWarning).toHaveBeenCalledWith('audit.verifyCancelled'), { timeout: 3000 })
  })

  it('picks a running verification up after a reload and reports a lost one', async () => {
    jobsService.list.mockResolvedValueOnce({ data: [running] })
    jobsService.get.mockResolvedValueOnce({ data: { ...running, state: 'failed', reason: 'executor_lost' } })
    renderPage()
    expect(await screen.findByText(/audit\.verifyProgress/)).toBeInTheDocument()
    await waitFor(() => expect(notify.showError).toHaveBeenCalledWith('audit.verifyLost'), { timeout: 3000 })
  })
})
