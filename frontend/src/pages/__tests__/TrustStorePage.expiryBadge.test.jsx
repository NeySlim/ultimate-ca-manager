/**
 * TrustStorePage expiry states: the state pill of each phone record follows the shared
 * day count (lib/utils daysRemaining) and the trust store 90-day window, so an entry
 * 12 hours or 60 days from its end is not green.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import en from '../../i18n/locales/en.json'

const i18n = vi.hoisted(() => ({ en: null }))
vi.mock('react-i18next', () => {
  const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), i18n.en)
  const t = (key, opts) => {
    const vars = typeof opts === 'object' && opts ? opts : {}
    const template = lookup(key)
    if (typeof template !== 'string') return key
    return template.replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
  }
  return {
    useTranslation: () => ({ t, i18n: { language: 'en' } }),
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
})
i18n.en = en

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false),
  }),
  useMobile: () => ({ isMobile: true }),
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: true }) }))
vi.mock('../../hooks', async () => {
  const modals = await vi.importActual('../../hooks/useCommon')
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    useModals: modals.useModals,
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({
      canWrite: () => false, canDelete: () => false, hasPermission: () => true, canRead: () => true,
    }),
  }
})

const store = vi.hoisted(() => ({ rows: [] }))
vi.mock('../../services', () => ({
  truststoreService: {
    getAll: () => Promise.resolve({ data: store.rows }),
    getById: () => Promise.resolve({ data: store.rows[0] }),
    getStats: vi.fn().mockResolvedValue({ data: { total: 1, root_ca: 1, intermediate_ca: 0, expired: 0, valid: 1 } }),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import TrustStorePage from '../TrustStorePage'

const HOUR = 3600 * 1000
const at = (ms) => new Date(Date.now() + ms).toISOString()
// The tone of the state pill on the record that shows this name
const toneOf = (name) => screen.getByText(name).closest('article').querySelector('.row-status .badge').className.replace('badge', '').trim()

describe('TrustStorePage expiry states', () => {
  it('colours each entry from its remaining days', async () => {
    store.rows = [
      { id: 1, name: 'half-day', purpose: 'root_ca', not_after: at(12 * HOUR) },
      { id: 2, name: 'gone', purpose: 'root_ca', not_after: at(-HOUR) },
      { id: 3, name: 'later', purpose: 'root_ca', not_after: at(120 * 24 * HOUR) },
      { id: 4, name: 'two-months', purpose: 'root_ca', not_after: at(60 * 24 * HOUR) },
    ]
    render(<MemoryRouter><TrustStorePage /></MemoryRouter>)
    await screen.findByText('half-day')
    expect(toneOf('half-day')).toBe('warn')
    expect(toneOf('gone')).toBe('bad')
    expect(toneOf('later')).toBe('good')
    // The trust store's window is 90 days, the one its filter and the server use
    expect(toneOf('two-months')).toBe('warn')
    expect(screen.getByText('two-months').closest('article')).toHaveTextContent(en.trustStore.module.states.expiring)
  })
})
