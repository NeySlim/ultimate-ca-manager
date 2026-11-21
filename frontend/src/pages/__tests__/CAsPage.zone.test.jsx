/**
 * CAsPage, the mockup's Authorities view: page head, state filters kept in the URL, the search,
 * the tree beside the side panel of the selected authority (`?authority=`), the list, the chain
 * repair, creation and import, the empty and failed states, and every page function in reach.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { ca, smallHierarchy, largeInstallation } from '../cas/__tests__/caFixtures'

const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : opts?.name ? `${key} ${opts.name}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false),
  },
  openEntity: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

let mockCanWrite = true
let mockCanRead = true
const mobile = { isMobile: false, isDesktop: true, isTablet: false, isLargeScreen: true, screenWidth: 1600 }
vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => mobile,
  useInspector: () => ({ openEntity: stable.openEntity, opened: [] }),
}))
vi.mock('../../contexts/InspectorContext', () => ({ useInspector: () => ({ openEntity: stable.openEntity, opened: [] }) }))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => mobile }))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => stable.openEntity }))

vi.mock('../../hooks', () => ({
  usePermission: () => ({
    canWrite: () => mockCanWrite, canDelete: () => mockCanWrite, hasPermission: () => true, canRead: () => mockCanRead,
  }),
  useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
  useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
}))

const getAll = vi.fn()
const getChainRepairStatus = vi.fn()
const getCrossFindings = vi.fn()
const getCrossCertificates = vi.fn()
const runChainRepair = vi.fn()
const exportCA = vi.fn()
vi.mock('../../services', () => ({
  casService: {
    getAll: (...a) => getAll(...a),
    getChainRepairStatus: (...a) => getChainRepairStatus(...a),
    getCrossFindings: (...a) => getCrossFindings(...a),
    getCrossCertificates: (...a) => getCrossCertificates(...a),
    runChainRepair: (...a) => runChainRepair(...a),
    export: (...a) => exportCA(...a),
  },
  crlService: { getOcspStatus: () => Promise.resolve({ data: { enabled: true } }) },
}))
const downloadExport = vi.fn().mockResolvedValue(null)
vi.mock('../../lib/exportDownload', () => ({ downloadExport: (...a) => downloadExport(...a) }))

vi.mock('../../components/cas/ManageTemplatePinsModal', () => ({ ManageTemplatePinsModal: () => null }))
vi.mock('../../components/cas/RestorePrimaryModal', () => ({ RestorePrimaryModal: () => null }))
// The side panel has its own tests: here it names the authority and hands « Émettre avec cette AC » to the page
vi.mock('../cas/CASide', () => ({
  CASide: ({ ca: shown, onIssue }) => (
    <aside data-testid="ca-side"><h2>{shown.name}</h2><button type="button" onClick={() => onIssue(shown)}>issue-with</button></aside>
  ),
}))
vi.mock('../certificates/IssueCertificateDialog', () => ({
  IssueCertificateDialog: ({ open, initialData }) => (open ? <div data-testid="issue-dialog">{JSON.stringify(initialData)}</div> : null),
}))
let createdCA = { id: 42, name: 'New CA' }
vi.mock('../cas/CreateCAModal', () => ({
  CreateCAModal: ({ open, onSuccess }) => (open ? <button type="button" onClick={() => onSuccess(createdCA)}>create-modal</button> : null),
}))
let importResult = null
vi.mock('../../components/SmartImport', () => ({
  SmartImportModal: ({ isOpen, onImportComplete }) => (isOpen ? <button type="button" onClick={() => onImportComplete(importResult)}>import-modal</button> : null),
}))

import CAsPage from '../CAsPage'
import { blockedWhileSuspended } from '../../components/shell/__tests__/writeGuardProbe'

const Where = () => <output data-testid="where">{useLocation().pathname}{useLocation().search}</output>
const renderAt = (url = '/cas') => render(
  <MemoryRouter initialEntries={[url]}>
    <Routes>
      <Route path="/cas" element={<CAsPage />} />
      <Route path="/cas/:id" element={<CAsPage />} />
      <Route path="/certificates" element={null} />
    </Routes>
    <Where />
  </MemoryRouter>,
)
const where = () => screen.getByTestId('where').textContent
const filter = (id) => within(screen.getByRole('group', { name: 'cas.viewsLabel' })).getByRole('button', { name: new RegExp(`^cas\\.views\\.${id}`) })
const filterIds = () => within(screen.getByRole('group', { name: 'cas.viewsLabel' })).getAllByRole('button').map((b) => b.dataset.status || 'all')
const treeNames = () => screen.getAllByRole('treeitem').map((el) => document.getElementById(el.getAttribute('aria-labelledby')).textContent)
const loaded = () => waitFor(() => expect(screen.queryByRole('tree') || screen.queryByRole('table') || document.getElementById('empty-cas')
  || document.getElementById('load-error-cas')).not.toBeNull())
const linked = { stats: { total_cas: 6, total_certs: 32, orphan_cas: 0 }, task: {} }
const side = () => screen.getByTestId('ca-side')

beforeEach(() => {
  window.localStorage.clear()
  mockCanWrite = true
  mockCanRead = true
  mobile.isMobile = false
  importResult = null
  for (const fn of [getAll, getChainRepairStatus, getCrossFindings, getCrossCertificates, runChainRepair, exportCA, stable.openEntity]) fn.mockReset()
  getAll.mockResolvedValue({ data: smallHierarchy() })
  getChainRepairStatus.mockResolvedValue({ data: linked })
  getCrossFindings.mockResolvedValue({ data: { findings: [] } })
  getCrossCertificates.mockResolvedValue({ data: [] })
  runChainRepair.mockResolvedValue({ data: linked })
  downloadExport.mockClear()
})

describe('CAsPage: page head and state filters', () => {
  it('heads the page as the mockup: title, total in words, intent, Read the hierarchy', async () => {
    const { container } = renderAt()
    await loaded()
    expect(container.querySelector('.atl > #app main.stage .page-content > header.page-head')).not.toBeNull()
    expect(screen.getByRole('heading', { level: 1, name: 'common.cas' })).toHaveAttribute('id', 'main-title')
    expect(container.querySelector('.page-head .total')).toHaveTextContent('cas.total:6')
    expect(screen.getByText('cas.intent')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'cas.help.title' }))
    expect(within(screen.getByTestId('cas-help')).getByText('cas.help.text')).toBeInTheDocument()
  })

  it('counts every authority in the filters, with offline only when there is one', async () => {
    renderAt()
    await loaded()
    expect(filterIds()).toEqual(['all', 'roots', 'intermediates', 'expired', 'offline'])
    expect(filter('all')).toHaveTextContent(/^cas\.views\.all6$/)
    expect(filter('roots')).toHaveTextContent(/2$/)
    expect(filter('intermediates')).toHaveTextContent(/4$/)
    expect(filter('offline')).toHaveTextContent(/1$/)
  })

  it('writes the filter in the URL and filters the tree with it', async () => {
    renderAt()
    await loaded()
    fireEvent.click(filter('expired'))
    expect(where()).toContain('view=expired')
    expect(filter('expired')).toHaveAttribute('aria-pressed', 'true')
    expect(treeNames()).toEqual(['Example Root', 'Services', 'Legacy'])
    fireEvent.click(filter('all'))
    expect(where()).not.toContain('view=')
  })

  it('opens on the filter of the URL and ignores one it does not know', async () => {
    renderAt('/cas?view=roots')
    await loaded()
    expect(filter('roots')).toHaveAttribute('aria-pressed', 'true')
    expect(treeNames()).toEqual(['Example Root', 'Second Root'])
    document.body.innerHTML = ''
    renderAt('/cas?view=bogus')
    await loaded()
    expect(filter('all')).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('CAsPage: hierarchy and side panel', () => {
  it('opens on the tree beside the panel of its first authority, as the mockup', async () => {
    const { container } = renderAt()
    await loaded()
    expect(container.querySelector('#view-scroll.scroll-view > .ca-layout > section.panel.ca-tree-panel')).not.toBeNull()
    expect(treeNames()).toEqual(['Example Root', 'Identities', 'Services', 'Second Root'])
    expect(within(side()).getByRole('heading')).toHaveTextContent('Example Root')
    expect(screen.getByRole('button', { name: 'cas.hierarchy' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('selects a node by the keyboard and keeps it in the URL', async () => {
    renderAt()
    await loaded()
    fireEvent.keyDown(screen.getByRole('treeitem', { name: 'Services' }), { key: 'Enter' })
    expect(where()).toBe('/cas?authority=2')
    expect(within(side()).getByRole('heading')).toHaveTextContent('Services')
    expect(screen.getByRole('treeitem', { name: 'Services' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows the authority of the URL, and leads /cas/:id and ?selected= there', async () => {
    renderAt('/cas?authority=5')
    await loaded()
    expect(screen.getByRole('treeitem', { name: 'Identities' })).toHaveAttribute('aria-selected', 'true')
    expect(within(side()).getByRole('heading')).toHaveTextContent('Identities')
    document.body.innerHTML = ''
    renderAt('/cas/3')
    await waitFor(() => expect(where()).toBe('/cas?authority=3'))
    document.body.innerHTML = ''
    renderAt('/cas?selected=4')
    await waitFor(() => expect(where()).toBe('/cas?authority=4'))
  })

  it('issues with the authority of the panel', async () => {
    renderAt('/cas?authority=2')
    await loaded()
    fireEvent.click(within(side()).getByRole('button', { name: 'issue-with' }))
    expect(JSON.parse(screen.getByTestId('issue-dialog').textContent)).toEqual({ ca_id: 2 })
  })

  it('opens a stored choice of a replaced view (org, columns) on the tree', async () => {
    window.localStorage.setItem('ucm-ca-view-mode', 'columns')
    renderAt()
    await loaded()
    expect(screen.getByRole('tree')).toBeInTheDocument()
    expect(window.localStorage.getItem('ucm-ca-view-mode')).toBe('tree')
  })

  it('filters the tree from the search field, and resets when nothing matches', async () => {
    renderAt()
    await loaded()
    const search = screen.getByRole('searchbox', { name: 'cas.searchLabel' })
    fireEvent.change(search, { target: { value: 'internal' } })
    expect(treeNames()).toEqual(['Example Root', 'Services', 'Internal'])
    fireEvent.change(search, { target: { value: 'nothing like it' } })
    expect(screen.getByText('cas.tree.noMatch').closest('[role=status]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'cas.tree.reset' }))
    expect(treeNames()).toEqual(['Example Root', 'Identities', 'Services', 'Second Root'])
  })

  it('stays readable with 139 authorities: a handful of cards, the idle roots in one group', async () => {
    getAll.mockResolvedValue({ data: largeInstallation() })
    const { container } = renderAt()
    await loaded()
    expect(container.querySelector('.page-head .total')).toHaveTextContent('cas.total:139')
    expect(container.querySelectorAll('.ca-card')).toHaveLength(10)
    expect(screen.getAllByRole('treeitem').length).toBeLessThan(30)
    expect(screen.getByRole('treeitem', { name: 'cas.tree.idleRoots:120' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('draws the link of a cross-certificate between its issuer and its holder', async () => {
    getAll.mockResolvedValue({ data: [ca(1, { name: 'Old root' }), ca(2, { name: 'New root', cross_certificate_count: 1 })] })
    getCrossCertificates.mockResolvedValue({ data: [{ id: 9, ca_id: 2, issuer_caref: 'ref-1' }] })
    const { container } = renderAt()
    await loaded()
    await waitFor(() => expect(container.querySelector('[data-cross-link="1-2"]')).not.toBeNull())
    expect(getCrossCertificates).toHaveBeenCalledTimes(1)
    expect(getCrossCertificates).toHaveBeenCalledWith(2)
  })
})

describe('CAsPage: list', () => {
  it('lists the authorities in the module table: sort, download, chevron to the panel', async () => {
    renderAt()
    await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'cas.listMode' }))
    const table = await screen.findByRole('table')
    expect(table).toHaveClass('cert-table', 'module-table')
    expect(window.localStorage.getItem('ucm-ca-view-mode')).toBe('list')
    const row = within(table).getByRole('button', { name: 'Services' }).closest('tr')
    fireEvent.click(within(row).getByTitle('cas.downloadCertificate'))
    await waitFor(() => expect(exportCA).toHaveBeenCalledWith(2, 'pem'))
    fireEvent.click(within(row).getByRole('button', { name: 'cas.side.show Services' }))
    expect(where()).toBe('/cas?authority=2')
    // Sorted by name, then the other way
    const names = () => within(screen.getByRole('table')).getAllByRole('button').filter((b) => b.classList.contains('entity-name')).map((b) => b.textContent)
    expect(names()[0]).toBe('Example Root')
    fireEvent.click(within(table).getByRole('button', { name: 'common.name' }))
    expect(names()[0]).toBe('Services')
    // The filter applies to the list as to the tree
    fireEvent.click(filter('roots'))
    expect(names()).toEqual(['Second Root', 'Example Root'])
    expect(document.querySelector('footer.table-footer')).toHaveTextContent('cas.range:2')
  })

  it('pages a long list by 25 under a footer, back to page one on a sort or a search', async () => {
    getAll.mockResolvedValue({ data: largeInstallation() })
    renderAt()
    await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'cas.listMode' }))
    const table = await screen.findByRole('table')
    const footer = document.querySelector('footer.table-footer')
    const rows = () => within(screen.getByRole('table')).getAllByRole('row').length - 1
    expect(rows()).toBe(25)
    expect(footer).toHaveTextContent('cas.range:139')
    expect(footer).toHaveTextContent('1 / 6')
    fireEvent.change(within(footer).getByRole('combobox', { name: 'table.perPageLabel' }), { target: { value: '50' } })
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    expect(footer).toHaveTextContent('2 / 3')
    expect(rows()).toBe(50)
    fireEvent.click(within(table).getByRole('button', { name: 'common.certificates' }))
    expect(footer).toHaveTextContent('1 / 3')
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    expect(footer).toHaveTextContent('2 / 3')
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'smoke' } })
    await waitFor(() => expect(footer).toHaveTextContent('cas.range:120'))
    expect(footer).toHaveTextContent('1 / 3')
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'issuing' } })
    await waitFor(() => expect(footer).toHaveTextContent('cas.range:8'))
    expect(rows()).toBe(8)
    expect(within(footer).queryByRole('button', { name: 'table.nextPage' })).toBeNull()
  })
})

describe('CAsPage: states', () => {
  it('offers to create the first authority when there is none', async () => {
    getAll.mockResolvedValue({ data: [] })
    renderAt()
    await loaded()
    expect(screen.getByText('cas.empty.title')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'cas.viewsLabel' })).toBeNull()
    fireEvent.click(within(document.getElementById('empty-cas')).getByRole('button', { name: 'common.createCA' }))
    expect(screen.getByText('create-modal')).toBeInTheDocument()
  })

  it('says why the authorities could not be read, and reads again', async () => {
    getAll.mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 500 }))
    renderAt()
    await loaded()
    const banner = document.getElementById('load-error-cas')
    expect(banner).toHaveAttribute('role', 'alert')
    expect(within(banner).getByText('cas.loadFailed')).toBeInTheDocument()
    fireEvent.click(within(banner).getByRole('button', { name: 'table.retry' }))
    await waitFor(() => expect(screen.getByRole('tree')).toBeInTheDocument())
  })
})

describe('CAsPage: functions in reach', () => {
  it('creates and imports from the page head, and opens what it made', async () => {
    renderAt()
    await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'common.createCA' }))
    fireEvent.click(screen.getByText('create-modal'))
    await waitFor(() => expect(where()).toBe('/cas?authority=42'))
    importResult = { imported_ids: { cas: [7], certificates: [], csrs: [] } }
    fireEvent.click(screen.getByRole('button', { name: 'common.import' }))
    fireEvent.click(screen.getByText('import-modal'))
    await waitFor(() => expect(where()).toBe('/cas?authority=7'))
  })

  it('opens a single imported certificate in its inspector, and nothing for two objects', async () => {
    renderAt()
    await loaded()
    importResult = { imported_ids: { cas: [], certificates: [9], csrs: [] } }
    fireEvent.click(screen.getByRole('button', { name: 'common.import' }))
    fireEvent.click(screen.getByText('import-modal'))
    expect(stable.openEntity).toHaveBeenCalledWith('certificate', 9)
    importResult = { imported_ids: { cas: [7], certificates: [9], csrs: [] } }
    fireEvent.click(screen.getByRole('button', { name: 'common.import' }))
    fireEvent.click(screen.getByText('import-modal'))
    expect(stable.openEntity).toHaveBeenCalledTimes(1)
  })

  it('suspends Import with the other writes', async () => {
    renderAt()
    await loaded()
    expect(blockedWhileSuspended(screen.getByRole('button', { name: 'common.import' }))).toBe(true)
  })

  it('offers neither to a reader', async () => {
    mockCanWrite = false
    renderAt()
    await loaded()
    expect(screen.queryByRole('button', { name: 'common.createCA' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'common.import' })).toBeNull()
    expect(getChainRepairStatus).not.toHaveBeenCalled()
  })

  it('keeps on a phone, under « ⋯ », what the mockup hides of the head', async () => {
    mobile.isMobile = true
    renderAt()
    await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'cas.pageActions' }))
    const menu = screen.getByTestId('cas-page-menu')
    fireEvent.click(within(menu).getByRole('button', { name: 'common.import' }))
    expect(screen.getByText('import-modal')).toBeInTheDocument()
  })

  it('keeps chain repair behind a button while every chain is linked', async () => {
    renderAt()
    await loaded()
    const button = await screen.findByRole('button', { name: 'dashboard.chainRepair' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('button', { name: 'dashboard.chainRepairRun' })).toBeNull()
    fireEvent.click(button)
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.chainRepairRun' }))
    await waitFor(() => expect(runChainRepair).toHaveBeenCalledTimes(1))
  })

  it('shows chain repair unasked when an authority is orphaned', async () => {
    getChainRepairStatus.mockResolvedValue({ data: { stats: { total_cas: 6, orphan_cas: 2 }, task: {} } })
    renderAt()
    await loaded()
    expect(await screen.findByRole('button', { name: 'dashboard.chainRepairRun' })).toBeInTheDocument()
    expect(screen.getByText(/dashboard\.chainRepairOrphans/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'dashboard.chainRepair' })).toBeNull()
  })

  it('shows chain repair unasked when a damaged record waits for its repair', async () => {
    getCrossFindings.mockResolvedValue({ data: { findings: [{ kind: 'shadowed_root', ca_id: 4, ca_name: 'A', root_name: 'B', actions: [] }] } })
    renderAt()
    await loaded()
    expect(await screen.findByText('crossCerts.findings:1')).toBeInTheDocument()
  })
})
