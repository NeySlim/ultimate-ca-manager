/**
 * The settings lists that grow (webhooks, Microsoft AC connections, security anomalies) as the
 * Active Directory table: search, sort by header, pages of 25 past ten rows, the common empty
 * block, and the row actions the viewer's permissions grant.
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render as rtlRender, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import '../../__tests__/pageRenderingSetup.jsx'
import WebhooksSection from '../WebhooksSection'
import MicrosoftCASection from '../MicrosoftCASection'
import AnomalyList from '../AnomalyList'

vi.mock('../WebhookDeliveriesModal', () => ({ default: ({ webhook }) => (webhook ? <p>deliveries-of-{webhook.name}</p> : null) }))

// The lists keep their sort in the address
const render = (ui) => rtlRender(ui, { wrapper: MemoryRouter })
const can = (...granted) => (p) => granted.includes(p)
const pad = (n) => String(n).padStart(2, '0')
const rows = () => [...document.querySelectorAll('table.module-table tbody tr')]
const names = () => rows().map((tr) => tr.querySelector('th, td').textContent.trim())
const search = (id, value) => fireEvent.change(document.getElementById(id), { target: { value } })

const HOOKS = Array.from({ length: 30 }, (_, i) => ({
  id: i + 1, name: `hook-${pad(i + 1)}`, url: `https://h${pad(i + 1)}.example.com/in`, enabled: i % 2 === 0,
  events: i === 6 ? ['certificate.revoked'] : ['certificate.issued'],
}))

const hooks = (list, perm, handlers = {}) => render(
  <WebhooksSection webhooks={list} webhooksLoading={false} handleWebhookCreate={vi.fn()} handleWebhookEdit={vi.fn()}
    handleWebhookToggle={vi.fn()} handleWebhookTest={vi.fn()} setWebhookConfirmDelete={vi.fn()} hasPermission={perm} {...handlers} />,
)

describe('webhooks table', () => {
  it('pages a long list by 25 in the module table', () => {
    hooks(HOOKS, can('read:settings'))
    expect(document.querySelector('.record-list')).toBeNull()
    expect(document.querySelector('[data-action="records-more"]')).toBeNull()
    expect(rows()).toHaveLength(25)
    fireEvent.click(document.querySelector('[data-page="next"]'))
    expect(names()).toEqual(['hook-26', 'hook-27', 'hook-28', 'hook-29', 'hook-30'])
  })

  it('finds a webhook by its address or an event', () => {
    hooks(HOOKS, can('read:settings'))
    search('webhook-search', 'h17.example')
    expect(names()).toEqual(['hook-17'])
    search('webhook-search', 'certificate.revoked')
    expect(names()).toEqual(['hook-07'])
    search('webhook-search', 'nowhere')
    expect(screen.getByText('common.noResults')).toBeInTheDocument()
  })

  it('sorts by a header, the second click reversing', () => {
    hooks(HOOKS, can('read:settings'))
    fireEvent.click(document.querySelector('button[data-sort="name"]'))
    expect(names()[0]).toBe('hook-30')
    fireEvent.click(document.querySelector('button[data-sort="state"]'))
    expect(rows().slice(0, 15).every((tr) => tr.textContent.includes('common.enabled'))).toBe(true)
  })

  it('shows the common empty block when there is no webhook', () => {
    hooks([], can('read:settings', 'admin:system'))
    expect(document.getElementById('empty-webhooks')).toHaveTextContent('webhooks.noWebhooks')
    expect(rows()).toHaveLength(1)
  })

  it('keeps the row actions and their permissions', () => {
    const handleWebhookTest = vi.fn()
    const setWebhookConfirmDelete = vi.fn()
    hooks(HOOKS.slice(0, 2), can('read:settings', 'write:settings'), { handleWebhookTest, setWebhookConfirmDelete })
    const [row] = rows()
    fireEvent.click(within(row).getByTitle('webhooks.test'))
    expect(handleWebhookTest).toHaveBeenCalledWith(HOOKS[0])
    expect(within(row).queryByTitle('common.delete')).toBeNull()
    fireEvent.click(within(row).getByTitle('webhooks.deliveries.title'))
    expect(screen.getByText('deliveries-of-hook-01')).toBeInTheDocument()
  })

  it('keeps the write actions from a reader', () => {
    hooks(HOOKS.slice(0, 1), can('read:settings'))
    const [row] = rows()
    expect(within(row).queryByTitle('webhooks.test')).toBeNull()
    expect(within(row).queryByTitle('common.edit')).toBeNull()
    expect(within(row).getByTitle('webhooks.deliveries.title')).toBeInTheDocument()
  })
})

const CONNS = Array.from({ length: 12 }, (_, i) => ({
  id: i + 1, name: `adcs-${pad(i + 1)}`, server: `dc${pad(i + 1)}.example.com`, enabled: true,
  auth_method: i === 3 ? 'kerberos' : 'basic', default_template: i === 5 ? 'WebServer' : 'User',
  crl_sync_enabled: i === 0, last_crl_sync_at: i === 0 ? '2026-11-20T10:00:00Z' : null, last_crl_sync_result: 'error: timeout',
  last_test_at: i === 0 ? '2026-11-20T10:00:00Z' : null, last_test_result: 'success',
}))
const msca = (list, perm, handlers = {}, extra = {}) => render(
  <MicrosoftCASection mscaConnections={list} mscaLoading={false} handleMscaCreate={vi.fn()} handleMscaEdit={vi.fn()} handleMscaToggle={vi.fn()}
    handleMscaTest={vi.fn()} handleMscaSyncCrl={vi.fn()} handleMscaPublishCrl={vi.fn()} handleMscaInventorySync={vi.fn()} handleMscaCaControl={vi.fn()}
    setMscaConfirmDelete={vi.fn()} hasPermission={perm} {...handlers} {...extra} />,
)

describe('Microsoft AC table', () => {
  it('pages past ten connections', () => {
    msca(CONNS, can('read:settings'))
    expect(document.querySelector('.record-list')).toBeNull()
    expect(rows()).toHaveLength(12)
    expect(document.querySelector('.table-footer')).not.toBeNull()
    fireEvent.change(document.querySelector('.table-footer select'), { target: { value: '10' } })
    expect(rows()).toHaveLength(10)
    fireEvent.click(document.querySelector('[data-page="next"]'))
    expect(names()).toEqual(['adcs-11', 'adcs-12'])
  })

  it('finds a connection by server or template', () => {
    msca(CONNS, can('read:settings'))
    search('msca-search', 'dc09')
    expect(names()).toEqual(['adcs-09'])
    search('msca-search', 'webserver')
    expect(names()).toEqual(['adcs-06'])
  })

  it('sorts by the authentication and says it in words', () => {
    msca(CONNS, can('read:settings'))
    fireEvent.click(document.querySelector('button[data-sort="auth"]'))
    expect(names()[0]).toBe('adcs-01')
    expect(rows()[0]).toHaveTextContent('msca.authBasic')
    fireEvent.click(document.querySelector('button[data-sort="auth"]'))
    expect(names()[0]).toBe('adcs-04')
    expect(rows()[0].textContent).not.toMatch(/\bkerberos\b/)
  })

  it('says the outcome of a test and of a sync in words', () => {
    msca(CONNS.slice(0, 1), can('read:settings'))
    const [row] = rows()
    expect(row.textContent).not.toMatch(/[✓✗]/)
    expect(row).toHaveTextContent('common.success')
    expect(row).toHaveTextContent('common.failed')
  })

  it('shows the common empty block when there is no connection', () => {
    msca([], can('read:settings', 'admin:system'))
    expect(document.getElementById('empty-msca')).toHaveTextContent('msca.noConnections')
    expect(screen.getAllByRole('button', { name: /msca.addConnection/ })).toHaveLength(1)
  })

  it('keeps the row actions, edit kept from a reader, test held while one runs', () => {
    const handleMscaTest = vi.fn()
    msca(CONNS.slice(0, 1), can('read:settings', 'write:settings', 'write:certificates'), { handleMscaTest })
    const [row] = rows()
    fireEvent.click(within(row).getByTitle('msca.testConnection'))
    expect(handleMscaTest).toHaveBeenCalledWith(CONNS[0])
    expect(within(row).getByTitle('msca.syncCrlNow')).toBeInTheDocument()
    document.body.innerHTML = ''
    msca(CONNS.slice(0, 1), can('read:settings', 'write:settings', 'write:certificates'), {}, { mscaTesting: true })
    expect(within(rows()[0]).getByTitle('msca.testConnection')).toBeDisabled()
    expect(within(rows()[0]).getByTitle('msca.syncCrlNow')).toBeDisabled()
    document.body.innerHTML = ''
    msca(CONNS.slice(0, 1), can('read:settings'))
    expect(within(rows()[0]).queryByTitle('common.edit')).toBeNull()
    expect(within(rows()[0]).queryByTitle('msca.testConnection')).toBeNull()
  })
})

const ANOMALIES = Array.from({ length: 14 }, (_, i) => ({
  timestamp: `2026-11-20T${pad(i)}:00:00Z`,
  details: { type: i === 4 ? 'brute_force' : 'unusual_hour', severity: i === 2 ? 'high' : 'warning', ip: `10.0.0.${i + 1}`, message: `event ${i + 1}` },
}))

describe('security anomalies table', () => {
  it('lists the newest first and pages past ten', () => {
    render(<AnomalyList anomalies={ANOMALIES} loading={false} />)
    expect(rows()).toHaveLength(14)
    expect(rows()[0]).toHaveTextContent('10.0.0.14')
    fireEvent.change(document.querySelector('.table-footer select'), { target: { value: '10' } })
    fireEvent.click(document.querySelector('[data-page="next"]'))
    expect(rows()).toHaveLength(4)
  })

  it('finds an anomaly by type, address or message and sorts by severity', () => {
    render(<AnomalyList anomalies={ANOMALIES} loading={false} />)
    search('anomaly-search', 'brute')
    expect(rows()).toHaveLength(1)
    expect(rows()[0]).toHaveTextContent('10.0.0.5')
    search('anomaly-search', '')
    fireEvent.click(document.querySelector('button[data-sort="severity"]'))
    expect(rows()[0]).toHaveTextContent('settings.anomalyHigh')
  })

  it('says there is none in the common empty block', () => {
    render(<AnomalyList anomalies={[]} loading={false} />)
    expect(document.getElementById('empty-anomalies')).toHaveTextContent('settings.noAnomalies')
  })
})
