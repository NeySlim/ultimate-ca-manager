/**
 * CAsPage on the list template: page head, state tabs with counters kept in the URL,
 * the tree as the default view, the two other views, the search, chain repair shown only
 * when it has something to say, and every page function in reach.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
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
  openEntity: () => {},
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

let mockCanWrite = true
let mockOpened = []
const mobile = { isMobile: false, isDesktop: true, isTablet: false, isLargeScreen: true, screenWidth: 1600 }
const inspector = () => ({ openEntity: stable.openEntity, opened: mockOpened, activeKey: mockOpened[0]?.key })
vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => mobile,
  useInspector: () => inspector(),
}))
vi.mock('../../contexts/InspectorContext', () => ({ useInspector: () => inspector() }))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => mobile }))

vi.mock('../../hooks', async () => {
  const modals = await vi.importActual('../../hooks/useCommon')
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    useModals: modals.useModals,
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({
      canWrite: () => mockCanWrite, canDelete: () => mockCanWrite, hasPermission: () => true, canRead: () => true,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

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
}))
const downloadExport = vi.fn().mockResolvedValue(null)
vi.mock('../../lib/exportDownload', () => ({ downloadExport: (...a) => downloadExport(...a) }))

vi.mock('../../components/cas/ManageTemplatePinsModal', () => ({ ManageTemplatePinsModal: () => null }))
vi.mock('../../components/cas/RestorePrimaryModal', () => ({ RestorePrimaryModal: () => null }))
vi.mock('../cas/CADetailsPanel', () => ({ CADetailsPanel: () => null }))
vi.mock('../cas/CreateCAModal', () => ({ CreateCAModal: ({ open }) => (open ? <div>create-modal</div> : null) }))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: ({ isOpen }) => (isOpen ? <div>import-modal</div> : null) }))

import CAsPage from '../CAsPage'

const Where = () => <output data-testid="where">{useLocation().search}</output>
const renderAt = (url = '/cas') => render(<MemoryRouter initialEntries={[url]}><CAsPage /><Where /></MemoryRouter>)
const tab = (id) => screen.getByRole('tab', { name: new RegExp(`^cas\\.views\\.${id}`) })
const tabIds = () => screen.getAllByRole('tab').map((el) => el.id.split('-tab-')[1])
const treeNames = () => screen.getAllByRole('treeitem').map((el) => document.getElementById(el.getAttribute('aria-labelledby')).textContent)
const loaded = () => waitFor(() => expect(screen.queryByRole('tree') || screen.queryByRole('table') || screen.queryByText('common.noCA')).not.toBeNull())
const linked = { stats: { total_cas: 6, total_certs: 32, orphan_cas: 0 }, task: {} }

beforeEach(() => {
  window.localStorage.clear()
  mockCanWrite = true
  mockOpened = []
  for (const fn of [getAll, getChainRepairStatus, getCrossFindings, getCrossCertificates, runChainRepair, exportCA]) fn.mockReset()
  getAll.mockResolvedValue({ data: smallHierarchy() })
  getChainRepairStatus.mockResolvedValue({ data: linked })
  getCrossFindings.mockResolvedValue({ data: { findings: [] } })
  getCrossCertificates.mockResolvedValue({ data: [] })
  runChainRepair.mockResolvedValue({ data: linked })
  downloadExport.mockClear()
})

describe('CAsPage: page head and tabs', () => {
  it('heads the page with its title, total in words and intent, and no stat tiles', async () => {
    renderAt()
    await loaded()
    expect(screen.getByRole('heading', { level: 1, name: 'common.cas' })).toBeInTheDocument()
    expect(screen.getByText('cas.total:6')).toBeInTheDocument()
    expect(screen.getByText('cas.intent')).toBeInTheDocument()
    // The tiles of the former stats bar and its filter dropdowns are gone
    expect(screen.queryByText('common.intermediateCA')).toBeNull()
    expect(screen.queryByText('common.allTypes')).toBeNull()
    expect(screen.queryByText('common.allStatus')).toBeNull()
  })

  it('counts every authority in tabs, with offline only when there is one', async () => {
    renderAt()
    await loaded()
    expect(tabIds()).toEqual(['all', 'roots', 'intermediates', 'expired', 'offline'])
    expect(tab('all')).toHaveTextContent(/^cas\.views\.all6$/)
    expect(tab('roots')).toHaveTextContent(/^cas\.views\.roots2$/)
    expect(tab('intermediates')).toHaveTextContent(/^cas\.views\.intermediates4$/)
    expect(tab('expired')).toHaveTextContent(/^cas\.views\.expired1$/)
    expect(tab('offline')).toHaveTextContent(/^cas\.views\.offline1$/)
    expect(screen.getByRole('tablist', { name: 'cas.viewsLabel' })).toBeInTheDocument()
  })

  it('leaves the offline tab out when nothing is offline', async () => {
    getAll.mockResolvedValue({ data: [ca(1), ca(2, { type: 'intermediate', parent_id: 1 })] })
    renderAt()
    await loaded()
    expect(tabIds()).toEqual(['all', 'roots', 'intermediates', 'expired'])
  })

  it('writes the tab in the URL and filters the tree with it', async () => {
    renderAt()
    await loaded()
    fireEvent.click(tab('expired'))
    expect(screen.getByTestId('where').textContent).toBe('?view=expired')
    expect(tab('expired')).toHaveAttribute('aria-selected', 'true')
    expect(treeNames()).toEqual(['Example Root', 'Services', 'Legacy'])
    fireEvent.click(tab('all'))
    expect(screen.getByTestId('where').textContent).toBe('')
  })

  it('opens on the tab of the URL and ignores one it does not know', async () => {
    renderAt('/cas?view=roots')
    await loaded()
    await waitFor(() => expect(tab('roots')).toHaveAttribute('aria-selected', 'true'))
    expect(treeNames()).toEqual(['Example Root', 'Second Root'])
    document.body.innerHTML = ''
    renderAt('/cas?view=bogus')
    await waitFor(() => expect(tab('all')).toHaveAttribute('aria-selected', 'true'))
  })
})

describe('CAsPage: views', () => {
  it('opens on the tree, folded beyond the first level', async () => {
    renderAt()
    await loaded()
    expect(treeNames()).toEqual(['Example Root', 'Identities', 'Services', 'Second Root'])
    expect(screen.getByRole('button', { name: 'cas.treeView' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('opens the tree for a stored choice of the view it replaced', async () => {
    window.localStorage.setItem('ucm-ca-view-mode', 'org')
    renderAt()
    await loaded()
    expect(screen.getByRole('tree')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'cas.treeView' })).toHaveAttribute('aria-pressed', 'true')
    expect(window.localStorage.getItem('ucm-ca-view-mode')).toBe('tree')
  })

  it('filters the tree from the search field and opens the branch found', async () => {
    renderAt()
    await loaded()
    fireEvent.change(screen.getByRole('searchbox', { name: 'cas.searchPlaceholder' }), { target: { value: 'internal' } })
    expect(treeNames()).toEqual(['Example Root', 'Services', 'Internal'])
    fireEvent.click(screen.getByRole('button', { name: 'common.clear' }))
    expect(treeNames()).toEqual(['Example Root', 'Identities', 'Services', 'Second Root'])
  })

  it('keeps the list view, on the list template: one action per row and a chevron', async () => {
    renderAt()
    await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'cas.listView' }))
    const table = await screen.findByRole('table')
    expect(table).toHaveClass('lv-table')
    expect(window.localStorage.getItem('ucm-ca-view-mode')).toBe('list')
    const row = within(table).getByRole('button', { name: 'Services' }).closest('tr')
    expect(within(row).getAllByRole('button').map((b) => b.getAttribute('aria-label')).filter(Boolean)).toHaveLength(2)
    fireEvent.click(within(row).getByTitle('cas.downloadCertificate'))
    await waitFor(() => expect(exportCA).toHaveBeenCalledWith(2, 'pem'))
    // The tab and the search apply to the list as to the tree
    fireEvent.click(tab('roots'))
    expect(within(screen.getByRole('table')).queryByRole('button', { name: 'Services' })).toBeNull()
    expect(within(screen.getByRole('table')).getByText('Second Root')).toBeInTheDocument()
  })

  it('keeps the columns view', async () => {
    renderAt()
    await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'cas.columnsView' }))
    expect(screen.queryByRole('tree')).toBeNull()
    expect(screen.getAllByText('Example Root').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Services').length).toBeGreaterThan(0)
  })

  it('opens the detail of a node and marks the authority the dock shows', async () => {
    const spy = vi.spyOn(stable, 'openEntity')
    mockOpened = [{ key: 'ca:5', type: 'ca', entityId: 5 }]
    renderAt()
    await loaded()
    expect(screen.getByRole('treeitem', { name: 'Identities' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(screen.getByRole('treeitem', { name: 'Services' }), { key: 'Enter' })
    expect(spy).toHaveBeenCalledWith('ca', 2)
    spy.mockRestore()
  })

  it('stays readable with 139 authorities: a handful of cards, the idle roots in one group', async () => {
    getAll.mockResolvedValue({ data: largeInstallation() })
    const { container } = renderAt()
    await loaded()
    expect(screen.getByText('cas.total:139')).toBeInTheDocument()
    expect(tab('roots')).toHaveTextContent(/131$/)
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

describe('CAsPage: functions in reach', () => {
  it('creates and imports from the page head', async () => {
    renderAt()
    await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'common.create' }))
    expect(screen.getByText('create-modal')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'common.import' }))
    expect(screen.getByText('import-modal')).toBeInTheDocument()
  })

  it('offers neither to a reader', async () => {
    mockCanWrite = false
    renderAt()
    await loaded()
    expect(screen.queryByRole('button', { name: 'common.create' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'common.import' })).toBeNull()
    expect(getChainRepairStatus).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'dashboard.chainRepair' })).toBeNull()
  })

  it('keeps chain repair behind a button while every chain is linked', async () => {
    renderAt()
    await loaded()
    const button = await screen.findByRole('button', { name: 'dashboard.chainRepair' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTitle('dashboard.chainRepairRun')).toBeNull()
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(screen.getByTitle('dashboard.chainRepairRun'))
    await waitFor(() => expect(runChainRepair).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.chainRepair' }))
    expect(screen.queryByTitle('dashboard.chainRepairRun')).toBeNull()
  })

  it('shows chain repair unasked when an authority is orphaned', async () => {
    getChainRepairStatus.mockResolvedValue({ data: { stats: { total_cas: 6, orphan_cas: 2 }, task: {} } })
    renderAt()
    await loaded()
    expect(await screen.findByTitle('dashboard.chainRepairRun')).toBeInTheDocument()
    expect(screen.getByText(/dashboard\.chainRepairOrphans/)).toBeInTheDocument()
    // Nothing to toggle: the strip is there
    expect(screen.queryByRole('button', { name: 'dashboard.chainRepair' })).toBeNull()
  })

  it('shows chain repair unasked when a damaged record waits for its repair', async () => {
    getCrossFindings.mockResolvedValue({ data: { findings: [{ kind: 'shadowed_root', ca_id: 4, ca_name: 'A', root_name: 'B', actions: [] }] } })
    renderAt()
    await loaded()
    expect(await screen.findByText('crossCerts.findings:1')).toBeInTheDocument()
  })

  it('offers to create the first authority when there is none', async () => {
    getAll.mockResolvedValue({ data: [] })
    renderAt()
    await waitFor(() => expect(screen.getByText('common.noCA')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /common\.createCA/ }))
    expect(screen.getByText('create-modal')).toBeInTheDocument()
  })
})
