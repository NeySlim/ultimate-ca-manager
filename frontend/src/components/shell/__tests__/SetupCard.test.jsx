/** First run: shown to an administrator of an empty instance, steps leading to the real screens, closed for good. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within, waitFor as rtlWaitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

const m = vi.hoisted(() => ({
  admin: true, stats: { total: 0 }, cas: [], acme: { enabled: true, issuing_ca_id: '' }, scep: { enabled: false }, est: { enabled: false },
  prefs: {}, persistPreference: vi.fn(), listeners: new Set(), casReads: 0,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o && o.count != null ? `${k}|${o.count}` : o && o.step ? `${k}|${o.step}` : k), i18n: { language: 'en' } }),
}))
vi.mock('../../../services', () => ({
  dashboardService: { getStats: async () => ({ data: { total_certificates: m.stats.total, total_cas: m.cas.length } }) },
  casService: { getAll: async () => { m.casReads += 1; return { data: m.cas } } },
  acmeService: { getSettings: async () => ({ data: m.acme }) },
  scepService: { getConfig: async () => ({ data: m.scep }) },
  estService: { getConfig: async () => ({ data: m.est }) },
}))
vi.mock('../../../stores/userPreferencesStore', () => ({
  getPreferences: () => m.prefs,
  subscribePreferences: (cb) => { m.listeners.add(cb); return () => m.listeners.delete(cb) },
  persistPreference: (key, value) => {
    m.persistPreference(key, value)
    m.prefs = { ...m.prefs, [key]: value }
    m.listeners.forEach(cb => cb(m.prefs))
  },
}))

import { SetupCard, SETUP_PREF } from '../SetupCard'
import { resetHealthForTests } from '../health'

// The card shows after five reads in sequence: a loaded worker needs more than the default second
const waitFor = (check) => rtlWaitFor(check, { timeout: 4000 })
const ROOT = { id: 1, is_root: true }
const ISSUING = { id: 2, is_root: false, parent_id: 1 }

function setup() {
  const user = userEvent.setup()
  const view = render(<MemoryRouter><SetupCard admin={m.admin} /></MemoryRouter>)
  return { user, ...view }
}
const card = () => screen.queryByRole('region', { name: /shell\.setup\.(title|doneTitle)/ })

beforeEach(() => {
  resetHealthForTests()
  localStorage.clear()
  sessionStorage.clear()
  Object.assign(m, { casReads: 0, admin: true, stats: { total: 0 }, cas: [], acme: { enabled: true, issuing_ca_id: '' }, scep: { enabled: false }, est: { enabled: false }, prefs: {} })
  m.persistPreference.mockReset()
  m.listeners.clear()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', ha: false }) }))
})
afterEach(() => { vi.unstubAllGlobals() })

describe('SetupCard', () => {
  it('shows the three steps on an instance without CA nor certificate, each leading to its screen', async () => {
    setup()
    await waitFor(() => expect(card()).not.toBeNull())
    const steps = within(card()).getAllByRole('listitem')
    expect(steps).toHaveLength(3)
    expect(within(steps[0]).getByRole('link', { name: 'shell.setup.steps.root.action' })).toHaveAttribute('href', '/cas?action=create')
    expect(steps[0]).toHaveAttribute('aria-current', 'step')
    // Later steps wait for the first one
    expect(within(steps[1]).getByRole('button', { name: 'shell.setup.steps.issuing.action' })).toBeDisabled()
    expect(within(steps[2]).getByText('shell.setup.stateAfter|1')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
    expect(m.persistPreference).toHaveBeenCalledWith(SETUP_PREF, 'started')
  })

  it('is not shown to an instance that already has a CA, unless it was started on an empty one', async () => {
    m.cas = [ROOT]
    const { unmount } = setup()
    await act(async () => {})
    expect(card()).toBeNull()
    unmount()
    m.prefs = { [SETUP_PREF]: 'started' }
    setup()
    await waitFor(() => expect(card()).not.toBeNull())
    const steps = within(card()).getAllByRole('listitem')
    expect(steps[0]).toHaveClass('is-done')
    expect(within(steps[1]).getByRole('link', { name: 'shell.setup.steps.issuing.action' })).toHaveAttribute('href', '/cas?action=create')
  })

  it('is not shown once a certificate exists, nor to a non-administrator', async () => {
    m.stats = { total: 3 }
    const { unmount } = setup()
    await act(async () => {})
    expect(card()).toBeNull()
    // The counts are enough: no CA list is read for an instance in use
    expect(m.casReads).toBe(0)
    unmount()
    m.stats = { total: 0 }
    m.admin = false
    setup()
    await act(async () => {})
    expect(card()).toBeNull()
    expect(m.casReads).toBe(0)
  })

  it('reads the counts through the page when it shares its requests', async () => {
    const share = vi.fn((key, run) => run())
    render(<MemoryRouter><SetupCard admin share={share} /></MemoryRouter>)
    await waitFor(() => expect(card()).not.toBeNull())
    expect(share).toHaveBeenCalledWith('stats', expect.any(Function))
  })

  it('counts a protocol only when it is enabled on an issuing CA', async () => {
    m.prefs = { [SETUP_PREF]: 'started' }
    m.cas = [ROOT, ISSUING]
    const { unmount } = setup()
    await waitFor(() => expect(card()).not.toBeNull())
    expect(within(card()).getAllByRole('listitem')[2]).not.toHaveClass('is-done')
    expect(within(card()).getByRole('link', { name: 'shell.setup.steps.protocol.action' })).toHaveAttribute('href', '/acme?tab=config')
    unmount()
    m.scep = { enabled: true, ca_id: 2 }
    setup()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'shell.setup.doneTitle' })).toBeInTheDocument())
  })

  it('folds into one line with Later, and comes back with Resume', async () => {
    const { user } = setup()
    await waitFor(() => expect(card()).not.toBeNull())
    await user.click(screen.getByRole('button', { name: 'shell.setup.later' }))
    expect(card()).toBeNull()
    expect(screen.getByText(/shell\.setup\.laterLine/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'shell.setup.resume' }))
    expect(card()).not.toBeNull()
  })

  it('closes for good from its folded line, and is never shown again', async () => {
    const { user, unmount } = setup()
    await waitFor(() => expect(card()).not.toBeNull())
    await user.click(screen.getByRole('button', { name: 'shell.setup.later' }))
    await user.click(screen.getByRole('button', { name: 'shell.setup.hide' }))
    expect(m.persistPreference).toHaveBeenLastCalledWith(SETUP_PREF, 'closed')
    expect(screen.queryByText(/shell\.setup\.laterLine/)).toBeNull()
    unmount()
    // Even when the server dropped the key, this browser remembers it
    m.prefs = {}
    setup()
    await act(async () => {})
    expect(card()).toBeNull()
    expect(screen.queryByText(/shell\.setup\.laterLine/)).toBeNull()
  })

  it('finished, offers the first issuance and Hide, and is not shown on the next visit', async () => {
    m.prefs = { [SETUP_PREF]: 'started' }
    m.cas = [ROOT, ISSUING]
    m.acme = { enabled: true, issuing_ca_id: 2 }
    const { user, unmount } = setup()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'shell.setup.doneTitle' })).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'shell.setup.issueFirst' })).toHaveAttribute('href', '/certificates?action=create')
    expect(m.persistPreference).toHaveBeenCalledWith(SETUP_PREF, 'done')
    await user.click(screen.getByRole('button', { name: 'shell.setup.hide' }))
    expect(card()).toBeNull()
    unmount()
    setup()
    await act(async () => {})
    expect(card()).toBeNull()
  })

  it('disables its steps during a cluster maintenance', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', ha: true,
      cluster: { nodes: 2, stale: 0, leader_node_id: 'n1' }, maintenance: { reason: 'restore' } }) }))
    setup()
    await waitFor(() => expect(card()).not.toBeNull())
    await waitFor(() => expect(within(card()).getByRole('button', { name: 'shell.setup.steps.root.action' })).toBeDisabled())
    expect(within(card()).getByRole('button', { name: 'shell.setup.steps.root.action' })).toHaveAttribute('aria-describedby', 'shell-writes-note')
  })
})
