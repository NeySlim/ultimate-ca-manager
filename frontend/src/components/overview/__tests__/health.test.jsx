/**
 * Automation health card: the TSA signer, statuses in the user's language, and a scheduler
 * that cannot look healthy while tasks fail or its published state is old.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, configure, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fr from '../../../i18n/locales/fr.json'

const lang = vi.hoisted(() => ({ fr: false }))
const api = vi.hoisted(() => ({ getHealth: vi.fn() }))
const frLookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), fr)
vi.mock('react-i18next', () => ({
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
  const card = await screen.findByTestId('card-health')
  await waitFor(() => expect(within(card).queryByRole('status')).toBeNull())
  return card
}
const row = (card, name) => within(card).getByTestId(`health-${name}`)

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
    expect(line.querySelector('.text-status-warning')).not.toBeNull()
    expect(line.querySelector('.text-status-danger')).toBeNull()
  })

  it('an expiring signer stays critical', async () => {
    const card = await show({ tsa: tsa({ state: 'expiring', days_left: 3, alert: true, severity: 'critical' }) })
    const line = row(card, 'tsa')
    expect(line.getAttribute('data-severity')).toBe('critical')
    expect(line.querySelector('.text-status-danger')).not.toBeNull()
  })

  it('no signer reads as not configured, neutral, with the link to configure it', async () => {
    lang.fr = true
    const card = await show({ tsa: tsa({ state: 'no_signer', alert: false, days_left: null }) })
    const line = row(card, 'tsa')
    expect(line.textContent).toContain('Non configuré')
    expect(line.getAttribute('data-alert')).toBe('false')
    expect(line.querySelector('.text-status-danger')).toBeNull()
    expect(within(line).getByRole('link').getAttribute('href')).toBe('/tsa-config')
  })

  it('links to the TSA page', async () => {
    const card = await show({ tsa: tsa({}) })
    expect(within(row(card, 'tsa')).getByRole('link').getAttribute('href')).toBe('/tsa-config')
  })

  it('is not listed while the server leaves it out', async () => {
    const card = await show({ scheduler: sched({}) })
    expect(within(card).queryByTestId('health-tsa')).toBeNull()
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
    expect(line.querySelector('.text-status-danger')).toBeNull()
  })

  it('shows only the witnesses the server sent (the right to read the setting)', async () => {
    const card = await show({ scheduler: sched({}), webhooks: witness('active', { count: 1 }) })
    expect(within(card).queryByTestId('health-smtp')).toBeNull()
    expect(within(card).queryByTestId('health-auto_renewal')).toBeNull()
    expect(within(card).getByTestId('health-webhooks')).toBeTruthy()
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
  it('reads a known state in French and an unknown one as sent', async () => {
    lang.fr = true
    const card = await show({
      acme: { periods: [], last_operation_at: '2026-11-01T10:00:00Z', last_status: 'failed' },
      scep: { periods: [], last_operation_at: null, last_status: 'quarantined' },
      est: { periods: [], last_operation_at: null, last_status: 'ok' },
    })
    expect(row(card, 'acme').textContent).toContain('Échec')
    expect(row(card, 'est').textContent).toContain('OK')
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
