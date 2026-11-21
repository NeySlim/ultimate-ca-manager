/**
 * Automation health card: the TSA signer, statuses in the user's language, and a scheduler
 * that cannot look healthy while tasks fail or its published state is old.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, within, configure, waitFor, fireEvent } from '@testing-library/react'
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
    expect(line.querySelector('.badge.warn')).not.toBeNull()
    expect(line.querySelector('.badge.bad')).toBeNull()
  })

  it('an expiring signer stays critical', async () => {
    const card = await show({ tsa: tsa({ state: 'expiring', days_left: 3, alert: true, severity: 'critical' }) })
    const line = row(card, 'tsa')
    expect(line.getAttribute('data-severity')).toBe('critical')
    expect(line.querySelector('.badge.bad')).not.toBeNull()
  })

  it('no signer reads as not configured, neutral, with the link to configure it', async () => {
    lang.fr = true
    const card = await show({ tsa: tsa({ state: 'no_signer', alert: false, days_left: null }) })
    const line = row(card, 'tsa')
    expect(line.textContent).toContain('Non configuré')
    expect(line.getAttribute('data-alert')).toBe('false')
    expect(line.querySelector('.badge.bad')).toBeNull()
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
    expect(line.querySelector('.badge.bad')).toBeNull()
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
  const spark = (line) => line.querySelector('svg.spark')

  it('draws the mockup sparkline for every protocol with daily figures, titled by its figures', async () => {
    const card = await show({ acme: busy, scep: idle })
    expect(spark(row(card, 'acme')).getAttribute('role')).toBe('img')
    expect(spark(row(card, 'acme')).getAttribute('aria-labelledby')).toBe('spark-acme')
    expect(spark(row(card, 'scep'))).not.toBeNull()
    expect(row(card, 'scep').textContent).not.toContain('–')
  })

  it('a protocol without operation says it is idle under its name, with its period', async () => {
    const card = await show({ scep: idle })
    expect(row(card, 'scep').querySelector('.health-name small').textContent).toBe('overview.health.idle:7')
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
    expect(row(card, 'acme').textContent).toContain('overview.health.idle:7')
    expect(row(card, 'acme').querySelector('.health-stats, svg.spark')).toBeNull()
  })

  it('the curve reads as its figures, oldest day first', async () => {
    lang.fr = true
    const card = await show({ acme: busy })
    expect(spark(row(card, 'acme')).querySelector('title').textContent)
      .toBe('ACME, par jour, du plus ancien au plus récent. Succès : 1, 0, 2, 0, 0, 0, 4. Échecs : 0, 0, 3, 0, 0, 0, 1.')
  })

  it('gives today and the whole period in figures, ACME failures leading to the queue', async () => {
    const showQueue = vi.fn()
    api.getHealth.mockResolvedValue({ data: { protocols: { acme: busy } } })
    render(<MemoryRouter><OverviewContext.Provider value={{ showQueue }}><HealthCard /></OverviewContext.Provider></MemoryRouter>)
    await waitFor(() => expect(document.querySelector('#card-health [data-protocol="acme"]')).not.toBeNull())
    const stats = [...document.querySelectorAll('[data-protocol="acme"] .health-stat')]
    expect(stats.map((s) => s.querySelector('.health-span').textContent)).toEqual(['overview.health.today', 'overview.days:7'])
    expect(stats.map((s) => s.querySelector('.health-values strong').textContent)).toEqual(['4', '7'])
    const fails = [...document.querySelectorAll('[data-protocol="acme"] button.fail-link')]
    expect(fails.map((b) => b.textContent)).toEqual(['overview.health.failures:1', 'overview.health.failures:4'])
    fireEvent.click(fails[0])
    expect(showQueue).toHaveBeenCalledWith('acme')
  })

  it('a failure of another protocol is said in red, not as a link; a zero stays muted', async () => {
    const card = await show({ est: { ...busy, periods: periods([[3, 1], [2, 0]]) } })
    expect(row(card, 'est').querySelectorAll('.fail-link')).toHaveLength(0)
    expect([...row(card, 'est').querySelectorAll('.health-values > span:last-child')].map((s) => s.className)).toEqual(['muted', 'bad'])
  })

  it('a good state stays silent; a failure is a bad badge and an unknown state a neutral one, each with its icon', async () => {
    const card = await show({ acme: busy, scep: { ...busy, last_status: 'failed' }, est: { ...busy, last_status: 'quarantined' } })
    expect(row(card, 'acme').querySelector('.badge')).toBeNull()
    expect(row(card, 'scep').querySelector('.badge.bad svg')).not.toBeNull()
    expect(row(card, 'est').querySelector('.badge').className).toBe('badge')
    expect(row(card, 'est').querySelector('.badge svg')).not.toBeNull()
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
