import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ Trans: ({ i18nKey }) => i18nKey, useTranslation: () => ({ t: (k, o) => (o?.defaultValue ?? k) }) }))
const api = vi.hoisted(() => ({
  getQueue: vi.fn(), getHealth: vi.fn(), getCompliance: vi.fn(), getIssuance: vi.fn(),
  getStats: vi.fn(), getAll: vi.fn(), getNext: vi.fn(), getActivity: vi.fn(), can: vi.fn(),
  getDashStats: vi.fn(), getTrend: vi.fn(), getScores: vi.fn(),
}))
vi.mock('../../../services', () => ({
  overviewService: { getQueue: api.getQueue, getHealth: api.getHealth, getCompliance: api.getCompliance, getIssuance: api.getIssuance },
  certificatesService: { getStats: api.getStats, getComplianceStats: api.getScores },
  casService: { getAll: api.getAll },
  dashboardService: { getNextExpirations: api.getNext, getActivityLog: api.getActivity,
    getStats: api.getDashStats, getCertificateTrend: api.getTrend },
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: api.can }) }))
const nav = vi.hoisted(() => vi.fn())
vi.mock('react-router-dom', async (orig) => ({ ...(await orig()), useNavigate: () => nav }))

import { OverviewContext } from '../shared'
import { QueueCard, ComplianceCard, HealthCard, HierarchyCard, HorizonCard, ActivityCard, TrendCard } from '..'
import { blockedWhileSuspended } from '../../../components/shell/__tests__/writeGuardProbe'

const show = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)
const item = (i) => ({ kind: 'manual_renewal_due', tier: 'warning', id: i, label: `cert-${i}`, due_at: null, href_hint: `/certificates/${i}` })
const error = (status) => Object.assign(new Error('x'), { status })

beforeEach(() => {
  vi.clearAllMocks()
  api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
  api.getScores.mockResolvedValue({ data: { average_score: 78, distribution: { 'A+': 1, A: 2, B: 3, C: 0, D: 0, F: 0 }, total: 6 } })
  api.getNext.mockResolvedValue({ data: [] })
  api.can.mockReturnValue(true)
})

const card = (id) => document.getElementById(`card-${id}`)
const counter = (id) => document.querySelector(`#card-${id}-title .counter`)

describe('card states', () => {
  const cases = [
    ['queue', QueueCard, api.getQueue, { items: [], counts: {}, total: 0 }, 'overview.queue.emptyTitle'],
    ['compliance', ComplianceCard, api.getCompliance, { total: 0, counters: {}, by_key_algorithm: [] }, 'overview.state.empty'],
    ['health', HealthCard, api.getHealth, { protocols: {} }, 'overview.state.empty'],
    ['hierarchy', HierarchyCard, api.getAll, [], 'overview.hierarchy.emptyTitle'],
    ['horizon', HorizonCard, api.getDashStats, { total_certificates: 0 }, 'overview.state.empty'],
    ['activity', ActivityCard, api.getActivity, { activity: [] }, 'overview.state.empty'],
    ['trend', TrendCard, api.getTrend, { trend: [{ date: '2026-11-19', issued: 0, revoked: 0, expired: 0 }] }, 'overview.trend.quiet'],
  ]
  it.each(cases)('%s: skeleton, empty, error with its cause and retry, missing permission', async (id, Card, fetcher, empty, emptyText) => {
    fetcher.mockReturnValueOnce(new Promise(() => {}))
    const { unmount } = show(<Card />)
    // The mockup's card skeleton: its title, five bars, the card's own class
    expect(screen.getByRole('status').textContent).toBe('overview.state.loading')
    expect(card(id).className).toBe(`panel dash-card card-${id} sk-card`)
    expect(card(id).querySelectorAll('.sk-body .sk')).toHaveLength(5)
    unmount()

    fetcher.mockResolvedValueOnce({ data: empty, meta: { total: 0 } })
    show(<Card />)
    expect(await screen.findByText(emptyText)).toBeTruthy()

    fetcher.mockRejectedValueOnce(Object.assign(error(500), { request: 'GET /api/v2/x' })).mockResolvedValueOnce({ data: empty, meta: { total: 0 } })
    show(<Card />)
    const alert = await screen.findByRole('alert')
    expect(alert.className).toBe('load-error')
    expect(alert.textContent).toContain('overview.state.errorTitle')
    fireEvent.click(screen.getByText('table.retry'))
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(4))

    fetcher.mockRejectedValueOnce(error(403))
    const { container } = show(<Card />)
    await waitFor(() => expect(container.textContent).toContain('overview.state.forbidden'))
  })
})

