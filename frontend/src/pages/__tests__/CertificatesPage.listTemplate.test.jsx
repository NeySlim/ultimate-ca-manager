/**
 * CertificatesPage on the list template: page head, default columns, one state
 * per row, the columns of the Columns menu, the footer in words, and the cards
 * a phone keeps.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && typeof opts.count === 'number'
      ? `${key}:${[opts.start, opts.end, opts.count].filter((v) => v !== undefined).join('/')}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(null),
  },
}))
const state = vi.hoisted(() => ({ mobile: false, write: true, opened: [], activeKey: null }))
const svc = vi.hoisted(() => ({ getAll: vi.fn(), getStats: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({
    isMobile: state.mobile, isDesktop: !state.mobile, isTablet: false, screenWidth: state.mobile ? 390 : 1280,
    sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
  useInspector: () => ({
    openEntity: vi.fn(), closeEntity: vi.fn(), closeAll: vi.fn(), windows: [],
    opened: state.opened, activeKey: state.activeKey,
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: () => {},
  }),
}))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({
      canWrite: () => state.write, canDelete: () => state.write, hasPermission: () => state.write, canRead: () => true,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

vi.mock('../../services', () => ({
  certificatesService: { getAll: (...a) => svc.getAll(...a), getStats: (...a) => svc.getStats(...a) },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 1, refid: 'ca-1', descr: 'CA 1' }] }) },
  truststoreService: { addFromCA: vi.fn() },
}))

import CertificatesPage from '../CertificatesPage'

const NOW = new Date('2026-11-08T12:00:00Z')
const DAY = 86400000
const at = (days) => new Date(NOW.getTime() + days * DAY).toISOString()
const WEB = {
  id: 7, cn: 'web.example.com', common_name: 'web.example.com', descr: 'Front door', status: 'valid',
  caref: 'ca-1', issuer: 'CN=Issuing CA 1,O=Example', source: 'acme', has_private_key: true,
  key_algorithm: 'EC-P256', valid_to: at(200), compliance_grade: 'A', compliance_score: 93,
  created_at: at(-10),
}
const SOON = { ...WEB, id: 8, cn: 'soon.example.com', common_name: 'soon.example.com', descr: '', status: 'expiring', valid_to: at(2.5), has_private_key: false }
const LATE = { ...WEB, id: 9, cn: 'late.example.com', common_name: 'late.example.com', status: 'expired', valid_to: at(-4.5), caref: 'gone' }
const GONE = { ...WEB, id: 10, cn: 'gone.example.com', common_name: 'gone.example.com', status: 'revoked', revoked: true, valid_to: at(-4.5), related_certificate_id: 7, hybrid_role: 'pq' }

const mount = async (rows = [WEB, SOON, LATE, GONE], total = 276) => {
  svc.getAll.mockResolvedValue({ data: rows, meta: { total } })
  const view = render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
  await screen.findByText(rows[0].cn)
  return view
}
const row = (cn) => screen.getByRole('row', { name: new RegExp(cn.replace(/\./g, '\\.')) })
const headers = () => screen.getAllByRole('columnheader').map((th) => th.textContent).filter((text) => text && text !== 'common.actions')

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  window.localStorage.clear()
  Object.assign(state, { mobile: false, write: true, opened: [], activeKey: null })
  svc.getAll.mockReset()
  svc.getStats.mockReset()
  svc.getStats.mockResolvedValue({ data: { valid: 250, expiring: 20, expired: 4, revoked: 2, total: 1234 } })
})
afterEach(() => { vi.useRealTimers() })

describe('CertificatesPage: page head', () => {
  it('shows the title, the total of the inventory in words and the intent', async () => {
    const { container } = await mount()
    const head = container.querySelector('header.lv-head')
    expect(within(head).getByRole('heading', { level: 1, name: 'common.certificates' })).toBeInTheDocument()
    // The whole inventory, not the 276 rows of the filter on screen
    await waitFor(() => expect(head).toHaveTextContent('certificates.total:1234'))
    expect(head).toHaveTextContent('certificates.intent')
  })

  it('puts Import and Issue on the right, Issue last and marked as the main action', async () => {
    const { container } = await mount()
    const buttons = within(container.querySelector('header.lv-head')).getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(['common.import', 'certificates.issue'])
    expect(buttons[1]).toHaveClass('is-primary')
    expect(buttons[0]).not.toHaveClass('is-primary')
  })

  it('shows neither to a principal who cannot write certificates', async () => {
    state.write = false
    const { container } = await mount()
    expect(within(container.querySelector('header.lv-head')).queryAllByRole('button')).toEqual([])
  })

  it('carries no Help button and no stat tiles', async () => {
    await mount()
    expect(screen.queryByRole('button', { name: 'common.help' })).toBeNull()
    expect(screen.queryByText('common.total')).toBeNull()
  })
})

describe('CertificatesPage: columns', () => {
  it('shows the default columns in order', async () => {
    await mount()
    expect(headers()).toEqual([
      'common.commonName', 'common.description', 'common.state', 'common.issuer',
      'certificates.source', 'certificates.expiry', 'common.keyAlgorithm',
    ])
  })

  it('keeps the compliance grade, the hybrid link and the creation date in the Columns menu', async () => {
    await mount()
    fireEvent.click(screen.getByRole('button', { name: 'table.columns' }))
    for (const name of ['compliance.grade', 'certificates.hybrid.column', 'common.created']) {
      fireEvent.click(screen.getByRole('button', { name }))
    }
    expect(headers().slice(7)).toEqual(['compliance.grade', 'certificates.hybrid.column', 'common.created'])
    const cells = within(row('gone.example.com')).getAllByRole('cell')
    expect(cells[8]).toHaveTextContent(/^A$/)
    expect(within(cells[8]).getByTitle('93/100')).toBeInTheDocument()
    expect(within(cells[9]).getByTestId('hybrid-linked-badge')).toHaveAttribute('title', 'certificates.hybrid.rolePq')
    expect(within(row('web.example.com')).queryByTestId('hybrid-linked-badge')).toBeNull()
  })

  it('does not read the column choice an earlier version stored as "all shown"', async () => {
    window.localStorage.setItem('ucm-certs-columns', '[]')
    await mount()
    expect(headers()).toHaveLength(7)
  })

  it('searches by what the placeholder names and exports from the toolbar', async () => {
    await mount()
    expect(screen.getByRole('searchbox')).toHaveAttribute('placeholder', 'certificates.searchPlaceholder')
    expect(screen.getByTitle('table.exportData')).toBeInTheDocument()
    expect(screen.getByTitle('table.filterPresets')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'table.density' })).toBeInTheDocument()
    for (const filter of ['common.allCAs', 'certificates.allSources', 'certificates.allTemplates']) {
      expect(screen.getByRole('button', { name: filter })).toBeInTheDocument()
    }
  })
})

describe('CertificatesPage: rows', () => {
  const cellsOf = (cn) => within(row(cn)).getAllByRole('cell').slice(1, 8).map((td) => td.textContent)

  it('shows one state per row, in words', async () => {
    await mount()
    expect(cellsOf('web.example.com')[2]).toBe('common.valid')
    expect(cellsOf('soon.example.com')[2]).toBe('certificates.views.expiring')
    expect(cellsOf('late.example.com')[2]).toBe('common.expired')
    expect(cellsOf('gone.example.com')[2]).toBe('common.revoked')
    for (const cn of ['web.example.com', 'soon.example.com', 'late.example.com', 'gone.example.com']) {
      expect(row(cn).querySelectorAll('.lv-pill')).toHaveLength(1)
    }
  })

  it('reads name, description, issuer, source and algorithm across the row', async () => {
    await mount()
    const cells = cellsOf('web.example.com')
    expect(cells[0]).toBe('web.example.com')
    expect(cells[1]).toBe('Front door')
    expect(cells[3]).toBe('Issuing CA 1')
    expect(cells[4]).toBe('certificates.sourceAcme')
    expect(cells[6]).toMatch(/P-?256/)
    // No description: an empty cell, not a second line under the name
    expect(cellsOf('soon.example.com')[1]).toBe('')
  })

  it('says how far the expiry is and colours it by urgency', async () => {
    await mount()
    const due = (cn) => row(cn).querySelector('.lv-due')
    expect(due('web.example.com').querySelector('.lv-due-rel')).toHaveTextContent('time.inDays:200')
    expect(due('web.example.com').className).not.toMatch(/is-(warn|bad)/)
    expect(due('soon.example.com').querySelector('.lv-due-rel')).toHaveTextContent('time.inDays:3')
    expect(due('soon.example.com')).toHaveClass('is-warn')
    expect(due('late.example.com').querySelector('.lv-due-rel')).toHaveTextContent('time.overdueDays:5')
    expect(due('late.example.com')).toHaveClass('is-bad')
    // The exact date and time, one level down
    expect(due('web.example.com')).toHaveAttribute('tabindex', '0')
    expect(due('web.example.com').dataset.tip).toBeTruthy()
  })

  it('counts nothing down for a revoked certificate', async () => {
    await mount()
    const due = row('gone.example.com').querySelector('.lv-due')
    expect(due.querySelector('time')).toBeInTheDocument()
    expect(due.querySelector('.lv-due-rel')).toBeNull()
    expect(due.className).not.toMatch(/is-(warn|bad)/)
  })

  it('marks a held key, a hybrid member and an orphan after the name', async () => {
    await mount()
    expect(within(row('web.example.com')).getByRole('img', { name: 'certificates.keyHeld' })).toBeInTheDocument()
    expect(within(row('soon.example.com')).queryByRole('img', { name: 'certificates.keyHeld' })).toBeNull()
    expect(within(row('gone.example.com')).getByRole('img', { name: 'certificates.hybrid.rolePq' })).toBeInTheDocument()
    expect(within(row('late.example.com')).getByRole('img', { name: 'certificates.orphanDescription' })).toHaveTextContent('certificates.orphan')
  })

  it('says the range of the page in words', async () => {
    await mount()
    expect(document.querySelector('footer.lv-footer')).toHaveTextContent('certificates.range:1/25/276')
  })

  it('marks the row of the certificate on top in the dock', async () => {
    state.opened = [{ key: 'certificate:7', type: 'certificate', entityId: 7 }, { key: 'ca:8', type: 'ca', entityId: 8 }]
    state.activeKey = 'certificate:7'
    await mount()
    expect(row('web.example.com')).toHaveClass('is-opened')
    expect(row('soon.example.com')).not.toHaveClass('is-opened')
  })

  it('marks no row for a CA of the same id on top in the dock', async () => {
    state.opened = [{ key: 'ca:8', type: 'ca', entityId: 8 }]
    state.activeKey = 'ca:8'
    await mount()
    expect(document.querySelector('tr.is-opened')).toBeNull()
  })
})

describe('CertificatesPage on a phone', () => {
  beforeEach(() => { state.mobile = true })

  it('keeps the cards under the same head and tabs', async () => {
    await mount()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByRole('heading', { level: 1, name: 'common.certificates' })).toBeInTheDocument()
    expect(screen.getAllByRole('tab').length).toBeGreaterThanOrEqual(6)
    expect(screen.getByRole('button', { name: 'certificates.issue' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'common.import' })).toBeInTheDocument()
  })

  it('shows on a card the name, its description, the state, the issuer, the source and the expiry', async () => {
    await mount([WEB])
    const name = screen.getByText('web.example.com')
    expect(name.parentElement).toHaveTextContent(/^web\.example\.comFront door$/)
    // One card on screen: its second line says who issued it, how, and when it is due
    const list = screen.getByRole('main')
    expect(list.querySelectorAll('.lv-pill')).toHaveLength(1)
    expect(list.querySelector('.lv-pill')).toHaveTextContent('common.valid')
    expect(within(list).getByText('Issuing CA 1')).toBeInTheDocument()
    expect(within(list).getByText('certificates.sourceAcme')).toBeInTheDocument()
    expect(list.querySelector('.lv-due-rel')).toHaveTextContent('time.inDays:200')
  })
})
