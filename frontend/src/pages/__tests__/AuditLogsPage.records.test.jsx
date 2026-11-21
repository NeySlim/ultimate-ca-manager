/**
 * Activité on a phone: each entry is a record (the mockup's mobile list) with the same facts as
 * the row, the whole record opens the detail and its chevron reaches it from the keyboard. On a
 * wider screen the short columns of the table are sized to their content.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))
const auth = vi.hoisted(() => ({ permissions: ['*'] }))
const screenSize = vi.hoisted(() => ({ isMobile: true }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, params) => (params ? `${key} ${JSON.stringify(params)}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ i18nKey, values }) => `${i18nKey} ${JSON.stringify(values)}`,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useAuth: () => ({ user: { id: 1, username: 'probe' }, permissions: auth.permissions }),
  useInspector: () => ({ openEntity: vi.fn() }),
}))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: auth.permissions, user: { id: 1 } }) }))
vi.mock('../../contexts/MobileContext', () => ({
  useMobile: () => ({ isMobile: screenSize.isMobile, isTablet: false, isDesktop: !screenSize.isMobile }),
}))
vi.mock('../../services/audit.service', () => ({
  default: {
    getLogs: vi.fn(), getStats: vi.fn(), getActions: vi.fn(),
    verifyIntegrity: vi.fn(), exportLogs: vi.fn(), cleanupLogs: vi.fn(),
  },
}))
vi.mock('../../services/jobs.service', async (importOriginal) => {
  const real = await importOriginal()
  return { ...real, default: { get: vi.fn(), list: vi.fn().mockResolvedValue({ data: [] }), cancel: vi.fn() } }
})

// The first-run state is useSetup's own subject: here it is given
const setup = vi.hoisted(() => ({ state: { visible: false } }))
vi.mock('../../components/shell/useSetup', async (actual) => ({ ...(await actual()), useSetup: () => setup.state }))

import auditService from '../../services/audit.service'
import jobsService from '../../services/jobs.service'
import AuditLogsPage from '../AuditLogsPage'

const entry = (over = {}) => ({
  id: 41, timestamp: '2026-11-08T10:42:18Z', username: 'alice', action: 'cert_created',
  resource_type: 'certificate', resource_id: '23', resource_name: 'device-05.example.com',
  details: 'Issued by Devices CA', ip_address: '192.0.2.10', user_agent: 'Mozilla/5.0 probe', success: true, ...over,
})
let rows

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  auth.permissions = ['*']
  setup.state = { visible: false }
  screenSize.isMobile = true
  rows = [entry(), entry({ id: 40, action: 'login_failure', resource_type: 'user', resource_id: '1', resource_name: null, success: false, username: 'bob' })]
  auditService.getLogs.mockImplementation(async (params) => {
    if (params.per_page === 1) return { data: [entry({ id: 1 })], meta: { total: rows.length ? 1234 : 0 } }
    return { data: rows, meta: { total: rows.length ? 120 : 0 } }
  })
  auditService.getStats.mockResolvedValue({ data: { success_count: 10, failure_count: 2, unique_users: 3 } })
  auditService.getActions.mockResolvedValue({ data: { actions: ['cert_created', 'login_failure'], categories: {} } })
  jobsService.list.mockResolvedValue({ data: [] })
})

const renderPage = () => render(<MemoryRouter initialEntries={['/audit']}><AuditLogsPage /></MemoryRouter>)
const records = (container) => [...container.querySelectorAll('article.mobile-record:not(.sk-record)')]

describe('the journal on a phone', () => {
  it('draws one record per entry with every fact of the row, and no table', async () => {
    const { container } = renderPage()
    await screen.findByText('device-05.example.com')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    const [first, second] = records(container)
    expect(records(container)).toHaveLength(2)
    // resource, operation, user, result and time, as the six columns of the row
    expect(within(first).getByRole('button', { name: 'device-05.example.com' })).toHaveClass('entity-name')
    expect(first.querySelector('.row-meta')).toHaveTextContent('Cert created')
    expect(first.querySelector('.row-meta')).toHaveTextContent('alice')
    expect(within(first).getByText('audit.badgeOk')).toHaveClass('badge', 'good')
    expect(first.querySelector('.row-status .remaining').textContent).toMatch(/\d{2}:\d{2}:\d{2}/)
    expect(within(second).getByRole('button', { name: 'user #1' })).toBeInTheDocument()
    expect(within(second).getByText('audit.badgeFailed')).toHaveClass('badge', 'bad')
    // the chevron of the row stays, at the right of the record's first line
    const chevron = within(first).getByRole('button', { name: 'audit.detailOf {"id":41}' })
    expect(chevron.parentElement).toHaveClass('row-top')
    expect(chevron.parentElement.lastElementChild).toBe(chevron)
  })

  it('opens the detail from anywhere on the record', async () => {
    const { container } = renderPage()
    await screen.findByText('device-05.example.com')
    fireEvent.click(records(container)[0].querySelector('.row-status .remaining'))
    expect(within(screen.getByRole('dialog')).getByRole('heading', { level: 2 })).toHaveTextContent('Cert created')
  })

  // The keys themselves are pressed in a real browser (e2e/activity-columns.spec.ts): the jsdom
  // dialog moves the focus inside before user-event ends the key press.
  it('reaches the detail from the keyboard: the chevron and the name are buttons, the focus comes back', async () => {
    renderPage()
    await screen.findByText('device-05.example.com')
    const chevron = screen.getByRole('button', { name: 'audit.detailOf {"id":40}' })
    const name = screen.getByRole('button', { name: 'device-05.example.com' })
    for (const control of [chevron, name]) {
      expect(control.tagName).toBe('BUTTON')
      expect(control).toHaveAttribute('type', 'button')
    }
    chevron.focus()
    fireEvent.click(chevron)
    expect(within(screen.getByRole('dialog')).getByRole('heading', { level: 2 })).toHaveTextContent('Login failure')
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(document.activeElement).toBe(chevron))
    name.focus()
    fireEvent.click(name)
    expect(within(screen.getByRole('dialog')).getByRole('heading', { level: 2 })).toHaveTextContent('Cert created')
  })

  it('shows record skeletons while the first read runs, then the records', async () => {
    let release
    auditService.getLogs.mockImplementation((p) => (p.per_page === 1 ? Promise.resolve({ data: [], meta: { total: 0 } }) : new Promise((r) => { release = r })))
    const { container } = renderPage()
    expect(container.querySelectorAll('article.sk-record')).toHaveLength(6)
    expect(screen.getByRole('status')).toHaveTextContent('table.loadingRows')
    await act(async () => { release({ data: rows, meta: { total: 2 } }) })
    expect(container.querySelectorAll('article.sk-record')).toHaveLength(0)
    expect(records(container)).toHaveLength(2)
  })

  it('says an empty journal in the list of records', async () => {
    rows = []
    const { container } = renderPage()
    expect(await screen.findByText('audit.emptyTitle')).toBeInTheDocument()
    expect(container.querySelector('.mobile-list #empty-activity')).toBeInTheDocument()
    expect(within(container.querySelector('#empty-activity')).getByRole('link', { name: 'audit.emptyAction' })).toHaveAttribute('href', '/certificates?action=create')
  })

  it('leads an empty journal to the setup assistant while its steps remain', async () => {
    rows = []
    setup.state = { visible: true, complete: false }
    const { container } = renderPage()
    await screen.findByText('audit.emptyTitle')
    const block = container.querySelector('#empty-activity')
    expect(within(block).getByRole('link', { name: 'shell.setup.open' })).toHaveAttribute('href', '/')
    expect(within(block).queryByRole('link', { name: 'audit.emptyAction' })).toBeNull()
  })
})

describe('the table on a wider screen', () => {
  it('sizes the time, user, result and chevron columns to their content, not operation and resource', async () => {
    screenSize.isMobile = false
    const { container } = renderPage()
    await screen.findByText('device-05.example.com')
    expect(container.querySelector('.mobile-list')).not.toBeInTheDocument()
    const fit = within(screen.getByRole('table')).getAllByRole('columnheader').map((th) => th.classList.contains('fit'))
    expect(fit).toEqual([true, false, false, true, true, true])
  })
})