describe('a card that could not read', () => {
  it('links to the journal for who may read it, as the mockup loadError', async () => {
    api.getCompliance.mockRejectedValue(error(503))
    const a = show(<ComplianceCard />)
    expect((await screen.findByText('work.viewLog')).closest('a').getAttribute('href')).toBe('/audit')
    a.unmount()
    api.can.mockImplementation((p) => p !== 'read:audit')
    show(<ComplianceCard />)
    await screen.findByRole('alert')
    expect(screen.queryByText('work.viewLog')).toBeNull()
  })
})

describe('queue card', () => {
  it('lists 6 rows, gives the totals per type as chips, and each row opens its href_hint', async () => {
    api.getQueue.mockResolvedValue({ data: {
      items: [1, 2, 3, 4, 5, 6, 7, 8].map(item), counts: { manual_renewal_due: 8, crl_due: 2 }, total: 10,
      filter_hints: { manual_renewal_due: { renewal: 'manual_renewal_due' } },
    } })
    show(<QueueCard />)
    await screen.findByText('cert-1')
    // Beyond six, the rows wait folded, as the mockup's hidden rows
    expect(screen.getByText('cert-7').closest('li').hidden).toBe(true)
    expect(screen.getByText('cert-6').closest('li').hidden).toBe(false)
    fireEvent.click(screen.getByText('cert-6').closest('li').querySelector('.queue-action .btn'))
    expect(nav).toHaveBeenCalledWith('/certificates/6')
    expect(counter('queue').textContent).toBe('10')
    expect(screen.getByText('overview.queue.group.crl').closest('button').textContent).toContain('2')
    expect(screen.getByText('overview.queue.group.renew').closest('button').textContent).toContain('8')
    const toList = document.querySelector('#card-queue [data-dashboard-link="renewal"]')
    expect(toList.className).toBe('text-link')
    fireEvent.click(toList)
    expect(nav).toHaveBeenCalledWith('/certificates?renewal=manual_renewal_due')
    fireEvent.click(screen.getByText('overview.queue.unfold'))
    expect(screen.getByText('cert-8').closest('li').hidden).toBe(false)
  })
})

describe('queue card preference', () => {
  it('follows the saved fold state when the preference arrives after mounting', async () => {
    api.getQueue.mockResolvedValue({ data: {
      items: [1, 2, 3, 4, 5, 6, 7, 8].map(item), counts: { manual_renewal_due: 8 }, total: 8,
    } })
    const view = show(<QueueCard defaultOpen={false} />)
    await screen.findByText('cert-1')
    expect(screen.getByText('cert-8').closest('li').hidden).toBe(true)
    view.rerender(<MemoryRouter><QueueCard defaultOpen /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('cert-8').closest('li').hidden).toBe(false))
    expect(screen.getByText('overview.queue.less').closest('button').getAttribute('aria-expanded')).toBe('true')
  })
})

