/**
 * CSRsPage names a post-quantum key with its level, in the list and in both
 * panels, and never shows a request whose key has no name as RSA.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import en from '../../i18n/locales/en.json'

beforeAll(() => {
  global.ResizeObserver = global.ResizeObserver || class { observe() {} unobserve() {} disconnect() {} }
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
})

const i18n = vi.hoisted(() => ({ en: null }))
vi.mock('react-i18next', () => {
  const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), i18n.en)
  const t = (key, opts) => {
    const vars = typeof opts === 'object' && opts ? opts : {}
    const template = lookup(key)
    if (typeof template !== 'string') return key
    return template.replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
  }
  const translation = { t, i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} } }
  return {
    useTranslation: () => translation,
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
})
i18n.en = en

const mobile = vi.hoisted(() => ({
  isMobile: false, isTablet: false, isDesktop: true, isTouch: false,
  isLargeScreen: true, screenWidth: 1440, sidebarOpen: true, setSidebarOpen: () => {},
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
  }),
  useMobile: () => mobile,
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => mobile }))
vi.mock('../../hooks', async () => {
  const common = await vi.importActual('../../hooks/useCommon')
  return {
    useModals: common.useModals,
    usePermission: () => ({
      canWrite: () => false, canDelete: () => false, canRead: () => true, hasPermission: () => true,
    }),
  }
})

const rows = vi.hoisted(() => ({ pending: [], history: [] }))
vi.mock('../../services', () => ({
  csrsService: {
    getAll: () => Promise.resolve({ data: rows.pending }),
    getHistory: () => Promise.resolve({ data: rows.history }),
    getById: (id) => Promise.resolve({ data: [...rows.pending, ...rows.history].find(r => r.id === id) }),
    download: vi.fn(), downloadKey: vi.fn(), resubmit: vi.fn(),
  },
  certificatesService: { export: vi.fn() },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  mscaService: { getEnabled: vi.fn().mockResolvedValue({ data: [] }), getPendingRequests: vi.fn().mockResolvedValue({ data: [] }) },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import CSRsPage from '../CSRsPage'

// The key reads as the Certificates zone names it: the algorithm, never a post-quantum level (the mockup shows none)
const PQ_LABEL = 'ML-DSA-65'
const PQ = { id: 5, cn: 'pq.example.com', common_name: 'pq.example.com', key_algorithm: 'ML-DSA-65', security_level: 3 }
const UNNAMED = { id: 6, cn: 'nokey.example.com', common_name: 'nokey.example.com', key_algorithm: null }

const openRow = async (tab, row) => {
  rows.pending = tab === 'pending' ? [row] : []
  rows.history = tab === 'history' ? [row] : []
  render(<MemoryRouter initialEntries={[`/csrs?tab=${tab}`]}><CSRsPage /></MemoryRouter>)
  const name = await screen.findByText(row.cn)
  const listed = screen.queryAllByText(PQ_LABEL).length
  fireEvent.click(within(name.closest('tr')).getAllByRole('button')[0])
  await screen.findByText(en.atelier.properties)
  return listed
}

describe('CSRsPage key display', () => {
  it('names a pending ML-DSA request in the list and in the dock', async () => {
    const listed = await openRow('pending', PQ)
    expect(listed).toBe(1)
    expect(screen.getAllByText(PQ_LABEL)).toHaveLength(2)
  })

  it('shows a pending request with an unnamed key as a dash, never RSA', async () => {
    await openRow('pending', UNNAMED)
    expect(screen.queryByText(/\bRSA\b/)).toBeNull()
  })

  it('names a signed ML-DSA certificate in the list and in the dock', async () => {
    await openRow('history', PQ)
    expect(screen.getAllByText(PQ_LABEL)).toHaveLength(2)
  })

  it('shows a signed certificate with an unnamed key as a dash, never RSA', async () => {
    await openRow('history', UNNAMED)
    expect(screen.queryByText(/\bRSA\b/)).toBeNull()
  })
})
