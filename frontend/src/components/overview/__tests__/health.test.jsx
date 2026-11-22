/**
 * Automation health card: the TSA signer, statuses in the user's language, and a scheduler
 * that cannot look healthy while tasks fail or its published state is old.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, within, configure, waitFor, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fr from '../../../i18n/locales/fr.json'

const lang = vi.hoisted(() => ({ fr: false }))
const api = vi.hoisted(() => ({ getHealth: vi.fn() }))
const frLookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), fr)
vi.mock('react-i18next', () => ({
  // As i18next: the count inside its <strong>, then the words
  Trans: ({ i18nKey, count, components }) => (components?.strong ? <><strong>{count}</strong> {i18nKey}</> : i18nKey),
  useTranslation: () => ({
    t: (key, arg) => {
      const opts = typeof arg === 'object' && arg ? arg : {}
      const fallback = typeof arg === 'string' ? arg : opts.defaultValue
      if (!lang.fr) return opts.count !== undefined ? `${key}:${opts.count}` : (fallback ?? key)
      // As i18next: a key without plural forms is read as is
      const found = (opts.count === undefined ? undefined : frLookup(`${key}_${opts.count === 1 ? 'one' : 'other'}`)) ?? frLookup(key)
      const text = typeof found === 'string' ? found : (fallback ?? key)
      return text.replace(/\{\{(\w+)\}\}/g, (_, name) => opts[name])
    },
  }),
}))
vi.mock('../../../services', () => ({ overviewService: { getHealth: api.getHealth } }))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))

const perms = vi.hoisted(() => ({ admin: true, granted: [] }))
vi.mock('../../../hooks/usePermission', () => ({
  usePermission: () => ({ isAdmin: () => perms.admin, hasPermission: (p) => perms.admin || perms.granted.includes(p) }),
}))

import { HealthCard } from '..'
import { OverviewContext } from '../shared'

// A loaded machine slows the first render past the default second
configure({ asyncUtilTimeout: 5000 })

const tsa = (over) => ({ basis: 'signer', periods: null, state: 'dedicated', reason: null, days_left: 200,
  alert: false, last_operation_at: null, last_status: null, ...over })
const sched = (over) => ({ basis: 'scheduler', periods: null, tasks: 20, by_status: { ok: 20 }, stale: false,
  last_operation_at: '2026-11-01T10:00:00Z', last_status: 'ok', ...over })
const show = async (protocols) => {
  // The answer comes after the first render, as on a loaded machine: the card is read once loaded
  api.getHealth.mockImplementation(() => new Promise((done) => setTimeout(() => done({ data: { protocols } }), 20)))
  render(<MemoryRouter><HealthCard /></MemoryRouter>)
  await waitFor(() => expect(document.querySelector('#card-health:not(.sk-card)')).not.toBeNull())
  return document.getElementById('card-health')
}
const row = (card, name) => card.querySelector(`[data-protocol="${name}"]`)

beforeEach(() => { vi.clearAllMocks(); lang.fr = false; perms.admin = true; perms.granted = [] })

describe('TSA signer on the health card', () => {
  it.each([
    ['ca_certificate', {}, 'overview.health.tsaState.ca_certificate', false],
    ['dedicated', {}, 'overview.health.tsaState.dedicated', false],
    ['expiring', { days_left: 12 }, 'overview.health.tsaState.expiring:12', true],
    ['no_signer', {}, 'overview.health.tsaState.no_signer', false],
    ['unavailable', {}, 'overview.health.tsaState.unavailable', true],
    ['unusable', { reason: 'expired' }, 'overview.health.tsaReason.expired', true],
    ['unusable', { reason: 'revoked' }, 'overview.health.tsaReason.revoked', true],
    ['unusable', { reason: 'key_unavailable' }, 'overview.health.tsaReason.key_unavailable', true],
    ['unusable', { reason: 'invalid' }, 'overview.health.tsaReason.invalid', true],
  ])('%s %j reads %s (alert: %s)', async (state, over, text, alert) => {
    const card = await show({ tsa: tsa({ state, alert, ...over }) })
    const line = row(card, 'tsa')
    expect(line.textContent).toContain(text)
    expect(line.getAttribute('data-alert')).toBe(alert ? 'true' : 'false')
  })

  it('the CA certificate signing is a warning, not a critical line', async () => {
    const card = await show({ tsa: tsa({ state: 'ca_certificate', alert: true, severity: 'warning' }) })
    const line = row(card, 'tsa')
    expect(line.textContent).toContain('overview.health.tsaState.ca_certificate')
    expect(line.getAttribute('data-severity')).toBe('warning')
    expect(line.dataset.tone).toBe('warn')
  })

  it('an expiring signer stays critical', async () => {
    const card = await show({ tsa: tsa({ state: 'expiring', days_left: 3, alert: true, severity: 'critical' }) })
    const line = row(card, 'tsa')
    expect(line.getAttribute('data-severity')).toBe('critical')
    expect(line.dataset.tone).toBe('bad')
  })

  it('no signer reads as not configured, neutral, with the link to configure it', async () => {
    lang.fr = true
    const card = await show({ tsa: tsa({ state: 'no_signer', alert: false, days_left: null }) })
    const line = row(card, 'tsa')
    expect(line.textContent).toContain('Non configuré')
    expect(line.getAttribute('data-alert')).toBe('false')
    expect(line.dataset.tone).toBe('neutral')
    expect(within(line).getByRole('link').getAttribute('href')).toBe('/tsa-config')
  })

  it('links to the TSA page', async () => {
    const card = await show({ tsa: tsa({}) })
    expect(within(row(card, 'tsa')).getByRole('link').getAttribute('href')).toBe('/tsa-config')
  })

  it('is not listed while the server leaves it out', async () => {
    const card = await show({ scheduler: sched({}) })
    expect(row(card, 'tsa')).toBeNull()
  })
})

const witness = (state, over) => ({ basis: 'setting', periods: null, state, count: null, alert: false,
  last_operation_at: null, last_status: null, ...over })

describe('mail, webhook and auto-renewal witnesses', () => {
  it.each([
    ['smtp', 'not_configured', {}, false, 'overview.health.witness.smtp.not_configured'],
    ['smtp', 'disabled', { alert: true }, true, 'overview.health.witness.smtp.disabled'],
    ['smtp', 'incomplete', { alert: true }, true, 'overview.health.witness.smtp.incomplete'],
    ['smtp', 'ready', {}, false, 'overview.health.witness.smtp.ready'],
    ['webhooks', 'not_configured', { count: 0 }, false, 'overview.health.witness.webhooks.not_configured'],
    ['webhooks', 'none_active', { count: 2, alert: true }, true, 'overview.health.witness.webhooks.none_active:2'],
    ['webhooks', 'active', { count: 3 }, false, 'overview.health.witness.webhooks.active:3'],
    ['auto_renewal', 'enabled', {}, false, 'overview.health.witness.auto_renewal.enabled'],
    ['auto_renewal', 'disabled', {}, false, 'overview.health.witness.auto_renewal.disabled'],
    ['smtp', 'unavailable', { alert: true }, true, 'overview.health.witness.unavailable'],
    ['webhooks', 'unavailable', { alert: true }, true, 'overview.health.witness.unavailable'],
    ['auto_renewal', 'unavailable', { alert: true }, true, 'overview.health.witness.unavailable'],
  ])('%s %s reads %s', async (name, state, over, alert, text) => {
    const card = await show({ [name]: witness(state, over) })
    const line = row(card, name)
    expect(line.textContent).toContain(text)
    expect(line.getAttribute('data-alert')).toBe(alert ? 'true' : 'false')
    expect(line.textContent).not.toContain('–')
  })

  it('a setting that is not configured is information in the user language, not an alert', async () => {
    lang.fr = true
    const card = await show({ smtp: witness('not_configured') })
    const line = row(card, 'smtp')
    expect(line.textContent).toContain('Non configuré')
    expect(line.dataset.tone).toBe('neutral')
  })

  it('shows only the witnesses the server sent (the right to read the setting)', async () => {
    const card = await show({ scheduler: sched({}), webhooks: witness('active', { count: 1 }) })
    expect(row(card, 'smtp')).toBeNull()
    expect(row(card, 'auto_renewal')).toBeNull()
    expect(row(card, 'webhooks')).not.toBeNull()
  })

  it('each row links to its settings tab', async () => {
    const card = await show({ smtp: witness('ready'), webhooks: witness('active', { count: 1 }), auto_renewal: witness('enabled') })
    expect(within(row(card, 'smtp')).getByRole('link').getAttribute('href')).toBe('/settings?tab=email')
    expect(within(row(card, 'webhooks')).getByRole('link').getAttribute('href')).toBe('/settings?tab=webhooks')
    expect(within(row(card, 'auto_renewal')).getByRole('link').getAttribute('href')).toBe('/settings?tab=autoRenewal')
  })
})

describe('row links follow the navigation guards', () => {
  it('an operator without the rights sees the rows without their links', async () => {
    perms.admin = false
    perms.granted = ['read:certificates']
    const card = await show({ tsa: tsa({}), scheduler: sched({}) })
    for (const name of ['tsa', 'scheduler']) {
      expect(row(card, name).textContent).toContain(`overview.health.${name}`)
      expect(within(row(card, name)).queryByRole('link'), name).toBeNull()
    }
  })

  it('read:settings opens the TSA page but not the admin-only scheduler settings', async () => {
    perms.admin = false
    perms.granted = ['read:settings']
    const card = await show({ tsa: tsa({}), scheduler: sched({}) })
    expect(within(row(card, 'tsa')).getByRole('link').getAttribute('href')).toBe('/tsa-config')
    expect(within(row(card, 'scheduler')).queryByRole('link')).toBeNull()
  })

  it('an administrator gets both links', async () => {
    const card = await show({ tsa: tsa({}), scheduler: sched({}) })
    expect(within(row(card, 'scheduler')).getByRole('link').getAttribute('href')).toBe('/settings?tab=scheduler')
  })
})

describe('states in the user language', () => {
  it('reads a failure in French and an unknown state as sent; a good state stays silent, as in the mockup', async () => {
    lang.fr = true
    const card = await show({
      acme: { periods: [], last_operation_at: '2026-11-01T10:00:00Z', last_status: 'failed' },
      scep: { periods: [], last_operation_at: null, last_status: 'quarantined' },
      est: { periods: [], last_operation_at: null, last_status: 'ok' },
    })
    expect(row(card, 'acme').textContent).toContain('Échec')
    expect(row(card, 'est').querySelector('.badge')).toBeNull()
    expect(row(card, 'scep').textContent).toContain('quarantined')
    expect(card.textContent).not.toMatch(/\bfailed\b/)
  })
})

describe('scheduler card', () => {
  it('says tasks failed although the latest run was fine', async () => {
    const card = await show({ scheduler: sched({ by_status: { ok: 18, failed: 2 }, last_status: 'ok' }) })
    const line = row(card, 'scheduler')
    expect(line.textContent).toContain('overview.health.tasksFailed:2')
    expect(line.getAttribute('data-alert')).toBe('true')
  })

  it('says tasks ended with a warning', async () => {
    const card = await show({ scheduler: sched({ by_status: { ok: 19, warning: 1 } }) })
    expect(row(card, 'scheduler').textContent).toContain('overview.health.tasksWarning:1')
  })

  it('says the published state is old', async () => {
    const card = await show({ scheduler: sched({ stale: true }) })
    const line = row(card, 'scheduler')
    expect(line.textContent).toContain('overview.health.stale')
    expect(line.getAttribute('data-alert')).toBe('true')
  })

  it('stays quiet when every task is fine', async () => {
    const card = await show({ scheduler: sched({}) })
    const line = row(card, 'scheduler')
    expect(line.getAttribute('data-alert')).toBe('false')
    expect(line.textContent).not.toContain('tasksFailed')
  })
})

describe('protocol rows', () => {
  const periods = (rows) => rows.map(([ok, failed], i) => ({ date: `2026-11-${13 + i}`, ok, failed }))
  const busy = { periods: periods([[1, 0], [0, 0], [2, 3], [0, 0], [0, 0], [0, 0], [4, 1]]), last_operation_at: '2026-11-19T10:00:00Z', last_status: 'ok' }
  const idle = { periods: periods(Array(7).fill([0, 0])), last_operation_at: null, last_status: null }
  const mirror = (line) => line.querySelector('.mirror')
  const tip = () => document.querySelector('[data-testid="chart-tip"]')
  const tipRows = () => [...tip().querySelectorAll('.row')].map((r) => [r.querySelector('span').textContent, r.querySelector('b').textContent])

  it('asks the health of the last 30 days', async () => {
    await show({ acme: busy })
    expect(api.getHealth).toHaveBeenCalledWith(30)
  })

  it('draws mirror bars for every protocol with daily figures, named by its period and totals', async () => {
    lang.fr = true
    const card = await show({ acme: busy, scep: idle })
    expect(mirror(row(card, 'acme')).getAttribute('role')).toBe('group')
    expect(mirror(row(card, 'acme')).getAttribute('aria-label'))
      .toBe('ACME sur 7 jours : 7 succès, 4 échecs. Les flèches le lisent jour par jour.')
    expect(mirror(row(card, 'acme')).querySelectorAll('.day')).toHaveLength(7)
    expect(mirror(row(card, 'scep'))).not.toBeNull()
    expect(row(card, 'scep').textContent).not.toContain('–'.repeat(2))
  })

  it('successes rise above the base line, failures drop under it, an idle day is a dash on it', async () => {
    const card = await show({ acme: busy })
    const base = Number(mirror(row(card, 'acme')).querySelector('line.base').getAttribute('y1'))
    const day = (i) => mirror(row(card, 'acme')).querySelector(`.day[data-day="${i}"]`)
    const ok = day(2).querySelector('rect.ok')
    const fail = day(2).querySelector('rect.fail')
    expect(Number(ok.getAttribute('y')) + Number(ok.getAttribute('height'))).toBeLessThanOrEqual(base)
    expect(Number(fail.getAttribute('y'))).toBeGreaterThanOrEqual(base)
    // The busiest day of successes is the tallest bar, the busiest day of failures the deepest
    expect(Number(day(6).querySelector('rect.ok').getAttribute('height'))).toBeGreaterThan(Number(ok.getAttribute('height')))
    expect(Number(fail.getAttribute('height'))).toBeGreaterThan(Number(day(6).querySelector('rect.fail').getAttribute('height')))
    expect(day(1).querySelector('rect.ok, rect.fail')).toBeNull()
    expect(day(1).querySelector('rect.idle')).not.toBeNull()
    // The series colour of the protocol, the failures in red (a class of the bad tone)
    expect(ok.style.fill).toBe('var(--s1)')
  })

  it('reads the bars day by day from the keyboard, the tooltip following, Escape closing it', async () => {
    const card = await show({ acme: busy })
    const frame = mirror(row(card, 'acme'))
    act(() => frame.focus())
    await waitFor(() => expect(tip()).not.toBeNull())
    expect(tipRows()).toEqual([['overview.health.ok', '4'], ['overview.health.failed', '1']])
    expect(frame.querySelector('.day.on').dataset.day).toBe('6')
    fireEvent.keyDown(frame, { key: 'Home' })
    await waitFor(() => expect(frame.querySelector('.day.on').dataset.day).toBe('0'))
    fireEvent.keyDown(frame, { key: 'ArrowRight' })
    fireEvent.keyDown(frame, { key: 'ArrowRight' })
    await waitFor(() => expect(tipRows()).toEqual([['overview.health.ok', '2'], ['overview.health.failed', '3']]))
    expect(frame.getAttribute('aria-describedby')).toBe(tip().id)
    fireEvent.keyDown(frame, { key: 'Escape' })
    await waitFor(() => expect(tip()).toBeNull())
  })

  it('shows the tooltip of the day under the pointer', async () => {
    const card = await show({ acme: busy })
    fireEvent.pointerEnter(mirror(row(card, 'acme')).querySelector('.day[data-day="2"]'))
    await waitFor(() => expect(tipRows()).toEqual([['overview.health.ok', '2'], ['overview.health.failed', '3']]))
    fireEvent.pointerLeave(mirror(row(card, 'acme')))
    await waitFor(() => expect(tip()).toBeNull())
  })

  it('a protocol without operation says it is idle under its name, with its period', async () => {
    const card = await show({ scep: idle })
    expect(row(card, 'scep').querySelector('.health-name small').textContent).toBe('overview.health.idle:7')
    expect(row(card, 'scep').querySelector('.health-rate b').textContent).toBe('–')
  })

  it('the last operation reads under the name, with the exact date behind it', async () => {
    lang.fr = true
    const card = await show({ est: { ...idle, last_operation_at: '2020-01-01T10:00:00Z' } })
    const small = row(card, 'est').querySelector('.health-name small')
    expect(small.textContent).toMatch(/^Dernière opération .+/)
    expect(small.getAttribute('title')).toMatch(/2020/)
  })

  it('a protocol without daily figures keeps its name and idle line, without figures', async () => {
    const card = await show({ acme: { periods: null, last_operation_at: null, last_status: null } })
    expect(row(card, 'acme').textContent).toContain('overview.health.idle:30')
    expect(row(card, 'acme').querySelector('.health-rate, .mirror')).toBeNull()
  })

  it('gives the success rate and the period figures, ACME failures leading to the queue', async () => {
    const showQueue = vi.fn()
    api.getHealth.mockResolvedValue({ data: { protocols: { acme: busy } } })
    render(<MemoryRouter><OverviewContext.Provider value={{ showQueue }}><HealthCard /></OverviewContext.Provider></MemoryRouter>)
    await waitFor(() => expect(document.querySelector('#card-health [data-protocol="acme"]')).not.toBeNull())
    const rate = document.querySelector('[data-protocol="acme"] .health-rate')
    // 7 successes, 4 failures: 63.6 %, rounded down
    expect(rate.querySelector('b').dataset.rate).toBe('63.6')
    expect(rate.querySelector('b').className).toBe('warn')
    expect(rate.querySelector('.health-values strong').textContent).toBe('7')
    const fail = rate.querySelector('button.fail-link')
    expect(fail.textContent).toBe('overview.health.failures:4')
    fireEvent.click(fail)
    expect(showQueue).toHaveBeenCalledWith('acme')
  })

  it('a failure of another protocol is said in red, not as a link; a zero stays muted', async () => {
    const card = await show({ est: { ...busy, periods: periods([[3, 1], [2, 0]]) }, scep: { ...busy, periods: periods([[3, 0]]) } })
    expect(row(card, 'est').querySelectorAll('.fail-link')).toHaveLength(0)
    expect(row(card, 'est').querySelector('.health-values > span:last-child').className).toBe('bad')
    expect(row(card, 'scep').querySelector('.health-values > span:last-child').className).toBe('muted')
    expect(row(card, 'scep').querySelector('.health-rate b').dataset.rate).toBe('100')
  })

  it('a good state stays silent; a failure is a bad badge and an unknown state a neutral one, each with its icon', async () => {
    const card = await show({ acme: busy, scep: { ...busy, last_status: 'failed' }, est: { ...busy, last_status: 'quarantined' } })
    expect(row(card, 'acme').querySelector('.badge')).toBeNull()
    expect(row(card, 'scep').querySelector('.badge.bad svg')).not.toBeNull()
    expect(row(card, 'est').querySelector('.badge').className).toBe('badge')
    expect(row(card, 'est').querySelector('.badge svg')).not.toBeNull()
  })

  it('draws the services as pills after the protocols, each with its state in words and its tone', async () => {
    const card = await show({ acme: busy, scheduler: sched({}), smtp: witness('ready'), webhooks: witness('none_active', { count: 2, alert: true }) })
    const pills = [...card.querySelectorAll('.services > li.svc')]
    expect(pills.map((p) => p.dataset.protocol)).toEqual(['scheduler', 'smtp', 'webhooks'])
    expect(pills.map((p) => p.dataset.tone)).toEqual(['good', 'good', 'bad'])
    expect(row(card, 'scheduler').querySelector('.svc-state').textContent).toMatch(/^overview\.health\.taskCount:20, /)
    expect(row(card, 'webhooks').querySelector('.svc-state').textContent).toBe('overview.health.witness.webhooks.none_active:2')
  })

  it('opens the days as a table from the card menu', async () => {
    api.getHealth.mockResolvedValue({ data: { protocols: { acme: busy, scep: idle } } })
    render(<MemoryRouter><OverviewContext.Provider value={{ hide: vi.fn() }}><HealthCard /></OverviewContext.Provider></MemoryRouter>)
    await waitFor(() => expect(document.querySelector('#card-health .mirror')).not.toBeNull())
    fireEvent.click(document.getElementById('card-menu-btn-health'))
    fireEvent.click(document.querySelector('[data-card-table="health"]'))
    const table = document.querySelector('#card-health table.viz-table')
    expect(table.querySelectorAll('thead th')).toHaveLength(5)
    expect([...table.querySelectorAll('tbody tr')].map((r) => r.textContent)).toHaveLength(7)
    expect([...table.querySelectorAll('tbody tr')[2].children].map((c) => c.textContent)).toEqual(['2026-11-15', '2', '3', '0', '0'])
  })
})

describe('summary under the rows', () => {
  it('counts the lines that report a problem', async () => {
    const card = await show({
      acme: { periods: [], last_operation_at: null, last_status: 'failed' },
      scheduler: sched({ stale: true }), smtp: witness('ready'),
    })
    expect(card.querySelector('.health-foot').textContent).toBe('overview.health.alerts:2')
    expect(card.querySelector('.health-foot.good')).toBeNull()
  })

  it('says so when nothing does', async () => {
    const card = await show({ scheduler: sched({}), smtp: witness('not_configured') })
    expect(card.querySelector('.health-foot.good').textContent).toBe('overview.health.allFine')
  })
})