describe('compliance card', () => {
  const entry = (count, hint) => ({ count, filter_available: Boolean(hint), filter_hint: hint })
  const meter = (name) => document.querySelector(`.meter[data-check="${name}"]`)
  const counters = {
    rsa_below_3072: entry(189, { live: 'true', key_algo_prefix: 'RSA', key_bits_below: '3072' }),
    server_lifetime_over_398_days: entry(11, { live: 'true', server: 'true', lifetime_over_days: '398' }),
    weak_signature_hash: entry(0, { live: 'true', sig_hash: ['sha1', 'md5'] }),
    incomplete_chain: entry(0, null),
    no_private_key: entry(8, null),
  }
  const summary = { total: 211, counters, by_key_algorithm: [{ key_algo: 'RSA 2048', count: 189 }] }

  it('a rule opens the list of its gaps the hint names, and not one without a filter', async () => {
    api.getCompliance.mockResolvedValue({ data: summary })
    show(<ComplianceCard />)
    await waitFor(() => expect(meter('rsa_below_3072')).not.toBeNull())
    expect(meter('rsa_below_3072').tagName).toBe('A')
    expect(meter('rsa_below_3072').getAttribute('href')).toBe('/certificates?live=true&key_algo_prefix=RSA&key_bits_below=3072')
    expect(meter('weak_signature_hash').getAttribute('href')).toBe('/certificates?live=true&sig_hash=sha1&sig_hash=md5')
    expect(meter('no_private_key').tagName).toBe('DIV')
    // The rule in words, its gap counted under it
    expect(meter('rsa_below_3072').querySelector('.name').textContent).toBe('overview.compliance.rule.rsa_below_3072overview.compliance.gap.rsa_below_3072')
  })

  it('each gauge gives the conforming share and count, its tone and its state said by an icon', async () => {
    api.getCompliance.mockResolvedValue({ data: summary })
    show(<ComplianceCard />)
    await waitFor(() => expect(meter('rsa_below_3072')).not.toBeNull())
    const width = (name) => meter(name).querySelector('.track i').style.width
    expect([width('rsa_below_3072'), width('server_lifetime_over_398_days'), width('weak_signature_hash')]).toEqual(['10%', '94%', '100%'])
    expect(meter('rsa_below_3072').querySelector('.val').textContent).toContain('22/211')
    expect(meter('server_lifetime_over_398_days').querySelector('.val').textContent).toContain('200/211')
    expect(['rsa_below_3072', 'server_lifetime_over_398_days', 'weak_signature_hash', 'no_private_key'].map((n) => meter(n).dataset.tone))
      .toEqual(['bad', 'warn', 'good', 'info'])
    for (const name of Object.keys(counters)) expect(meter(name).querySelector('.rule-state[role="img"]').getAttribute('aria-label')).toMatch(/^overview\.compliance\.state\./)
  })

  it('lists the rules in the mockup order', async () => {
    api.getCompliance.mockResolvedValue({ data: summary })
    show(<ComplianceCard />)
    await waitFor(() => expect(meter('rsa_below_3072')).not.toBeNull())
    expect([...document.querySelectorAll('#card-compliance .meter')].map((m) => m.dataset.check)).toEqual([
      'rsa_below_3072', 'server_lifetime_over_398_days', 'weak_signature_hash', 'incomplete_chain', 'no_private_key'])
  })

  it('shows a dash, not zero, and no tone for a figure the response lacks', async () => {
    api.getCompliance.mockResolvedValue({ data: { total: 3, counters: { rsa_below_3072: {} }, by_key_algorithm: [] } })
    show(<ComplianceCard />)
    await waitFor(() => expect(meter('rsa_below_3072')).not.toBeNull())
    expect(meter('rsa_below_3072').querySelector('.val').textContent).toBe('–')
    expect(meter('rsa_below_3072').dataset.tone).toBeUndefined()
    expect(meter('rsa_below_3072').querySelector('.track i')).toBeNull()
  })

  it('rings the average score with its grade and grades, its base written when it is not the rules\' population', async () => {
    api.getCompliance.mockResolvedValue({ data: summary })
    api.getScores.mockResolvedValue({ data: { average_score: 78, distribution: { 'A+': 12, A: 80, B: 121, C: 47, D: 6, F: 0 }, total: 266 } })
    show(<ComplianceCard />)
    await waitFor(() => expect(document.querySelector('.ring-arc')).not.toBeNull())
    expect(document.querySelector('.ring-arc').dataset.value).toBe('78')
    expect(document.querySelector('.ring-center .value').textContent).toBe('78')
    // F has no certificate: no segment, but its line in the legend
    expect([...document.querySelectorAll('.grade-bar i')].map((i) => i.dataset.grade)).toEqual(['A+', 'A', 'B', 'C', 'D'])
    expect([...document.querySelectorAll('.comp .legend li')].map((li) => li.textContent)).toEqual(['A+12', 'A80', 'B121', 'C47', 'D6', 'F0'])
    expect(document.querySelector('.score-base').textContent).toBe('overview.compliance.scoreBase')
  })

  it('takes the score of the compliance route once it carries one, without a base line', async () => {
    api.getCompliance.mockResolvedValue({ data: { ...summary, score: 64, distribution: { 'A+': 0, A: 1, B: 0, C: 0, D: 0, F: 1 } } })
    show(<ComplianceCard />)
    await waitFor(() => expect(document.querySelector('.ring-arc')).not.toBeNull())
    expect(document.querySelector('.ring-arc').dataset.value).toBe('64')
    expect([...document.querySelectorAll('.grade-bar i')].map((i) => i.dataset.grade)).toEqual(['A', 'F'])
    expect(document.querySelector('.score-base')).toBeNull()
  })

  it('keeps its gauges, flagged partial, without the right to read the scores', async () => {
    api.getCompliance.mockResolvedValue({ data: summary })
    api.getScores.mockRejectedValue(error(403))
    show(<ComplianceCard />)
    await waitFor(() => expect(meter('rsa_below_3072')).not.toBeNull())
    expect(document.querySelector('.ring-wrap')).toBeNull()
    expect(screen.getByRole('note').textContent).toBe('overview.state.partialForbidden')
  })

  it('opens its figures as a table from the card menu, and goes back to the chart', async () => {
    api.getCompliance.mockResolvedValue({ data: summary })
    render(<MemoryRouter><OverviewContext.Provider value={{ hide: vi.fn() }}><ComplianceCard /></OverviewContext.Provider></MemoryRouter>)
    await waitFor(() => expect(meter('rsa_below_3072')).not.toBeNull())
    fireEvent.click(document.getElementById('card-menu-btn-compliance'))
    fireEvent.click(document.querySelector('[data-card-table="compliance"]'))
    const tables = [...document.querySelectorAll('#card-compliance table.viz-table')]
    expect(tables.map((tb) => tb.querySelector('caption').textContent)).toEqual([
      'overview.compliance.tableRules', 'overview.compliance.tableGrades', 'overview.compliance.byAlgorithm'])
    expect([...tables[0].querySelector('tbody tr').children].map((c) => c.textContent))
      .toEqual(['overview.compliance.rule.rsa_below_3072', '22', '189', '10'])
    expect(document.querySelector('#card-compliance [data-action="export-csv"]')).not.toBeNull()
    expect(document.querySelector('#card-compliance .meter')).toBeNull()
    fireEvent.click(document.getElementById('card-menu-btn-compliance'))
    expect(document.querySelector('[data-card-table="compliance"]').textContent).toBe('atelier.chartView')
    fireEvent.click(document.querySelector('[data-card-table="compliance"]'))
    expect(document.querySelector('#card-compliance table.viz-table')).toBeNull()
    expect(meter('rsa_below_3072')).not.toBeNull()
  })
})

