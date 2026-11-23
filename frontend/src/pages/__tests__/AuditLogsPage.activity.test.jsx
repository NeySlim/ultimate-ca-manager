/**
 * Activité (audit journal) drawn from the Atelier mockup: what the page keeps of the journal's
 * functions, on the mockup's structure (filters, server pages, detail, export, clean-up, states).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))
const auth = vi.hoisted(() => ({ permissions: ['*'] }))
const inspector = vi.hoisted(() => ({ openEntity: vi.fn() }))

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
  useInspector: () => inspector,
}))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: auth.permissions, user: { id: 1 } }) }))

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
vi.mock('../../lib/utils', async (importOriginal) => ({ ...(await importOriginal()), downloadBlob: vi.fn() }))

import auditService from '../../services/audit.service'
import jobsService from '../../services/jobs.service'
import { downloadBlob } from '../../lib/utils'
import AuditLogsPage from '../AuditLogsPage'

const ACTIONS = ['cert_created', 'cert_revoked', 'login_success', 'login_failure', 'user_create', 'ca_created']
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
  rows = [entry(), entry({ id: 40, action: 'login_failure', resource_type: 'user', resource_id: '1', resource_name: null, success: false, username: 'bob' })]
  // page 1 / per_page 1 is the journal's size; page = size is its oldest entry; the rest is the list
  auditService.getLogs.mockImplementation(async (params) => {
    if (params.per_page === 1) return { data: [entry({ id: 1, timestamp: '2026-04-07T08:00:00Z' })], meta: { total: 1234 } }
    return { data: rows, meta: { total: rows.length ? 120 : 0 } }
  })
  auditService.getStats.mockResolvedValue({ data: { success_count: 10, failure_count: 2, unique_users: 3 } })
  auditService.getActions.mockResolvedValue({ data: { actions: ACTIONS, categories: {} } })
  auditService.exportLogs.mockResolvedValue('id,action\n')
  auditService.cleanupLogs.mockResolvedValue({ data: { deleted: 5 } })
  jobsService.list.mockResolvedValue({ data: [] })
})

const listCalls = () => auditService.getLogs.mock.calls.map(([p]) => p).filter((p) => p.per_page !== 1)
const lastList = () => listCalls().at(-1)
const renderPage = (route = '/audit') => render(<MemoryRouter initialEntries={[route]}><AuditLogsPage /></MemoryRouter>)
const ready = async () => { await screen.findByText('device-05.example.com'); await waitFor(() => expect(auditService.getActions).toHaveBeenCalled()) }
const dialog = () => screen.getByRole('dialog')

describe('the journal as the mockup draws it', () => {
  it('shows the page head, the summary and one row per entry', async () => {
    renderPage()
    await ready()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('audit.pageTitle')
    expect(await screen.findByText(/audit\.events.*"count":1234/)).toHaveClass('total')
    expect(screen.getByText(/audit\.since/)).toBeInTheDocument()
    expect(screen.getByText(/audit\.last30.*"success":"10".*"failed":"2"/)).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(
      ['audit.colTime', 'audit.colOperation', 'audit.colResource', 'audit.colUser', 'audit.colResult', 'audit.colDetail'])
    const [, first, second] = within(table).getAllByRole('row')
    expect(first).toHaveTextContent('Cert created')
    expect(first).toHaveTextContent('device-05.example.com')
    expect(first).toHaveTextContent('alice')
    expect(within(first).getByText('audit.badgeOk')).toHaveClass('badge', 'good')
    // no name: the resource type and its id; a failure is said in words, not by colour alone
    expect(second).toHaveTextContent('user #1')
    expect(within(second).getByText('audit.badgeFailed')).toHaveClass('badge', 'bad')
  })

  it('reads the search of the link, as the certificate inspector writes it', async () => {
    renderPage('/audit?search=web.example.com')
    await waitFor(() => expect(lastList()).toMatchObject({ search: 'web.example.com' }))
  })

  it('asks the server for the actions of the chosen operation type', async () => {
    renderPage()
    await ready()
    fireEvent.change(screen.getByRole('combobox', { name: 'audit.typeLabel' }), { target: { value: 'auth' } })
    await waitFor(() => expect(lastList()).toMatchObject({ action: ['login_success', 'login_failure'], page: 1 }))
    // the type options are those present in the server's list
    const options = within(screen.getByRole('combobox', { name: 'audit.typeLabel' })).getAllByRole('option').map((o) => o.value)
    expect(options).toEqual(['', 'issued', 'revoked', 'auth', 'users', 'setup'])
  })

  it('reads nothing when the chosen actions are not of the chosen type', async () => {
    localStorage.setItem('ucm-filter-audit-action', JSON.stringify(['cert_revoked']))
    localStorage.setItem('ucm-filter-audit-type', JSON.stringify('auth'))
    renderPage()
    expect(await screen.findByText('audit.noMatchTitle')).toBeInTheDocument()
    expect(listCalls()).toHaveLength(0)
  })

  it('pages on the server: next, size, jump', async () => {
    renderPage()
    await ready()
    expect(screen.getByText(/audit\.pageRange.*"from":"1".*"to":"50"/)).toBeInTheDocument()
    // the sizes the former list offered
    expect(within(screen.getByRole('combobox', { name: 'audit.perPageLabel' })).getAllByRole('option').map((o) => o.value)).toEqual(['10', '25', '50', '100'])
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await waitFor(() => expect(lastList()).toMatchObject({ page: 2, per_page: 50 }))
    fireEvent.change(screen.getByRole('combobox', { name: 'audit.perPageLabel' }), { target: { value: '25' } })
    await waitFor(() => expect(lastList()).toMatchObject({ page: 1, per_page: 25 }))
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'table.goToPage' }))
    await waitFor(() => expect(lastList()).toMatchObject({ page: 4, per_page: 25 }))
    expect(screen.getByRole('button', { name: 'table.previousPage' })).not.toBeDisabled()
  })

  it('refreshes the list on demand', async () => {
    renderPage()
    await ready()
    const before = listCalls().length
    fireEvent.click(screen.getByRole('button', { name: 'audit.refresh' }))
    await waitFor(() => expect(listCalls().length).toBe(before + 1))
  })
})

describe('the detail of an entry', () => {
  it('shows what the server recorded and opens the certificate it names', async () => {
    renderPage()
    await ready()
    const opener = screen.getByRole('button', { name: 'device-05.example.com' })
    opener.focus()
    fireEvent.click(opener)
    const d = dialog()
    expect(within(d).getByRole('heading', { level: 2 })).toHaveTextContent('Cert created')
    for (const text of ['Issued by Devices CA', 'device-05.example.com', 'alice', '192.0.2.10', 'Mozilla/5.0 probe', 'cert_created']) {
      expect(within(d).getByText(text)).toBeInTheDocument()
    }
    fireEvent.click(within(d).getByRole('button', { name: 'audit.inspectCertificate' }))
    expect(inspector.openEntity).toHaveBeenCalledWith('certificate', 23)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('copies the IP address, as the former detail did', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
    renderPage()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'device-05.example.com' }))
    fireEvent.click(within(dialog()).getByRole('button', { name: 'protocols.copyValue {"name":"audit.ipAddress"}' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('192.0.2.10'))
  })

  it('types the facts of an entry: its result a pill, its address copyable in its value, the client a long row', async () => {
    renderPage()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'device-05.example.com' }))
    const d = dialog()
    expect(d.querySelector('dl.props')).toBeNull()
    const row = (term) => within(d).getByText(term, { selector: 'dt' }).closest('.row')
    expect(row('audit.colResult').querySelector('dd.v .badge.good')).toHaveTextContent('audit.badgeOk')
    expect(row('audit.ipAddress').querySelector('dd.v .code-value')).toHaveTextContent('192.0.2.10')
    expect(row('audit.client')).toHaveClass('long')
    // Nothing but the value's own copy button in the column of values
    expect([...d.querySelectorAll('dl.kv dd.v button')].every((b) => b.closest('.code-value'))).toBe(true)
  })

  it('offers no inspection without the right to read certificates', async () => {
    auth.permissions = ['read:audit']
    renderPage()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'audit.detailOf {"id":41}' }))
    expect(within(dialog()).queryByRole('button', { name: 'audit.inspectCertificate' })).not.toBeInTheDocument()
  })

  it('closes on Escape and on Fermer, and gives the focus back', async () => {
    renderPage()
    await ready()
    const opener = screen.getByRole('button', { name: 'audit.detailOf {"id":41}' })
    opener.focus()
    fireEvent.click(opener)
    fireEvent.keyDown(dialog(), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(document.activeElement).toBe(opener))
    fireEvent.click(opener)
    fireEvent.click(within(dialog()).getByRole('button', { name: 'common.close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('the journal actions', () => {
  it('exports in CSV or JSON with the filters of the list', async () => {
    localStorage.setItem('ucm-filter-audit-username', JSON.stringify('alice'))
    localStorage.setItem('ucm-filter-audit-action', JSON.stringify(['login_failure']))
    localStorage.setItem('ucm-filter-audit-success', JSON.stringify('false'))
    renderPage()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'audit.exportJournal' }))
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.download' }))
    await waitFor(() => expect(auditService.exportLogs).toHaveBeenCalled())
    expect(auditService.exportLogs.mock.calls[0][0]).toMatchObject({
      format: 'csv', username: 'alice', action: ['login_failure'], success: 'false', limit: 10000,
    })
    expect(downloadBlob.mock.calls[0][1]).toMatch(/\.csv$/)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'audit.exportJournal' }))
    fireEvent.click(within(dialog()).getByRole('radio', { name: /JSON/ }))
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.download' }))
    await waitFor(() => expect(auditService.exportLogs.mock.calls[1][0]).toMatchObject({ format: 'json' }))
  })

  it('reaches the export from the actions menu too (the head button is hidden on a phone)', async () => {
    renderPage()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'audit.moreActions' }))
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.exportJournal' }))
    expect(within(dialog()).getByRole('button', { name: 'audit.download' })).toBeInTheDocument()
  })

  it('cleans up old entries with the retention typed, from 30 to 3650 days', async () => {
    renderPage()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'audit.moreActions' }))
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.cleanupLogsEllipsis' }))
    const days = within(dialog()).getByRole('spinbutton')
    fireEvent.change(days, { target: { value: '1' } })
    fireEvent.change(days, { target: { value: '12' } })
    expect(days).toHaveValue(12) // a value is checked when complete, not while it is typed
    fireEvent.change(days, { target: { value: '120' } })
    expect(days).toHaveValue(120)
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.deleteOldLogs' }))
    await waitFor(() => expect(auditService.cleanupLogs).toHaveBeenCalledWith(120))
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: 'audit.moreActions' }))
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.cleanupLogsEllipsis' }))
    // Two years are kept as typed; out of range, nothing is sent and the field says why
    fireEvent.change(within(dialog()).getByRole('spinbutton'), { target: { value: '730' } })
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.deleteOldLogs' }))
    await waitFor(() => expect(auditService.cleanupLogs).toHaveBeenLastCalledWith(730))
    fireEvent.click(screen.getByRole('button', { name: 'audit.moreActions' }))
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.cleanupLogsEllipsis' }))
    for (const value of ['5', '5000', '']) {
      fireEvent.change(within(dialog()).getByRole('spinbutton'), { target: { value } })
      expect(within(dialog()).getByRole('spinbutton')).toHaveAttribute('aria-invalid', 'true')
      expect(within(dialog()).getByRole('button', { name: 'audit.deleteOldLogs' })).toBeDisabled()
    }
    expect(auditService.cleanupLogs).toHaveBeenCalledTimes(2)
  })

  it('offers no clean-up without the right to delete the journal', async () => {
    auth.permissions = ['read:audit']
    renderPage()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'audit.moreActions' }))
    expect(within(dialog()).getByRole('button', { name: 'audit.verifyIntegrity' })).toBeInTheDocument()
    expect(within(dialog()).queryByRole('button', { name: 'audit.cleanupLogsEllipsis' })).not.toBeInTheDocument()
  })
})

describe('the filters the toolbar has no room for', () => {
  const openFilters = () => fireEvent.click(screen.getByRole('button', { name: 'audit.filters' }))

  it('filters on dates, user, result and actions, and shows them as chips', async () => {
    renderPage()
    await ready()
    openFilters()
    const d = dialog()
    fireEvent.change(within(d).getByLabelText('audit.dateFrom'), { target: { value: '2026-11-01' } })
    fireEvent.change(within(d).getByLabelText('audit.dateTo'), { target: { value: '2026-11-08' } })
    fireEvent.change(within(d).getByRole('combobox', { name: 'audit.colUser' }), { target: { value: 'alice' } })
    fireEvent.change(within(d).getByRole('combobox', { name: 'audit.colResult' }), { target: { value: 'false' } })
    fireEvent.click(within(d).getByRole('checkbox', { name: 'User create' }))
    await waitFor(() => expect(lastList()).toMatchObject({
      date_from: '2026-11-01', date_to: '2026-11-08T23:59:59.999999', username: 'alice', success: 'false', action: ['user_create'], page: 1,
    }))
    fireEvent.click(within(d).getByRole('button', { name: 'audit.done' }))
    const chips = screen.getByRole('group', { name: 'table.activeFilters' })
    expect(within(chips).getAllByRole('button')).toHaveLength(5)
    fireEvent.click(within(chips).getByRole('button', { name: /table\.removeFilter.*audit\.chipUser/ }))
    await waitFor(() => expect(lastList().username).toBeUndefined())
  })

  it('narrows the action list to the chosen type', async () => {
    localStorage.setItem('ucm-filter-audit-type', JSON.stringify('auth'))
    renderPage()
    await ready()
    openFilters()
    expect(within(dialog()).getAllByRole('checkbox').map((c) => c.parentElement.textContent)).toEqual(['Login success', 'Login failure'])
  })

  it('applies a shortcut and saves, applies and deletes a filter set', async () => {
    renderPage()
    await ready()
    openFilters()
    fireEvent.click(within(dialog()).getByRole('button', { name: 'common.failedLogins' }))
    await waitFor(() => expect(lastList()).toMatchObject({ action: ['login_failure'] }))
    openFilters()
    fireEvent.change(within(dialog()).getByRole('textbox', { name: 'audit.presetName' }), { target: { value: 'Échecs de connexion' } })
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.savePreset' }))
    const saved = JSON.parse(localStorage.getItem('ucm-audit-presets'))
    expect(saved).toEqual([expect.objectContaining({ name: 'Échecs de connexion', filters: { action: ['login_failure'] } })])
    fireEvent.click(within(dialog()).getByRole('button', { name: 'audit.resetFilters' }))
    await waitFor(() => expect(lastList().action).toBeUndefined())
    openFilters()
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Échecs de connexion' }))
    await waitFor(() => expect(lastList()).toMatchObject({ action: ['login_failure'] }))
    openFilters()
    fireEvent.click(within(dialog()).getByRole('button', { name: /audit\.deletePreset/ }))
    expect(JSON.parse(localStorage.getItem('ucm-audit-presets'))).toEqual([])
  })
})

describe('out of the nominal case', () => {
  it('says why the journal could not be read and reads it again on Réessayer', async () => {
    auditService.getLogs.mockRejectedValue(Object.assign(new Error('down'), { status: 503, request: 'GET /api/v2/audit/logs' }))
    renderPage()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('audit.loadErrorTitle')
    expect(alert).toHaveTextContent(/work\.cause\.status.*"status":503.*GET \/api\/v2\/audit\/logs/)
    const before = listCalls().length
    auditService.getLogs.mockImplementation(async () => ({ data: rows, meta: { total: 2 } }))
    fireEvent.click(within(alert).getByRole('button', { name: 'table.retry' }))
    await screen.findByText('device-05.example.com')
    expect(listCalls().length).toBeGreaterThan(before)
  })

  it('says the journal is empty, with the next action for who may issue', async () => {
    rows = []
    auditService.getLogs.mockImplementation(async () => ({ data: [], meta: { total: 0 } }))
    renderPage()
    expect(await screen.findByText('audit.emptyTitle')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'audit.emptyAction' })).toHaveAttribute('href', '/certificates?action=create')
  })

  it('hides the issue action from who may not issue', async () => {
    auth.permissions = ['read:audit']
    auditService.getLogs.mockImplementation(async () => ({ data: [], meta: { total: 0 } }))
    renderPage()
    await screen.findByText('audit.emptyTitle')
    expect(screen.queryByRole('link', { name: 'audit.emptyAction' })).not.toBeInTheDocument()
  })

  it('says nothing matches a search and resets the filters', async () => {
    renderPage()
    await ready()
    rows = []
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } })
    expect(await screen.findByText('audit.noMatchTitle')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'audit.resetFilters' }))
    await waitFor(() => expect(lastList().search).toBeUndefined())
    expect(screen.getByRole('searchbox')).toHaveValue('')
  })

  it('shows skeleton rows while the first read runs', async () => {
    let release
    auditService.getLogs.mockImplementation((p) => (p.per_page === 1 ? Promise.resolve({ data: [], meta: { total: 0 } }) : new Promise((r) => { release = r })))
    const { container } = renderPage()
    expect(container.querySelectorAll('tr.sk-row')).toHaveLength(12)
    expect(container.querySelector('.table-container')).toHaveAttribute('aria-busy', 'true')
    await act(async () => { release({ data: rows, meta: { total: 2 } }) })
    expect(container.querySelectorAll('tr.sk-row')).toHaveLength(0)
  })
})

describe('a link of the overview', () => {
  it('opens the journal on one UTC day of failures of a type, the last day included', async () => {
    localStorage.setItem('ucm-filter-audit-username', JSON.stringify('bob'))
    auditService.getActions.mockResolvedValue({ data: { actions: [...ACTIONS, 'acme.order.finalize_failed'], categories: {} } })
    renderPage('/audit?type=acme&success=false&date_from=2026-11-14&date_to=2026-11-14')
    await waitFor(() => expect(lastList()).toMatchObject({
      success: 'false', date_from: '2026-11-14', date_to: '2026-11-14T23:59:59.999999', action: ['acme.order.finalize_failed'],
    }))
    expect(lastList().username).toBeUndefined()
    const chips = screen.getByRole('group', { name: 'table.activeFilters' })
    expect(chips).toHaveTextContent('audit.chipFrom')
    expect(chips).toHaveTextContent('audit.chipTo')
  })

  it('opens on the actions of a prefix, the set the overview counts, and reads nothing before it knows them', async () => {
    const acme = ['acme.account.new', 'acme.order.finalize', 'acme.client.renewal_failed']
    auditService.getActions.mockResolvedValue({ data: { actions: [...ACTIONS, ...acme, 'acme_client_renewal_failed', 'dns_provider_test'], categories: {} } })
    renderPage('/audit?action_prefix=acme.&success=false&date_from=2026-11-14&date_to=2026-11-14')
    await waitFor(() => expect(lastList()).toMatchObject({ success: 'false', date_from: '2026-11-14', action: acme }))
    expect(listCalls().every((p) => Array.isArray(p.action) && p.action.length === 3)).toBe(true)
  })

  it('reads nothing for a prefix no action of the journal holds', async () => {
    renderPage('/audit?action_prefix=acme.&success=false&date_from=2026-11-14&date_to=2026-11-14')
    await waitFor(() => expect(lastList()?.action).toEqual(['acme.']))
    expect(listCalls().filter((p) => !p.action)).toHaveLength(0)
  })

  it('ignores a value it does not know', async () => {
    renderPage('/audit?type=nope&success=maybe&date_from=yesterday')
    await ready()
    await waitFor(() => expect(lastList().success).toBeUndefined())
    expect(lastList().date_from).toBeUndefined()
  })
})
