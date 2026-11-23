/**
 * CSRsPage as the mockup's csr module: the two server lists as state chips, the list's words, the
 * dock and its tabs, the read error, the empty and no-match blocks, the server sort, the rights.
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { renderAtUrl } from '../../test/dockUrl'
import { sortKeys, sortedHeaders, absorbing } from '../../test/listColumns'

beforeAll(() => {
  global.ResizeObserver = global.ResizeObserver || class { observe() {} unobserve() {} disconnect() {} }
})

vi.mock('react-i18next', async () => {
  const { enI18n } = await import('../../test/enT')
  return { useTranslation: () => enI18n, Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }
})

const perms = vi.hoisted(() => ({ write: true, del: true, audit: true }))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn(),
}))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false }),
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../hooks', async () => {
  const common = await vi.importActual('../../hooks/useCommon')
  return {
    useModals: common.useModals,
    usePermission: () => ({
      canWrite: () => perms.write, canDelete: () => perms.del, canRead: () => true,
      hasPermission: (p) => (p === 'read:audit' ? perms.audit : true),
    }),
  }
})

const getAll = vi.fn()
const getHistory = vi.fn()
vi.mock('../../services', () => ({
  csrsService: {
    getAll: (...a) => getAll(...a),
    getHistory: (...a) => getHistory(...a),
    getById: (id) => Promise.resolve({ data: { id } }),
    download: vi.fn(), downloadKey: vi.fn(), delete: vi.fn(),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  mscaService: { getEnabled: vi.fn().mockResolvedValue({ data: [] }), getPendingRequests: vi.fn().mockResolvedValue({ data: [] }) },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  certificatesService: { export: vi.fn() },
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import CSRsPage from '../CSRsPage'

const PENDING = {
  id: 139, cn: 'e2e-appr.example.test', common_name: 'e2e-appr.example.test', requester: 'admin', key_type: 'EC secp256r1',
  created_at: '2026-07-11T09:43:43Z', status: 'Pending', has_private_key: true, descr: 'CSR for e2e-appr', pem: '-----BEGIN CERTIFICATE REQUEST-----',
}
const SIGNED = {
  id: 298, cn: 'smartcard.example.test', common_name: 'smartcard.example.test', requester: 'system', key_type: 'RSA 2048',
  created_at: '2026-10-12T15:30:29Z', status: 'Signed', signed_by: 'Smoke CA', signed_at: '2026-10-12T15:15:29Z',
  san_combined: 'Email:rc@example.com', valid_to: '2026-11-11T15:30:29Z',
}
const page = (rows, total = rows.length) => Promise.resolve({ data: rows, meta: { total } })
const renderAt = (url = '/csrs') => render(<MemoryRouter initialEntries={[url]}><CSRsPage /></MemoryRouter>)

beforeEach(() => {
  perms.write = true; perms.del = true; perms.audit = true
  getAll.mockReset().mockImplementation((p) => page(p.per_page === 1 ? [PENDING] : [PENDING], 6))
  getHistory.mockReset().mockImplementation(() => page([SIGNED], 38))
})

describe('CSRs list', () => {
  it('draws the module head, the two lists as counted chips and the rows in the mockup\'s columns', async () => {
    const { container } = renderAt()
    const row = (await screen.findByRole('button', { name: 'CSR-139' })).closest('tr')
    expect(container.querySelector('.atl h1#main-title')).toHaveTextContent('Certificate Signing Requests')
    expect(container.querySelector('.page-head .total')).toHaveTextContent('44 requests')
    const chips = [...container.querySelectorAll('.views .view-btn')].map((b) => b.textContent)
    expect(chips).toEqual(['Pending6', 'Signed38'])
    expect([...container.querySelectorAll('thead th')].map((th) => th.textContent).slice(0, 6)).toEqual(['Name', 'Subject', 'Requester', 'Key', 'Submitted', 'State'])
    expect(within(row).getByText('e2e-appr.example.test')).toBeTruthy()
    expect(within(row).getByText('ECDSA P-256')).toBeTruthy()
    expect(within(row).getByText('admin')).toBeTruthy()
    expect(row.querySelector('.badge.warn')).toHaveTextContent('Pending')
    expect(container.querySelector('.table-footer')).toHaveTextContent('1–6 of 6 requests')
  })

  it('reads the signed list from its chip', async () => {
    const { container } = renderAt()
    await screen.findByRole('button', { name: 'CSR-139' })
    fireEvent.click(container.querySelector('[data-status="history"]'))
    const row = (await screen.findByRole('button', { name: 'CSR-298' })).closest('tr')
    expect(row.querySelector('.badge.good')).toHaveTextContent('Signed')
    expect(getHistory).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, per_page: 25 }))
  })

  it('opens on the newest submitted first, asked of the server, every column but the state sorting', async () => {
    const { container } = renderAt()
    await screen.findByRole('button', { name: 'CSR-139' })
    expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'created_at', sort_order: 'desc', page: 1 }))
    expect(sortedHeaders(container)).toEqual([['Submitted', 'descending']])
    expect(sortKeys(container)).toEqual(['id', 'cn', 'requester', 'key_type', 'created_at'])
    expect(absorbing(container)).toEqual(['Subject'])
  })

  it('sorts on the server in two states, back to page one, kept in the address', async () => {
    getAll.mockImplementation((p) => page([PENDING], p.per_page === 1 ? 1 : 60))
    const at = renderAtUrl(<CSRsPage />, '/csrs')
    await screen.findByRole('button', { name: 'CSR-139' })
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await waitFor(() => expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })))
    const subject = () => at.container.querySelector('[data-sort="cn"]')
    fireEvent.click(subject())
    await waitFor(() => expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'cn', sort_order: 'asc', page: 1 })))
    expect(at.where()).toBe('/csrs?sort=cn&order=asc')
    fireEvent.click(subject())
    await waitFor(() => expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'cn', sort_order: 'desc' })))
    fireEvent.click(subject())
    await waitFor(() => expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'cn', sort_order: 'asc' })))
    fireEvent.click(at.container.querySelector('[data-sort="requester"]'))
    await waitFor(() => expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'requester', sort_order: 'asc' })))
    // The other tab starts from its own default: the sort is the tab's
    fireEvent.click(at.container.querySelector('[data-status="history"]'))
    await waitFor(() => expect(getHistory).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'created_at', sort_order: 'desc' })))
    expect(at.where()).toBe('/csrs?tab=history')
  })

  it('reads the sort of a link, and falls back on the default for an unknown key', async () => {
    const at = renderAtUrl(<CSRsPage />, '/csrs?sort=key_type&order=desc')
    await screen.findByRole('button', { name: 'CSR-139' })
    expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'key_type', sort_order: 'desc' }))
    expect(sortedHeaders(at.container)).toEqual([['Key', 'descending']])
    at.unmount()
    renderAtUrl(<CSRsPage />, '/csrs?sort=nope&order=asc')
    await screen.findByRole('button', { name: 'CSR-139' })
    expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'created_at', sort_order: 'desc' }))
  })

  it('offers Import and Generate CSR only with write:csrs', async () => {
    perms.write = false
    const { container } = renderAt()
    await screen.findByRole('button', { name: 'CSR-139' })
    expect(container.querySelector('.page-head .actions')).toBeNull()
  })
})

describe('CSRs states', () => {
  it('says why a read failed, retries it and links the journal for who may read it', async () => {
    getAll.mockReset().mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }))
    const { container } = renderAt()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Failed to load CSRs')
    expect(within(alert).getByRole('link')).toHaveAttribute('href', '/audit')
    getAll.mockImplementation(() => page([PENDING]))
    fireEvent.click(container.querySelector('#retry-csrs'))
    expect(await screen.findByRole('button', { name: 'CSR-139' })).toBeTruthy()
  })

  it('gives no journal link without read:audit', async () => {
    perms.audit = false
    getAll.mockReset().mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }))
    renderAt()
    const alert = await screen.findByRole('alert')
    expect(within(alert).queryByRole('link')).toBeNull()
  })

  it('shows the empty pending list with Import CSR, only for who may write', async () => {
    getAll.mockReset().mockImplementation(() => page([]))
    const { container, unmount } = renderAt()
    const empty = await waitFor(() => { const e = container.querySelector('#empty-csrs'); expect(e).toBeTruthy(); return e })
    expect(within(empty).getByRole('button', { name: /Import CSR/ })).toBeTruthy()
    unmount()
    perms.write = false
    const again = renderAt()
    const block = await waitFor(() => { const e = again.container.querySelector('#empty-csrs'); expect(e).toBeTruthy(); return e })
    expect(within(block).queryByRole('button')).toBeNull()
  })

  it('says nothing matches a search, and clears it', async () => {
    const { container } = renderAt()
    await screen.findByRole('button', { name: 'CSR-139' })
    getAll.mockImplementation((p) => page(p.search ? [] : [PENDING]))
    fireEvent.change(container.querySelector('#csr-search'), { target: { value: 'nothing' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Clear all filters' }, { timeout: 2000 }))
    expect(await screen.findByRole('button', { name: 'CSR-139' })).toBeTruthy()
    expect(container.querySelector('#csr-search').value).toBe('')
  })
})

describe('CSR dock', () => {
  it('opens a pending request with its properties, details and PEM tabs', async () => {
    const { container } = renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'CSR-139' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    expect(within(dock).getByRole('heading', { name: 'CSR-139' })).toBeTruthy()
    expect([...dock.querySelectorAll('[role=tab]')].map((x) => x.textContent)).toEqual(['Overview', 'Details', 'PEM'])
    expect(dock.querySelector('.summary')).toHaveTextContent('CSR for e2e-appr')
    expect(within(dock).getByRole('button', { name: /Sign/ })).toBeTruthy()
    fireEvent.click(within(dock).getByRole('tab', { name: 'PEM' }))
    expect(dock.querySelector('.code-preview')).toHaveTextContent('BEGIN CERTIFICATE REQUEST')
  })

  it('opens a signed request with its signer, its names and no PEM tab', async () => {
    const { container } = renderAt('/csrs?tab=history')
    fireEvent.click(await screen.findByRole('button', { name: 'CSR-298' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    expect([...dock.querySelectorAll('[role=tab]')].map((x) => x.textContent)).toEqual(['Overview', 'Details'])
    expect(dock.querySelector('.summary').textContent).toMatch(/^Signed by Smoke CA on /)
    fireEvent.click(within(dock).getByRole('tab', { name: 'Details' }))
    expect(within(dock).getByText('Email:rc@example.com')).toBeTruthy()
    expect(within(dock).queryByRole('button', { name: /^Sign$/ })).toBeNull()
  })

  it('withholds Sign and the write actions of the menu without write:csrs', async () => {
    perms.write = false
    const { container } = renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'CSR-139' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    expect(within(dock).queryByRole('button', { name: 'Sign' })).toBeNull()
    fireEvent.click(within(dock).getByRole('button', { name: /Other actions/ }))
    const menu = await screen.findByTestId('inspector-actions-dialog')
    expect(within(menu).getByRole('heading', { name: 'Request actions' })).toBeTruthy()
    expect(within(menu).queryByRole('button', { name: /Re-key/ })).toBeNull()
    expect(within(menu).queryByRole('button', { name: /Upload Key/ })).toBeNull()
    expect(within(menu).getByRole('button', { name: /Delete/ })).toBeTruthy()
  })
})

describe('CSR dock in the URL', () => {
  let where
  function Where() { const l = useLocation(); where = l.pathname + l.search; return null }
  const at = (url) => render(<MemoryRouter initialEntries={[url]}><CSRsPage /><Where /></MemoryRouter>)
  const dockIn = (container) => waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })

  it('reopens the request and its section a link names (a reload)', async () => {
    const { container } = at('/csrs?item=139&section=pem')
    const dock = await dockIn(container)
    expect(within(dock).getByRole('tab', { name: 'PEM' })).toHaveAttribute('aria-selected', 'true')
    expect(within(dock).getByRole('heading', { name: 'CSR-139' })).toBeTruthy()
  })

  it('opens the request of a palette result (?selected=), even off the list\'s page', async () => {
    const { container } = at('/csrs?selected=777')
    const dock = await dockIn(container)
    expect(within(dock).getByRole('heading', { name: 'CSR-777' })).toBeTruthy()
  })

  it('writes the open request and its section, and the chip change closes it', async () => {
    const { container } = at('/csrs')
    fireEvent.click(await screen.findByRole('button', { name: 'CSR-139' }))
    expect(where).toBe('/csrs?item=139')
    const dock = await dockIn(container)
    fireEvent.click(within(dock).getByRole('tab', { name: 'Details' }))
    expect(where).toBe('/csrs?item=139&section=details')
    fireEvent.click(container.querySelector('[data-status="history"]'))
    await waitFor(() => expect(where).toBe('/csrs?tab=history'))
    expect(container.querySelector('#inspector')).toBeNull()
  })
})
