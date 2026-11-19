/**
 * Work queue card: chips that filter, rows on two levels with their delay, the operations the
 * API offers as buttons (a link otherwise), and what only needs watching folded apart.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => {
    if (o && 'defaultValue' in o) return o.defaultValue
    return o && Object.keys(o).length > 0 ? `${k}:${Object.values(o).join(',')}` : k
  } }),
}))
const api = vi.hoisted(() => ({
  getQueue: vi.fn(), getById: vi.fn(), renew: vi.fn(), renewOrder: vi.fn(), regenerate: vi.fn(), can: vi.fn(),
}))
vi.mock('../../../services', () => ({
  overviewService: { getQueue: api.getQueue },
  certificatesService: { getById: api.getById, renew: api.renew },
  acmeService: { renewOrder: api.renewOrder },
  crlService: { regenerate: api.regenerate },
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: api.can }) }))

import { QueueCard } from '..'
import { OverviewContext } from '../shared'

const NOW = Date.parse('2026-11-19T12:00:00Z')
const DAY = 86400000
const at = (days) => new Date(NOW + days * DAY).toISOString()
const row = (kind, id, over = {}) => ({ kind, tier: 'warning', id, label: `${kind}-${id}`, due_at: at(12), href_hint: `/x/${kind}/${id}`, ...over })
const answer = (items, counts) => ({ data: {
  items, total: Object.values(counts).reduce((a, b) => a + b, 0), counts,
  filter_hints: { manual_renewal_due: { renewal: 'manual_renewal_due' } },
} })
const notify = { showSuccess: vi.fn(), showError: vi.fn(), showPrompt: vi.fn(), showConfirm: vi.fn() }
const show = (page = { notify }) => render(
  <MemoryRouter><OverviewContext.Provider value={page}><QueueCard /></OverviewContext.Provider></MemoryRouter>)
const rows = () => screen.getAllByTestId('queue-row')
const names = () => rows().map((r) => r.querySelector('.ov-queue-subject').textContent)

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
  api.can.mockReturnValue(true)
})
afterEach(() => { vi.useRealTimers() })

describe('chips', () => {
  const mixed = () => answer([
    row('manual_renewal_due', 1), row('acme_order_failed', 2, { tier: 'critical' }), row('approval_pending', 3),
    row('crl_due', 4), row('manual_renewal_due', 5),
  ], { manual_renewal_due: 2, acme_order_failed: 1, approval_pending: 1, crl_due: 1, ca_expiring: 0 })

  it('show one chip per type that has items, with its total, and All first', async () => {
    api.getQueue.mockResolvedValue(mixed())
    show()
    await screen.findByText('manual_renewal_due-1')
    const chips = within(screen.getByRole('group', { name: 'overview.queue.filterLabel' })).getAllByRole('button')
    expect(chips.map((c) => c.textContent)).toEqual([
      'overview.queue.group.all5', 'overview.queue.group.renew2', 'overview.queue.group.acme1',
      'overview.queue.group.request1', 'overview.queue.group.crl1',
    ])
    expect(chips[0].getAttribute('aria-pressed')).toBe('true')
  })

  it('a chip keeps the rows of its type, and All brings the others back', async () => {
    api.getQueue.mockResolvedValue(mixed())
    show()
    await screen.findByText('manual_renewal_due-1')
    fireEvent.click(screen.getByText('overview.queue.group.renew'))
    expect(names()).toEqual(['manual_renewal_due-1', 'manual_renewal_due-5'])
    expect(screen.getByText('overview.queue.group.renew').closest('button').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('card-queue').textContent).toContain('overview.queue.subFiltered:2,5,overview.queue.group.renew')
    fireEvent.click(screen.getByText('overview.queue.group.all'))
    expect(rows()).toHaveLength(5)
  })

  it('another card asks for one type through the page event', async () => {
    api.getQueue.mockResolvedValue(mixed())
    show()
    await screen.findByText('manual_renewal_due-1')
    act(() => { window.dispatchEvent(new CustomEvent('ucm:overview-queue', { detail: { group: 'acme' } })) })
    expect(names()).toEqual(['acme_order_failed-2'])
  })
})

describe('rows', () => {
  it('give the name as a link, the type as a pill and the cause, on two levels', async () => {
    api.getQueue.mockResolvedValue(answer([row('manual_renewal_due', 1)], { manual_renewal_due: 1 }))
    show()
    const link = await screen.findByText('manual_renewal_due-1')
    expect(link.closest('a').getAttribute('href')).toBe('/x/manual_renewal_due/1')
    const line = rows()[0]
    expect(line.querySelector('.ov-pill').textContent).toBe('manual_renewal_due')
    expect(line.getAttribute('data-kind')).toBe('manual_renewal_due')
  })

  it('a critical row says so in words, not only in colour', async () => {
    api.getQueue.mockResolvedValue(answer([
      row('crl_missing', 1, { tier: 'critical' }), row('approval_pending', 2),
    ], { crl_missing: 1, approval_pending: 1 }))
    show()
    await screen.findByText('crl_missing-1')
    expect(rows()[0].getAttribute('data-tier')).toBe('critical')
    expect(rows()[0].textContent).toContain('overview.queue.critical')
    expect(rows()[0].querySelector('.ov-pill.is-bad')).not.toBeNull()
    expect(rows()[1].textContent).not.toContain('overview.queue.critical')
    expect(rows()[1].querySelector('.ov-pill.is-bad')).toBeNull()
  })

  it('a deadline reads as a delay, late in words, with the exact date in the tooltip', async () => {
    api.getQueue.mockResolvedValue(answer([
      row('manual_renewal_due', 1, { due_at: at(-190) }), row('manual_renewal_due', 2, { due_at: at(3) }),
      row('manual_renewal_due', 3, { due_at: at(40) }), row('manual_renewal_due', 4, { due_at: null }),
    ], { manual_renewal_due: 4 }))
    show()
    await screen.findByText('manual_renewal_due-1')
    const due = rows().map((r) => r.querySelector('.ov-queue-due'))
    expect(due[0].querySelector('strong').textContent).toBe('overview.queue.overdue:6 months')
    expect(due[0].getAttribute('data-late')).toBe('true')
    expect(due[0].className).toContain('is-bad')
    expect(due[0].getAttribute('title')).toMatch(/2026/)
    expect(due[0].querySelector('small').textContent).toBe(due[0].getAttribute('title'))
    expect(due[1].querySelector('strong').textContent).toBe('in 3 days')
    expect(due[1].className).toContain('is-warn')
    expect(due[2].querySelector('strong').textContent).toBe('in 40 days')
    expect(due[2].className).not.toMatch(/is-(warn|bad)/)
    expect(due[3].textContent).toBe('–')
  })

  it('a date that tells when it happened is never called late', async () => {
    api.getQueue.mockResolvedValue(answer([row('acme_order_failed', 1, { due_at: at(-2) })], { acme_order_failed: 1 }))
    show()
    await screen.findByText('acme_order_failed-1')
    const due = rows()[0].querySelector('.ov-queue-due')
    expect(due.querySelector('strong').textContent).toBe('2 days ago')
    expect(due.getAttribute('data-late')).toBe('false')
  })
})

describe('a missing CRL', () => {
  it('has no deadline: the date the server gives is the time of the request', async () => {
    api.getQueue.mockResolvedValue(answer([
      row('crl_missing', 1, { tier: 'critical', due_at: at(0) }), row('crl_due', 2, { due_at: at(-3) }),
    ], { crl_missing: 1, crl_due: 1 }))
    show()
    await screen.findByText('crl_missing-1')
    const due = rows().map((r) => r.querySelector('.ov-queue-due'))
    expect(due[0].textContent).toBe('–')
    expect(due[0].getAttribute('data-late')).toBeNull()
    expect(due[1].querySelector('strong').textContent).toBe('overview.queue.overdue:3 days')
  })
})

describe('row operations', () => {
  const three = () => answer([
    row('manual_renewal_due', 7), row('acme_client_renewal_failed', 8), row('crl_due', 9), row('approval_pending', 10),
    row('ca_expiring', 11, { tier: 'critical' }), row('acme_order_failed', 12),
  ], { manual_renewal_due: 1, acme_client_renewal_failed: 1, crl_due: 1, approval_pending: 1, ca_expiring: 1, acme_order_failed: 1 })
  const control = (i) => rows()[i].querySelector('.ov-queue-action').firstElementChild

  it('offers a button where the API has the operation and a link to the object elsewhere', async () => {
    api.getQueue.mockResolvedValue(three())
    show()
    await screen.findByText('manual_renewal_due-7')
    expect([0, 1, 2, 3, 4, 5].map((i) => `${control(i).tagName} ${control(i).textContent}`)).toEqual([
      'BUTTON common.renew', 'BUTTON overview.queue.retry', 'BUTTON overview.queue.publish',
      'A overview.queue.review', 'A overview.queue.viewCa', 'A overview.queue.open',
    ])
    expect(control(3).getAttribute('href')).toBe('/x/approval_pending/10')
    expect(control(0).getAttribute('aria-label')).toBe('common.renew: manual_renewal_due-7')
  })

  it('without the write permission every row is a link', async () => {
    api.can.mockReturnValue(false)
    api.getQueue.mockResolvedValue(three())
    show()
    await screen.findByText('manual_renewal_due-7')
    expect([0, 1, 2].map((i) => control(i).tagName)).toEqual(['A', 'A', 'A'])
    expect(api.can).toHaveBeenCalledWith('write:certificates')
    expect(api.can).toHaveBeenCalledWith('write:acme')
    expect(api.can).toHaveBeenCalledWith('write:crl')
  })

  it('a card rendered outside the page has no operation', async () => {
    api.getQueue.mockResolvedValue(three())
    show(null)
    await screen.findByText('manual_renewal_due-7')
    expect(control(0).tagName).toBe('A')
  })

  it('Renew asks for the duration, renews, says so and reloads the queue', async () => {
    api.getQueue.mockResolvedValue(three())
    api.getById.mockResolvedValue({ data: { id: 7, valid_from: at(-100), valid_to: at(12) } })
    notify.showPrompt.mockResolvedValue('90')
    api.renew.mockResolvedValue({ data: {} })
    const changed = vi.fn()
    window.addEventListener('ucm:data-changed', changed)
    show()
    await screen.findByText('manual_renewal_due-7')
    fireEvent.click(control(0))
    await waitFor(() => expect(api.renew).toHaveBeenCalledWith(7, { validity_days: 90 }))
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith('certificates.renewed'))
    window.removeEventListener('ucm:data-changed', changed)
    expect(changed.mock.calls[0][0].detail).toEqual({ type: 'certificate' })
    expect(api.getQueue).toHaveBeenCalledTimes(2)
  })

  it('a cancelled prompt renews nothing', async () => {
    api.getQueue.mockResolvedValue(three())
    api.getById.mockResolvedValue({ data: { id: 7 } })
    notify.showPrompt.mockResolvedValue(null)
    show()
    await screen.findByText('manual_renewal_due-7')
    fireEvent.click(control(0))
    await waitFor(() => expect(notify.showPrompt).toHaveBeenCalled())
    await waitFor(() => expect(control(0).disabled).toBe(false))
    expect(api.renew).not.toHaveBeenCalled()
    expect(notify.showSuccess).not.toHaveBeenCalled()
  })

  it('Retry and Publish call their route with the row id; a refusal is shown', async () => {
    api.getQueue.mockResolvedValue(three())
    api.renewOrder.mockResolvedValue({})
    api.regenerate.mockRejectedValue(new Error('CA cannot sign'))
    show()
    await screen.findByText('manual_renewal_due-7')
    fireEvent.click(control(1))
    await waitFor(() => expect(api.renewOrder).toHaveBeenCalledWith(8))
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith('overview.queue.retried'))
    fireEvent.click(control(2))
    await waitFor(() => expect(api.regenerate).toHaveBeenCalledWith(9))
    await waitFor(() => expect(notify.showError).toHaveBeenCalledWith('CA cannot sign'))
  })

  it('a second click while an operation runs starts nothing', async () => {
    api.getQueue.mockResolvedValue(three())
    api.renewOrder.mockReturnValue(new Promise(() => {}))
    show()
    await screen.findByText('manual_renewal_due-7')
    fireEvent.click(control(1))
    await waitFor(() => expect(control(1).disabled).toBe(true))
    expect(control(2).disabled).toBe(true)
    fireEvent.click(control(1))
    expect(api.renewOrder).toHaveBeenCalledTimes(1)
  })
})

describe('to watch', () => {
  const withWatch = () => answer([
    row('ca_expiring', 1, { tier: 'critical' }), row('manual_renewal_due', 2),
    row('client_renewal_overdue', 3), row('ca_expiring', 4), row('truststore_expiring', 5),
  ], { ca_expiring: 2, manual_renewal_due: 1, client_renewal_overdue: 1, truststore_expiring: 1 })

  it('folds apart what needs no action today, never a critical row', async () => {
    api.getQueue.mockResolvedValue(withWatch())
    show()
    await screen.findByText('manual_renewal_due-2')
    expect(names()).toEqual(['ca_expiring-1', 'manual_renewal_due-2'])
    expect(screen.getByText('overview.queue.watch:3')).toBeTruthy()
    const toggle = screen.getByRole('button', { name: 'overview.queue.watchShow' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(toggle)
    expect(names()).toEqual(['ca_expiring-1', 'manual_renewal_due-2', 'client_renewal_overdue-3', 'ca_expiring-4', 'truststore_expiring-5'])
    fireEvent.click(screen.getByRole('button', { name: 'overview.queue.watchHide' }))
    expect(rows()).toHaveLength(2)
  })

  it('a chip that keeps only rows to watch shows them unfolded', async () => {
    api.getQueue.mockResolvedValue(answer([row('manual_renewal_due', 2), row('truststore_expiring', 5), row('ca_expiring', 4)],
      { manual_renewal_due: 1, truststore_expiring: 1, ca_expiring: 1 }))
    show()
    await screen.findByText('manual_renewal_due-2')
    fireEvent.click(screen.getByText('overview.queue.group.ca'))
    expect(names()).toEqual(['truststore_expiring-5', 'ca_expiring-4'])
    expect(screen.queryByRole('button', { name: /overview\.queue\.watch(Show|Hide)/ })).toBeNull()
  })

  it('says so when nothing but rows to watch is left', async () => {
    api.getQueue.mockResolvedValue(answer([row('ca_expiring', 4)], { ca_expiring: 1 }))
    show()
    expect(await screen.findByText('overview.queue.none')).toBeTruthy()
    expect(screen.queryAllByTestId('queue-row')).toHaveLength(0)
  })
})

describe('fold', () => {
  it('tells how many rows it hides and reports the choice to the page', async () => {
    const items = Array.from({ length: 9 }, (_, i) => row('manual_renewal_due', i + 1))
    api.getQueue.mockResolvedValue(answer(items, { manual_renewal_due: 9 }))
    const onToggle = vi.fn()
    render(<MemoryRouter><QueueCard onToggle={onToggle} /></MemoryRouter>)
    await screen.findByText('manual_renewal_due-1')
    const more = screen.getByText('overview.queue.unfold:3')
    expect(more.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(more)
    expect(onToggle).toHaveBeenCalledWith(true)
    expect(rows()).toHaveLength(9)
  })

  it('has no fold for six rows or fewer', async () => {
    api.getQueue.mockResolvedValue(answer(Array.from({ length: 6 }, (_, i) => row('manual_renewal_due', i + 1)), { manual_renewal_due: 6 }))
    show()
    await screen.findByText('manual_renewal_due-1')
    expect(screen.queryByText(/overview\.queue\.(unfold|less)/)).toBeNull()
  })
})
