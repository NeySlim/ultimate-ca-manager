/** The overview's first-run assistant, the mockup's setupWizard(): three steps, folded by Plus tard into one line. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor as rtlWaitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

const m = vi.hoisted(() => ({
  admin: true, stats: { total: 0 }, cas: [], acme: { enabled: true, issuing_ca_id: '' }, scep: { enabled: false }, est: { enabled: false },
  prefs: {}, persistPreference: vi.fn(), listeners: new Set(), casReads: 0,
}))

vi.mock('react-i18next', () => ({
  Trans: ({ i18nKey }) => i18nKey,
  useTranslation: () => ({ t: (k, o) => (o && o.count != null ? `${k}|${o.count}` : o && o.step ? `${k}|${o.step}` : o && (o.what || o.protocol) ? [k, o.what, o.root, o.protocol].filter(Boolean).join('|') : k), i18n: { language: 'en' } }),
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

import { SetupWizard } from '../SetupWizard'
import { resetHealthForTests } from '../../shell/health'

const waitFor = (check) => rtlWaitFor(check, { timeout: 4000 })
const ROOT = { id: 1, is_root: true }
const wizard = () => document.getElementById('setup-wizard')

function setup(props = {}) {
  const user = userEvent.setup()
  const view = render(<MemoryRouter><SetupWizard admin={m.admin} {...props} /></MemoryRouter>)
  return { user, ...view }
}

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

describe('SetupWizard', () => {
  it('draws the mockup steps: the current one leads to its screen, the later ones wait', async () => {
    setup()
    await waitFor(() => expect(wizard()).not.toBeNull())
    const steps = [...wizard().querySelectorAll('ol.setup-steps > li.setup-step')]
    expect(steps.map((s) => s.className)).toEqual(['setup-step todo', 'setup-step blocked', 'setup-step blocked'])
    expect(steps.map((s) => s.id)).toEqual(['setup-step-root', 'setup-step-issuing', 'setup-step-protocol'])
    const go = document.getElementById('setup-go-root')
    expect(go.tagName).toBe('A')
    expect(go.getAttribute('href')).toBe('/cas?action=create')
    expect(go.className).toBe('btn primary')
    expect(document.getElementById('setup-go-issuing').disabled).toBe(true)
    expect(steps[1].querySelector('.setup-state').textContent).toBe('shell.setup.stateAfter|1')
    expect(wizard().querySelector('[role="progressbar"]').getAttribute('aria-valuenow')).toBe('0')
  })

  it('Plus tard folds it into one line that keeps the progress, and Reprendre brings it back', async () => {
    const { user } = setup()
    await waitFor(() => expect(wizard()).not.toBeNull())
    await user.click(document.getElementById('setup-later-btn'))
    expect(wizard()).toBeNull()
    const line = document.getElementById('setup-later')
    expect(line.textContent).toContain('shell.setup.laterLine')
    expect(line.textContent).toContain('shell.setup.count|0')
    await user.click(document.getElementById('setup-resume'))
    await waitFor(() => expect(wizard()).not.toBeNull())
  })

  it('a step done says so and the next one becomes the current step', async () => {
    m.prefs = { setup_card: 'started' }
    m.cas = [ROOT]
    setup()
    await waitFor(() => expect(wizard()).not.toBeNull())
    expect(document.getElementById('setup-step-root').className).toBe('setup-step done')
    expect(document.getElementById('setup-go-root')).toBeNull()
    expect(document.getElementById('setup-step-issuing').getAttribute('aria-current')).toBe('step')
    expect(document.getElementById('setup-go-issuing').className).toBe('btn primary')
  })

  it('is not shown to who is not an administrator', async () => {
    m.admin = false
    setup()
    await act(async () => {})
    expect(wizard()).toBeNull()
    expect(document.getElementById('setup-later')).toBeNull()
  })
})