describe('missing figures read as a dash on every card', () => {
  it('hierarchy, horizon', async () => {
    api.getIssuance.mockResolvedValue({ data: {} })
    api.getDashStats.mockResolvedValue({ data: { total_certificates: 4 } })
    api.getAll.mockResolvedValue({ data: [{ id: 1, refid: 'r', descr: 'Root' }, { id: 2, refid: 's', descr: 'Sub', parent_id: 1 }], meta: {} })
    const a = show(<HierarchyCard />)
    expect((await screen.findByText('Sub')).closest('a').textContent).toContain('overview.hierarchy.issued')
    expect(screen.getByText('Sub').closest('a').querySelector('.hier-meta').lastChild.textContent).toBe('overview.hierarchy.issued')
    a.unmount()
    show(<HorizonCard />)
    expect((await screen.findByText('overview.horizon.state.expiring')).parentElement.textContent).toContain('–')
  })
})

describe('hierarchy card', () => {
  it('marks an offline root and a cross-signed one, and no other', async () => {
    api.getAll.mockResolvedValue({ data: [
      { id: 1, refid: 'r', descr: 'Root', offline: true, offline_label: 'Offline', cross_certificate_count: 0 },
      { id: 4, refid: 'q', descr: 'Root G2', offline: false, offline_label: null, cross_certificate_count: 2 },
      { id: 3, refid: 't', descr: 'Plain', parent_id: 1, offline: false, cross_certificate_count: 0 },
    ], meta: { total: 3 } })
    show(<HierarchyCard />)
    const line = async (name) => (await screen.findByText(name)).closest('a').textContent
    expect(await line('Root')).toContain('overview.hierarchy.offline')
    expect(await line('Root')).not.toContain('overview.hierarchy.crossSigned')
    expect(await line('Root G2')).toContain('overview.hierarchy.crossSigned')
    expect(await line('Root G2')).not.toContain('overview.hierarchy.offline')
    expect(await line('Plain')).not.toMatch(/offline|crossSigned/)
  })
})

