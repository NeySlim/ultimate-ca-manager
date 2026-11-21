/**
 * The Certificates page drawn from the Atelier mockup (pageHead, statusFilters, tableView, the
 * phone records, the states, the selection bar and its dialogs, the overview links and the saved
 * filters), over the real list API (mocked here).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, cleanup, act } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => {
      if (!opts || typeof opts !== 'object') return key
      const vals = ['n', 'count', 'start', 'end', 'label', 'value', 'query', 'page', 'name', 'action', 'algo', 'bits', 'px'].filter((k) => opts[k] !== undefined).map((k) => opts[k])
      return vals.length ? `${key}:${vals.join('/')}` : key
    },
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(null),
  },
}))
const state = vi.hoisted(() => ({ mobile: false, write: true, opened: [], activeKey: null, openEntity: null }))
const svc = vi.hoisted(() => ({ getAll: vi.fn(), getStats: vi.fn(), bulkExport: vi.fn(), cas: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ i18nKey }) => i18nKey,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: state.mobile, isDesktop: !state.mobile }),
  useInspector: () => ({
    openEntity: state.openEntity, closeEntity: vi.fn(), closeAll: vi.fn(), setActiveKey: vi.fn(), setEntityData: vi.fn(),
    opened: state.opened, activeKey: state.activeKey, setGeometry: vi.fn(), setCollapsed: vi.fn(),
    height: 278, width: 460, position: 'bottom', collapsed: false,
  }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: state.mobile }) }))
vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({ canWrite: () => state.write, canDelete: () => state.write, hasPermission: () => state.write, canRead: () => true }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => (...a) => state.openEntity(...a) }))
vi.mock('../../services', () => ({
  certificatesService: {
    getAll: (...a) => svc.getAll(...a), getStats: (...a) => svc.getStats(...a), bulkExport: (...a) => svc.bulkExport(...a),
    export: vi.fn(), getById: vi.fn().mockResolvedValue({ data: {} }),
  },
  casService: { getAll: (...a) => svc.cas(...a) },
  truststoreService: { addFromCA: vi.fn() },
}))
// The import and issue dialogs are their own subjects: a stand-in says when they open
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: ({ isOpen }) => (isOpen ? <div data-testid="import-open" /> : null) }))
vi.mock('../certificates/IssueCertificateDialog', () => ({ IssueCertificateDialog: ({ open }) => (open ? <div data-testid="issue-open" /> : null) }))
vi.mock('../../components/shell/SetupCard', () => ({ SetupCard: () => null }))
vi.mock('../certificates/dialogs/ExportDialog', () => ({ ExportDialog: ({ open, entityName }) => (open ? <div data-testid="export-open">{entityName}</div> : null) }))

import CertificatesPage from '../CertificatesPage'

const NOW = new Date('2026-11-08T12:00:00Z')
const DAY = 86400000
const at = (days) => new Date(NOW.getTime() + days * DAY).toISOString()
const WEB = {
  id: 7, cn: 'web.example.com', common_name: 'web.example.com', descr: 'Front door', status: 'valid', caref: 'ca-1',
  issuer: 'CN=Issuing CA 1,O=Example', source: 'acme', has_private_key: true, key_algorithm: 'EC-P256', key_type: 'EC-P256',
  valid_to: at(200), compliance_grade: 'A', compliance_score: 93, created_at: at(-10), san_combined: 'web.example.com', template_name: 'Serveur TLS',
}
const SOON = { ...WEB, id: 8, cn: 'soon.example.com', common_name: 'soon.example.com', descr: '', status: 'expiring', valid_to: at(2.5), has_private_key: false, source: 'manual' }
const LATE = { ...WEB, id: 9, cn: 'late.example.com', common_name: 'late.example.com', status: 'expired', valid_to: at(-4.5), caref: 'gone' }
const GONE = { ...WEB, id: 10, cn: 'gone.example.com', common_name: 'gone.example.com', status: 'revoked', revoked: true, valid_to: at(-4.5), related_certificate_id: 7, hybrid_role: 'pq' }
const ROWS = [WEB, SOON, LATE, GONE]

const Where = () => <output data-testid="where">{useLocation().search}</output>
const mount = async (url = '/certificates', rows = ROWS, total = 276) => {
  svc.getAll.mockResolvedValue({ data: rows, meta: { total } })
  const view = render(<MemoryRouter initialEntries={[url]}><CertificatesPage /><Where /></MemoryRouter>)
  if (rows.length) await screen.findAllByText(rows[0].cn)
  else await waitFor(() => expect(svc.getAll).toHaveBeenCalled())
  return view
}
const lastParams = () => svc.getAll.mock.calls[svc.getAll.mock.calls.length - 1][0]
const where = () => screen.getByTestId('where').textContent
const zone = () => screen.getByTestId('certificates-zone')
const head = () => zone().querySelector('header.page-head')
const tabs = () => within(screen.getByRole('group', { name: 'certificates.viewsLabel' })).getAllByRole('button')
const tab = (id) => tabs().find((b) => b.dataset.status === id)
const row = (cn) => screen.getByRole('row', { name: new RegExp(cn.replace(/\./g, '\\.')) })
const headers = () => [...zone().querySelectorAll('thead th')].map((th) => th.textContent).filter((x) => x && x !== 'common.actions')
const settle = () => new Promise((r) => setTimeout(r, 400))

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  window.localStorage.clear()
  Object.assign(state, { mobile: false, write: true, opened: [], activeKey: null, openEntity: vi.fn() })
  svc.getAll.mockReset()
  svc.bulkExport.mockReset()
  svc.getStats.mockReset()
  svc.getStats.mockResolvedValue({ data: { valid: 250, expiring: 20, expired: 4, revoked: 2, total: 1234, sources: ['acme', 'manual'] } })
  svc.cas.mockReset()
  svc.cas.mockResolvedValue({ data: [{ id: 1, refid: 'ca-1', descr: 'Root CA' }, { id: 2, refid: 'ca-2', descr: 'Issuing CA', parent_id: 1 }] })
  Object.values(stable.notify).forEach((f) => f.mockClear?.())
})
afterEach(() => { vi.useRealTimers() })

describe('CertificatesPage: the page head (pageHead)', () => {
  it('shows the title, the whole inventory in words and the intent', async () => {
    await mount()
    expect(within(head()).getByRole('heading', { level: 1, name: 'common.certificates' })).toHaveAttribute('id', 'main-title')
    await waitFor(() => expect(head().querySelector('.total')).toHaveTextContent('certificates.total:1234'))
    expect(head()).toHaveTextContent('certificates.intent')
  })

  it('puts Importer then Émettre, the main action last', async () => {
    await mount()
    const buttons = within(head()).getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(['common.import', 'certificates.issue'])
    expect(buttons[0]).toHaveClass('btn', 'quiet')
    expect(buttons[1]).toHaveClass('btn', 'primary')
    fireEvent.click(buttons[1])
    expect(screen.getByTestId('issue-open')).toBeInTheDocument()
  })

  it('opens the import from Importer', async () => {
    await mount()
    fireEvent.click(within(head()).getByRole('button', { name: 'common.import' }))
    expect(screen.getByTestId('import-open')).toBeInTheDocument()
  })

  it('offers neither to a principal who cannot write certificates', async () => {
    state.write = false
    await mount()
    expect(within(head()).queryAllByRole('button')).toEqual([])
  })
})

describe('CertificatesPage: the state filters (statusFilters)', () => {
  it('counts each state over the whole inventory, À renouveler marked', async () => {
    await mount()
    await waitFor(() => expect(tab('')).toHaveTextContent(/^certificates\.views\.all1,234$/))
    expect(tabs().map((b) => b.dataset.status)).toEqual(['', 'expiring', 'valid', 'expired', 'revoked', 'archived'])
    expect(tab('expiring').querySelector('.dot.warn')).not.toBeNull()
    expect(tab('archived').querySelector('.counter')).toBeNull()
    expect(tab('').getAttribute('aria-pressed')).toBe('true')
  })

  it('shows Orphelins only when there are orphans', async () => {
    svc.getStats.mockResolvedValue({ data: { valid: 1, expiring: 0, expired: 0, revoked: 0, orphan: 7, total: 8 } })
    await mount()
    await waitFor(() => expect(tab('orphan')).toHaveTextContent(/7$/))
  })

  it('writes the state in the URL and asks the server for it, page one', async () => {
    await mount()
    fireEvent.click(tab('valid'))
    await waitFor(() => expect(lastParams().status).toEqual(['valid']))
    expect(where()).toBe('?view=valid')
    expect(lastParams().page).toBe(1)
    expect(tab('valid').getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(tab(''))
    await waitFor(() => expect(lastParams().status).toBeUndefined())
    expect(where()).toBe('')
  })

  it('ignores a state the list does not know', async () => {
    await mount('/certificates?view=bogus')
    expect(lastParams().status).toBeUndefined()
    expect(tab('').getAttribute('aria-pressed')).toBe('true')
  })

  it('offers « Effacer recherche, AC et source » only once something narrows the list', async () => {
    await mount()
    expect(screen.queryByRole('button', { name: /certificates\.clearSearchAndFilters/ })).toBeNull()
    fireEvent.change(screen.getByRole('combobox', { name: 'certificates.filterBySource' }), { target: { value: 'acme' } })
    await waitFor(() => expect(lastParams().source).toEqual(['acme']))
    fireEvent.click(screen.getByRole('button', { name: /certificates\.clearSearchAndFilters/ }))
    await waitFor(() => expect(lastParams().source).toBeUndefined())
  })
})

describe('CertificatesPage: the toolbar (tableView)', () => {
  it('searches on the server once the typing stops, and says how many results', async () => {
    await mount()
    const box = screen.getByRole('searchbox', { name: 'certificates.searchLabel' })
    expect(box).toHaveAttribute('placeholder', 'certificates.searchPlaceholder')
    fireEvent.change(box, { target: { value: 'web' } })
    expect(zone().querySelector('.search-status')).toHaveTextContent('table.searching')
    await waitFor(() => expect(lastParams().search).toBe('web'), { timeout: 2000 })
    await waitFor(() => expect(zone().querySelector('.search-status')).toHaveTextContent('table.results:276'))
  })

  it('filters by one authority, grouped under its root, and by source', async () => {
    await mount()
    const ca = await screen.findByRole('combobox', { name: 'certificates.filterByCa' })
    await waitFor(() => expect(ca.querySelector('optgroup')).not.toBeNull())
    expect(ca.querySelector('optgroup').getAttribute('label')).toBe('Root CA')
    expect([...ca.querySelectorAll('optgroup option')].map((o) => o.textContent)).toEqual(['Root CA', 'Issuing CA'])
    fireEvent.change(ca, { target: { value: '2' } })
    await waitFor(() => expect(lastParams().ca_id).toEqual(['2']))
    fireEvent.change(screen.getByRole('combobox', { name: 'certificates.filterBySource' }), { target: { value: 'manual' } })
    await waitFor(() => expect(lastParams().source).toEqual(['manual']))
  })

  it('keeps the « modified from its template » filter in the Filters dialog, its chip removable', async () => {
    await mount()
    expect(zone().querySelector('.toolbar #template-filter')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'certificates.filters.title' }))
    const dialog = await screen.findByTestId('filters-dialog')
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'certificates.template' }), { target: { value: 'modified' } })
    await waitFor(() => expect(lastParams().template_modified).toBe('true'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'table.done' }))
    const chips = zone().querySelector('.applied-filters')
    expect(chips).toHaveTextContent('table.filterChip:certificates.template/certificates.modifiedFromTemplate')
    fireEvent.click(within(chips).getByRole('button', { name: /table\.removeFilter/ }))
    await waitFor(() => expect(lastParams().template_modified).toBeUndefined())
  })

  it('shows the mockup columns in order, the product ones in the Columns dialog', async () => {
    await mount()
    expect(headers()).toEqual(['common.commonName', 'common.description', 'certificates.state', 'common.issuer', 'certificates.source', 'certificates.expiry', 'common.keyAlgorithm'])
    fireEvent.click(screen.getByRole('button', { name: 'table.columns' }))
    const dialog = await screen.findByRole('dialog')
    const boxes = within(dialog).getAllByRole('checkbox')
    expect(boxes.map((b) => b.dataset.column)).toEqual(['description', 'ca', 'source', 'expiry', 'key', 'grade', 'pair', 'created'])
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'certificates.complianceColumn' }))
    expect(headers()).toContain('certificates.complianceColumn')
  })

  it('sorts on the server: the same header twice reverses, Source does not sort', async () => {
    await mount()
    expect(lastParams()).toMatchObject({ sort_by: 'valid_to', sort_order: 'asc' })
    fireEvent.click(screen.getByRole('button', { name: 'common.commonName' }))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'subject', sort_order: 'asc' }))
    fireEvent.click(screen.getByRole('button', { name: 'common.commonName' }))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'subject', sort_order: 'desc' }))
    expect(zone().querySelector('th.col-name').getAttribute('aria-sort')).toBe('descending')
    expect(zone().querySelector('th.col-source button')).toBeNull()
  })

  it('pages on the server: size, next, jump', async () => {
    await mount()
    expect(zone().querySelector('footer.table-footer')).toHaveTextContent('certificates.range:276/1/12')
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await waitFor(() => expect(lastParams().page).toBe(2))
    fireEvent.change(screen.getByRole('combobox', { name: 'certificates.perPageLabel' }), { target: { value: '50' } })
    await waitFor(() => expect(lastParams()).toMatchObject({ page: 1, per_page: 50 }))
    const jump = zone().querySelector('#page-jump')
    fireEvent.change(jump, { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'table.goToPage' }))
    await waitFor(() => expect(lastParams().page).toBe(4))
  })
})

describe('CertificatesPage: the rows', () => {
  it('reads name, description, state, issuer, source, expiry and algorithm across the row', async () => {
    await mount()
    const cells = [...row('web.example.com').querySelectorAll('td')].map((td) => td.textContent)
    expect(cells.slice(1, 8)).toEqual(['web.example.com', 'Front door', 'common.valid', 'Issuing CA 1', 'certificates.sourceAcme', expect.stringContaining('time.short.months'), 'ECDSA P-256'])
  })

  it('draws each state as the mockup badge, with its icon', async () => {
    await mount()
    expect(row('web.example.com').querySelector('.badge.good')).toHaveTextContent('common.valid')
    expect(row('soon.example.com').querySelector('.badge.warn')).toHaveTextContent('certificates.views.expiring')
    expect(row('late.example.com').querySelector('.badge.bad')).toHaveTextContent('common.expired')
    expect(row('gone.example.com').querySelector('.badge.muted')).toHaveTextContent('common.revoked')
    expect(row('gone.example.com').querySelector('.badge svg')).not.toBeNull()
  })

  it('says what is left: days in amber when due, Échu once lapsed, Révoqué for a revoked one', async () => {
    await mount()
    expect(row('soon.example.com').querySelector('.expiry-cell')).toHaveClass('warn')
    expect(row('late.example.com').querySelector('.remaining')).toHaveClass('bad')
    expect(row('late.example.com').querySelector('.remaining')).toHaveTextContent('time.short.expired')
    expect(row('gone.example.com').querySelector('.remaining')).toHaveTextContent('common.revoked')
    expect(row('gone.example.com').querySelector('.remaining')).toHaveClass('muted')
  })

  it('marks a held key, a linked pair member and an orphan after the name', async () => {
    await mount()
    expect(within(row('web.example.com')).getByRole('img', { name: 'certificates.keyHeld' })).toBeInTheDocument()
    expect(within(row('gone.example.com')).getByRole('img', { name: 'certificates.hybrid.rolePq' })).toBeInTheDocument()
    expect(within(row('late.example.com')).getByRole('img', { name: 'certificates.orphanDescription' })).toBeInTheDocument()
  })

  it('opens a certificate from its name or its chevron, not from the rest of the row', async () => {
    await mount()
    fireEvent.click(within(row('web.example.com')).getByRole('button', { name: /^web\.example\.com/ }))
    expect(state.openEntity).toHaveBeenCalledWith('certificate', 7)
    state.openEntity.mockClear()
    fireEvent.click(row('soon.example.com').querySelector('td.description-cell'))
    expect(state.openEntity).not.toHaveBeenCalled()
    fireEvent.click(within(row('soon.example.com')).getByRole('button', { name: 'table.openRow:soon.example.com' }))
    expect(state.openEntity).toHaveBeenCalledWith('certificate', 8)
  })

  it('exports one certificate from its row, to a read-only operator too', async () => {
    state.write = false
    await mount()
    fireEvent.click(within(row('web.example.com')).getByRole('button', { name: 'table.rowAction:web.example.com/export.title' }))
    expect(screen.getByTestId('export-open')).toHaveTextContent('web.example.com')
    expect(state.openEntity).not.toHaveBeenCalled()
  })

  it('marks the row of the certificate on top in the dock, not a CA of the same id', async () => {
    state.opened = [{ key: 'certificate:7', type: 'certificate', entityId: 7 }]
    state.activeKey = 'certificate:7'
    await mount()
    expect(row('web.example.com')).toHaveClass('opened')
    cleanup()
    state.opened = [{ key: 'ca:7', type: 'ca', entityId: 7 }]
    state.activeKey = 'ca:7'
    await mount()
    expect(row('web.example.com')).not.toHaveClass('opened')
  })
})

describe('CertificatesPage: the selection (batchbar, largeBatch)', () => {
  const tick = (cn) => fireEvent.click(within(row(cn)).getByRole('checkbox'))

  it('counts the ticked rows, locks the names and gives them back', async () => {
    await mount()
    tick('web.example.com')
    const bar = zone().querySelector('.batchbar')
    expect(bar).toHaveTextContent('certificates.selectedOnPage:1')
    expect(within(row('soon.example.com')).getByRole('button', { name: /^soon\.example\.com/ })).toBeDisabled()
    fireEvent.click(within(bar).getByRole('button', { name: 'table.clearSelection' }))
    expect(zone().querySelector('.batchbar')).toBeNull()
    expect(within(row('soon.example.com')).getByRole('button', { name: /^soon\.example\.com/ })).not.toBeDisabled()
  })

  it('compares exactly two: the dialog lists the mockup properties, the different ones marked', async () => {
    await mount()
    tick('web.example.com')
    const compare = () => within(zone().querySelector('.batchbar')).getByRole('button', { name: 'common.compare' })
    expect(compare()).toBeDisabled()
    tick('soon.example.com')
    fireEvent.click(compare())
    const dialog = await screen.findByTestId('compare-dialog')
    const rows = [...dialog.querySelectorAll('tbody tr')]
    expect(rows.map((r) => r.querySelector('th').textContent)).toEqual(['certificates.state', 'common.description', 'compare.authority', 'common.keyAlgorithm', 'certificates.expiry', 'certificates.source', 'certificates.template', 'SAN', 'common.privateKey'])
    expect(rows[0]).toHaveClass('different')
    expect(rows[2]).not.toHaveClass('different')
    tick('late.example.com')
    expect(compare()).toBeDisabled()
  })

  it('offers every result once the page is ticked, and exports them by the bulk dialog', async () => {
    await mount()
    fireEvent.click(zone().querySelector('#select-all'))
    fireEvent.click(screen.getByRole('button', { name: 'certificates.selectAllResults:276' }))
    expect(zone().querySelector('#selection-count')).toHaveTextContent('certificates.allResultsSelected:276')
    expect(within(zone().querySelector('.batchbar')).getByRole('button', { name: 'common.compare' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'certificates.keepPageOnly' }))
    expect(zone().querySelector('#selection-count')).toHaveTextContent('certificates.selectedOnPage:4')
  })

  it('exports the ticked certificates as one PEM file and says what was skipped', async () => {
    const blob = new Blob(['x'])
    blob.exportedCount = 1
    blob.skippedCount = 1
    svc.bulkExport.mockResolvedValue(blob)
    global.URL.createObjectURL = vi.fn(() => 'blob:x')
    global.URL.revokeObjectURL = vi.fn()
    await mount()
    tick('web.example.com')
    tick('soon.example.com')
    fireEvent.click(zone().querySelector('#bulk-export'))
    const dialog = await screen.findByTestId('bulk-export-dialog')
    expect(within(dialog).getByRole('radio', { name: /PEM/ })).toBeChecked()
    fireEvent.click(within(dialog).getByRole('button', { name: 'certificates.bulkExport.confirm:2' }))
    await waitFor(() => expect(svc.bulkExport).toHaveBeenCalledWith([7, 8], 'pem'))
    expect(stable.notify.showWarning).toHaveBeenCalled()
  })

  it('says why a batch export failed', async () => {
    svc.bulkExport.mockRejectedValue(Object.assign(new Error('nope'), { status: 400 }))
    await mount()
    tick('web.example.com')
    fireEvent.click(zone().querySelector('#bulk-export'))
    fireEvent.click(within(await screen.findByTestId('bulk-export-dialog')).getByRole('button', { name: /bulkExport\.confirm/ }))
    await waitFor(() => expect(stable.notify.showError).toHaveBeenCalledWith('nope'))
  })

  it('exports the metadata of every result from the toolbar, as CSV', async () => {
    const created = []
    global.URL.createObjectURL = vi.fn((b) => { created.push(b); return 'blob:x' })
    global.URL.revokeObjectURL = vi.fn()
    await mount()
    fireEvent.click(screen.getByRole('button', { name: 'certificates.exportList' }))
    const dialog = await screen.findByTestId('bulk-export-dialog')
    expect(within(dialog).getByRole('radio', { name: /CSV/ })).toBeChecked()
    expect(dialog.querySelector('#bulk-count')).toHaveTextContent('certificates.bulkExport.all')
    svc.getAll.mockResolvedValue({ data: [WEB], meta: { total: 1 } })
    fireEvent.click(within(dialog).getByRole('button', { name: /bulkExport\.confirm/ }))
    await waitFor(() => expect(created.length).toBe(1))
    const text = await new Promise((r) => { const f = new FileReader(); f.onload = () => r(f.result); f.readAsText(created[0]) })
    expect(text.split('\n')[0]).toContain('common.commonName,common.description')
    expect(text).toContain('web.example.com,Front door')
  })

  it('drops from the selection a row the list no longer shows', async () => {
    await mount()
    tick('web.example.com')
    svc.getAll.mockResolvedValue({ data: [SOON], meta: { total: 1 } })
    act(() => { window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'certificate' } })) })
    await waitFor(() => expect(zone().querySelector('.batchbar')).toBeNull())
  })
})

describe('CertificatesPage: overview links and saved filters', () => {
  it('sends the link filters alone, one removable chip each', async () => {
    window.localStorage.setItem('ucm-filter-certs-source', JSON.stringify(['acme']))
    await mount('/certificates?status=expiring&sig_hash=sha1')
    expect(lastParams().source).toBeUndefined()
    expect(lastParams().status).toEqual(['expiring'])
    const chips = zone().querySelector('.applied-filters')
    expect(chips).toHaveTextContent('table.filterChip')
    fireEvent.click(within(chips).getAllByRole('button', { name: /table\.removeFilter/ })[0])
    await waitFor(() => expect(where()).toBe('?sig_hash=sha1'))
    expect(lastParams().status).toBeUndefined()
  })

  it('in a link view a state rewrites the link statuses only, Tous clears them, the other filters stay', async () => {
    await mount('/certificates?status=expiring&sig_hash=sha1')
    expect(tab('expiring').getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(tab('expired'))
    await waitFor(() => expect(where()).toBe('?sig_hash=sha1&status=expired'))
    await waitFor(() => expect(lastParams()).toMatchObject({ status: ['expired'], sig_hash: ['sha1'] }))
    fireEvent.click(tab(''))
    await waitFor(() => expect(where()).toBe('?sig_hash=sha1'))
  })

  it('reads the weak-key link as one chip and removes both filters', async () => {
    await mount('/certificates?key_algo_prefix=RSA&key_bits_below=3072')
    const chips = zone().querySelector('.applied-filters')
    expect(within(chips).getAllByRole('button', { name: /table\.removeFilter/ })).toHaveLength(1)
    fireEvent.click(within(chips).getByRole('button', { name: /table\.removeFilter/ }))
    await waitFor(() => expect(where()).toBe(''))
  })

  it('saves the current state and filters, and reopens them', async () => {
    await mount('/certificates?view=expired')
    fireEvent.change(screen.getByRole('combobox', { name: 'certificates.filterBySource' }), { target: { value: 'acme' } })
    await settle()
    fireEvent.click(screen.getByRole('button', { name: 'certificates.filters.title' }))
    let dialog = await screen.findByTestId('filters-dialog')
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'table.presetName' }), { target: { value: 'Old ACME' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'table.saveFilters' }))
    expect(JSON.parse(window.localStorage.getItem('ucm-certs-presets'))[0]).toMatchObject({ name: 'Old ACME', filters: { status: ['expired'], source: ['acme'] } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'table.done' }))
    fireEvent.click(tab(''))
    fireEvent.click(screen.getByRole('button', { name: /certificates\.clearSearchAndFilters/ }))
    await waitFor(() => expect(lastParams().source).toBeUndefined())
    fireEvent.click(screen.getByRole('button', { name: 'certificates.filters.title' }))
    dialog = await screen.findByTestId('filters-dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Old ACME' }))
    await waitFor(() => expect(lastParams()).toMatchObject({ status: ['expired'], source: ['acme'] }))
    expect(where()).toBe('?view=expired')
  })

  it('a preset with several states applies them all: no state pressed, one chip', async () => {
    window.localStorage.setItem('ucm-certs-presets', JSON.stringify([{ id: 1, name: 'Due', filters: { status: ['expiring', 'expired'] } }]))
    await mount()
    fireEvent.click(screen.getByRole('button', { name: 'certificates.filters.title' }))
    fireEvent.click(within(await screen.findByTestId('filters-dialog')).getByRole('button', { name: 'Due' }))
    await waitFor(() => expect(lastParams().status).toEqual(['expiring', 'expired']))
    expect(tabs().filter((b) => b.getAttribute('aria-pressed') === 'true')).toEqual([])
    const chips = zone().querySelector('.applied-filters')
    fireEvent.click(within(chips).getByRole('button', { name: /table\.removeFilter/ }))
    await waitFor(() => expect(lastParams().status).toBeUndefined())
  })
})

describe('CertificatesPage: states (emptyBlock, loadError, skeletonRows)', () => {
  it('says the first issuance waits for an issuing CA, with Émettre un certificat when one exists', async () => {
    svc.getStats.mockResolvedValue({ data: { valid: 0, expiring: 0, expired: 0, revoked: 0, total: 0 } })
    await mount('/certificates', [], 0)
    await waitFor(() => expect(zone().querySelector('#empty-certificates')).not.toBeNull())
    expect(zone().querySelector('#empty-certificates')).toHaveTextContent('certificates.emptyHintReady')
    fireEvent.click(within(zone().querySelector('#empty-certificates')).getByRole('button', { name: 'certificates.issueCertificate' }))
    expect(screen.getByTestId('issue-open')).toBeInTheDocument()
    cleanup()
    svc.cas.mockResolvedValue({ data: [] })
    await mount('/certificates', [], 0)
    await waitFor(() => expect(zone().querySelector('#empty-certificates')).toHaveTextContent('certificates.emptyHintNoCa'))
  })

  it('says nothing matches a search, with Réinitialiser les filtres', async () => {
    await mount('/certificates?view=revoked', [], 0)
    const block = await screen.findByText('certificates.noMatchTitle')
    fireEvent.click(within(block.closest('.empty')).getByRole('button', { name: 'certificates.resetFilters' }))
    await waitFor(() => expect(where()).toBe(''))
  })

  it('shows the cause and Réessayer in place of the list, and reads again', async () => {
    svc.getAll.mockRejectedValueOnce(Object.assign(new Error('down'), { status: 503, request: 'GET /api/v2/certificates' }))
    render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveAttribute('id', 'load-error-certificates')
    expect(alert).toHaveTextContent('certificates.loadFailed')
    expect(within(alert).getByRole('link', { name: /work\.viewLog/ })).toHaveAttribute('href', '/audit')
    svc.getAll.mockResolvedValue({ data: ROWS, meta: { total: 4 } })
    fireEvent.click(within(alert).getByRole('button', { name: 'table.retry' }))
    await screen.findByText('web.example.com')
  })

  it('draws skeleton rows and bars in the counters while the first read is out', async () => {
    svc.getAll.mockReturnValue(new Promise(() => {}))
    render(<MemoryRouter><CertificatesPage /></MemoryRouter>)
    await waitFor(() => expect(zone().querySelectorAll('tr.sk-row').length).toBe(12))
    expect(tab('').querySelector('.sk-num')).not.toBeNull()
    expect(head().querySelector('.total')).toHaveTextContent('')
  })
})

describe('CertificatesPage on a phone (mobile records)', () => {
  it('shows a record per certificate, the chevron at the right, the whole record opening it', async () => {
    state.mobile = true
    await mount()
    const record = screen.getByText('web.example.com').closest('article.mobile-record')
    expect(record.querySelector('.row-description')).toHaveTextContent('Front door')
    expect(record.querySelector('.row-meta')).toHaveTextContent('Issuing CA 1certificates.sourceAcmecertificates.keyInUcm')
    expect(record.querySelector('.row-status .badge.good')).toBeInTheDocument()
    expect(record.querySelector('.row-top > .icon-btn')).toHaveAttribute('aria-label', 'table.openRow:web.example.com')
    fireEvent.click(record.querySelector('.row-meta'))
    expect(state.openEntity).toHaveBeenCalledWith('certificate', 7)
    expect(zone().querySelector('table')).toBeNull()
  })
})
