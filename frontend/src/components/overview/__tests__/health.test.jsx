/**
 * Automation health card: the TSA signer, statuses in the user's language, and a scheduler
 * that cannot look healthy while tasks fail or its published state is old.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
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
      const found = opts.count === undefined ? frLookup(key) : frLookup(`${key}_${opts.count === 1 ? 'one' : 'other'}`)
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

vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: () => true }) }))

import { HealthCard } from '..'

const tsa = (over) => ({ basis: 'signer', periods: null, state: 'dedicated', reason: null, days_left: 200,
  alert: false, last_operation_at: null, last_status: null, ...over })
const sched = (over) => ({ basis: 'scheduler', periods: null, tasks: 20, by_status: { ok: 20 }, stale: false,
  last_operation_at: '2026-11-01T10:00:00Z', last_status: 'ok', ...over })
const show = async (protocols) => {
  api.getHealth.mockResolvedValue({ data: { protocols } })
  render(<MemoryRouter><HealthCard /></MemoryRouter>)
  return screen.findByTestId('card-health')
}
const row = (card, name) => within(card).getByTestId(`health-${name}`)

beforeEach(() => { vi.clearAllMocks(); lang.fr = false })

describe('TSA signer on the health card', () => {
  it.each([
    ['ca_certificate', {}, 'overview.health.tsaState.ca_certificate', false],
    ['dedicated', {}, 'overview.health.tsaState.dedicated', false],
    ['expiring', { days_left: 12 }, 'overview.health.tsaState.expiring:12', true],
    ['no_signer', {}, 'overview.health.tsaState.no_signer', true],
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

  it('links to the TSA page', async () => {
    const card = await show({ tsa: tsa({}) })
    expect(within(row(card, 'tsa')).getByRole('link').getAttribute('href')).toBe('/tsa-config')
  })

  it('is not listed while the server leaves it out', async () => {
    const card = await show({ scheduler: sched({}) })
    expect(within(card).queryByTestId('health-tsa')).toBeNull()
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