describe('a card with two requests keeps what one of them gave', () => {
  it('hierarchy: issuance down, the tree stays with dashes and a partial note', async () => {
    api.getAll.mockResolvedValue({ data: [{ id: 1, refid: 'r', descr: 'Root' }], meta: { total: 1 } })
    api.getIssuance.mockRejectedValue(error(500))
    show(<HierarchyCard />)
    expect(await screen.findByText('Root')).toBeTruthy()
    expect(screen.getByRole('note').textContent).toBe('overview.state.partial')
    expect(screen.getByRole('note').className).toBe('notice warn')
  })

  it('hierarchy: authorities forbidden, the issuances per CA stay', async () => {
    api.getAll.mockRejectedValue(error(403))
    api.getIssuance.mockResolvedValue({ data: { by_ca: [{ caref: 'r', ca_id: 7, ca_name: 'Root', issued: 4, total: 5 }] } })
    show(<HierarchyCard />)
    const row = (await screen.findByText('Root')).closest('li')
    expect(row.textContent).toContain('overview.hierarchy.issued')
    // Nothing leads to the page the role cannot open
    expect(document.querySelector('a[href^="/cas"]')).toBeNull()
    expect(screen.getByRole('note').textContent).toBe('overview.state.partialForbidden')
  })

  it('hierarchy: both down is an error', async () => {
    api.getAll.mockRejectedValue(error(500))
    api.getIssuance.mockRejectedValue(error(500))
    show(<HierarchyCard />)
    expect(await screen.findByText('table.retry')).toBeTruthy()
  })

  it('horizon: next expirations down, the counters stay', async () => {
    api.getDashStats.mockResolvedValue({ data: { total_certificates: 4, expiring_soon: 2, expired: 1 } })
    api.getNext.mockRejectedValue(error(500))
    show(<HorizonCard />)
    expect((await screen.findByText('overview.horizon.state.expiring')).parentElement.textContent).toContain('2')
    expect(screen.getByRole('note').textContent).toBe('overview.state.partial')
  })

  it('horizon: counters forbidden, the soonest list stays with dashed counters', async () => {
    api.getDashStats.mockRejectedValue(error(403))
    api.getNext.mockResolvedValue({ data: [{ id: 9, common_name: 'soon.example', valid_to: null }] })
    show(<HorizonCard />)
    expect(await screen.findByText('soon.example')).toBeTruthy()
    expect(screen.getByText('overview.horizon.state.expiring').parentElement.textContent).toContain('–')
    expect(screen.getByRole('note').textContent).toBe('overview.state.partialForbidden')
  })

  it('no note when both answer', async () => {
    api.getDashStats.mockResolvedValue({ data: { total_certificates: 4, expiring_soon: 2, expired: 1 } })
    show(<HorizonCard />)
    await screen.findByText('overview.horizon.state.expiring')
    expect(screen.queryByRole('note')).toBeNull()
  })
})

describe('queue card write guard', () => {
  it('suspends Publish now with the other writes', async () => {
    api.can.mockReturnValue(true)
    api.getQueue.mockResolvedValue({ data: { items: [{ kind: 'crl_due', tier: 'warning', id: 14, label: 'Services CA', due_at: null, href_hint: '/crl-ocsp?ca=14' }], counts: { crl_due: 1 }, total: 1 } })
    const notify = { showSuccess: vi.fn(), showError: vi.fn() }
    show(<OverviewContext.Provider value={{ notify }}><QueueCard /></OverviewContext.Provider>)
    const publish = await screen.findByRole('button', { name: /overview.queue.publish/ })
    expect(blockedWhileSuspended(publish)).toBe(true)
  })
})
