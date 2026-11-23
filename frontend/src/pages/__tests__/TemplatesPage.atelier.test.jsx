/**
 * TemplatesPage as the mockup's templates module: the state chips, the columns and their words,
 * the client sort, the dock's tabs, the read error and the rights.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { renderAtUrl } from '../../test/dockUrl'
import { sortKeys, sortedHeaders, absorbing, numberHeads } from '../../test/listColumns'

vi.mock('react-i18next', async () => {
  const { enI18n } = await import('../../test/enT')
  return { useTranslation: () => enI18n, Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }
})

const perms = vi.hoisted(() => ({ write: true }))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn(),
}))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false }),
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  return {
    usePersistedState: persisted.usePersistedState,
    useCRUDPage: crud.useCRUDPage,
    usePermission: () => ({ canWrite: () => perms.write, canDelete: () => true, canRead: () => true, hasPermission: () => true }),
  }
})
const getAll = vi.fn()
vi.mock('../../services', () => ({
  templatesService: { getAll: (...a) => getAll(...a), update: vi.fn(), duplicate: vi.fn(), delete: vi.fn(), export: vi.fn() },
}))
vi.mock('../../services/eku.service', () => ({ ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) } }))

import TemplatesPage from '../TemplatesPage'

const TLS = {
  id: 1, name: 'Web Server', is_system: true, is_active: true, validity_days: 397, key_type: 'EC-P256', usage_count: 1, digest: 'sha256',
  description: 'TLS servers', dn_template: { CN: '{hostname}', O: 'Example' }, ad_derived_subject: true,
  extensions_template: { key_usage: ['digitalSignature'], extended_key_usage: ['serverAuth'], san_types: ['dns'] },
  pinned_subject_fields: { O: 'Example' }, allowed_ad_group: 'PKI-Users',
}
const OLD = { id: 2, name: 'Archive', is_system: false, is_active: false, validity_days: 90, key_type: 'RSA-3072', usage_count: 0 }
const renderPage = () => render(<MemoryRouter><TemplatesPage /></MemoryRouter>)

beforeEach(() => {
  window.localStorage.clear()
  perms.write = true
  getAll.mockReset().mockResolvedValue({ data: [TLS, OLD] })
})

describe('Templates list', () => {
  it('counts the states present, shows the mockup\'s columns and filters by state', async () => {
    const { container } = renderPage()
    const row = (await screen.findByRole('button', { name: 'Web Server' })).closest('tr')
    expect(container.querySelector('.page-head .total')).toHaveTextContent('2 templates')
    expect([...container.querySelectorAll('.views .view-btn')].map((b) => b.textContent)).toEqual(['All2', 'Active1', 'Inactive1'])
    expect([...container.querySelectorAll('thead th')].map((th) => th.textContent).slice(0, 6)).toEqual(['Name', 'Source', 'Validity', 'Key', 'Uses', 'State'])
    expect(container.querySelector('[data-sort="key"]')).toHaveAttribute('aria-label', 'Default key')
    expect(row).toHaveTextContent('397 d')
    expect(row).toHaveTextContent('ECDSA P-256')
    expect(row).toHaveTextContent('1 certificate')
    fireEvent.click(container.querySelector('[data-status="inactive"]'))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Web Server' })).toBeNull())
    expect(screen.getByRole('button', { name: 'Archive' }).closest('tr').querySelector('.badge.muted')).toHaveTextContent('Inactive')
    expect(container.querySelector('.table-footer')).toHaveTextContent('1 of 2 templates')
  })

  it('sorts by name, then by validity, both ways', async () => {
    const { container } = renderPage()
    await screen.findByRole('button', { name: 'Web Server' })
    const names = () => [...container.querySelectorAll('tbody .entity-name')].map((b) => b.textContent)
    expect(names()).toEqual(['Archive', 'Web Server'])
    fireEvent.click(container.querySelector('[data-sort="validity_days"]'))
    expect(names()).toEqual(['Archive', 'Web Server'])
    fireEvent.click(container.querySelector('[data-sort="validity_days"]'))
    expect(names()).toEqual(['Web Server', 'Archive'])
  })

  it('sorts every column and pages a long list by 25', async () => {
    const many = Array.from({ length: 28 }, (_, i) => ({ ...OLD, id: 10 + i, name: `Bulk ${String(i + 1).padStart(2, '0')}`, usage_count: i }))
    getAll.mockReset().mockResolvedValue({ data: [TLS, OLD, ...many] })
    const { container } = renderPage()
    await screen.findByRole('button', { name: 'Archive' })
    const footer = container.querySelector('.table-footer')
    const names = () => [...container.querySelectorAll('tbody .entity-name')].map((b) => b.textContent)
    expect(names()).toHaveLength(25)
    expect(footer).toHaveTextContent('1–25 of 30 templates')
    fireEvent.click(within(footer).getByRole('button', { name: 'Next page' }))
    expect(names()).toEqual(['Bulk 25', 'Bulk 26', 'Bulk 27', 'Bulk 28', 'Web Server'])
    fireEvent.click(container.querySelector('[data-sort="usage_count"]'))
    fireEvent.click(container.querySelector('[data-sort="usage_count"]'))
    expect(footer).toHaveTextContent('1–25 of 30 templates')
    expect(names()[0]).toBe('Bulk 28')
    for (const key of ['source', 'key', 'state']) {
      fireEvent.click(container.querySelector(`[data-sort="${key}"]`))
      expect(container.querySelector(`[data-sort="${key}"]`).closest('th')).toHaveAttribute('aria-sort', 'ascending')
    }
    expect(names()[0]).toBe('Web Server')
  })

  it('opens on the name ascending, the name taking the room left, the counts at the right', async () => {
    const { container } = renderPage()
    await screen.findByRole('button', { name: 'Web Server' })
    expect(sortedHeaders(container)).toEqual([['Name', 'ascending']])
    expect(sortKeys(container)).toEqual(['name', 'source', 'validity_days', 'key', 'usage_count', 'state'])
    expect(absorbing(container)).toEqual(['Name'])
    expect(numberHeads(container)).toEqual(['Validity', 'Uses'])
  })

  it('keeps another sort in the address and reads it back', async () => {
    const at = renderAtUrl(<TemplatesPage />, '/templates')
    await screen.findByRole('button', { name: 'Web Server' })
    fireEvent.click(at.container.querySelector('[data-sort="validity_days"]'))
    expect(at.where()).toBe('/templates?sort=validity_days&order=asc')
    at.unmount()
    const again = renderAtUrl(<TemplatesPage />, '/templates?sort=validity_days&order=desc')
    await screen.findByRole('button', { name: 'Web Server' })
    expect(sortedHeaders(again.container)).toEqual([['Validity', 'descending']])
    expect(again.container.querySelector('tbody .entity-name')).toHaveTextContent('Web Server')
  })

  it('offers Import and Create Template only with write:templates', async () => {
    perms.write = false
    const { container } = renderPage()
    await screen.findByRole('button', { name: 'Web Server' })
    expect(container.querySelector('.page-head .actions')).toBeNull()
  })

  it('says why the read failed and retries it', async () => {
    getAll.mockReset().mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 503 })).mockResolvedValue({ data: [TLS] })
    const { container } = renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load templates')
    fireEvent.click(container.querySelector('#retry-templates'))
    expect(await screen.findByRole('button', { name: 'Web Server' })).toBeTruthy()
  })
})

describe('Template dock', () => {
  it('shows the overview, then the subject, extensions and enrollment of the template', async () => {
    const { container } = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Web Server' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    expect([...dock.querySelectorAll('[role=tab]')].map((x) => x.textContent)).toEqual(['Overview', 'Subject', 'Extensions', 'Enrollment'])
    expect(dock.querySelector('.summary')).toHaveTextContent('TLS servers')
    expect(dock).toHaveTextContent('AD, ACL, Pinned')
    fireEvent.click(within(dock).getByRole('tab', { name: 'Subject' }))
    expect(dock).toHaveTextContent('{hostname}')
    fireEvent.click(within(dock).getByRole('tab', { name: 'Extensions' }))
    expect(within(dock).getByText('serverAuth')).toBeTruthy()
    fireEvent.click(within(dock).getByRole('tab', { name: 'Enrollment' }))
    expect(dock).toHaveTextContent('PKI-Users')
    expect(dock).toHaveTextContent('O=Example')
  })

  it('types its facts: switches and state in pills, the fields it leaves unset in grey', async () => {
    const { container } = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    const row = (term) => within(dock).getByText(term, { selector: 'dt' }).closest('.row')
    expect(dock.querySelector('dl.props')).toBeNull()
    expect(row('State').querySelector('dd.v .badge.muted')).toHaveTextContent('Inactive')
    expect(row('Digest').querySelector('dd.absent')).toHaveTextContent('—')
    fireEvent.click(within(dock).getByRole('tab', { name: 'Subject' }))
    expect(row('Org Unit').querySelector('dd.absent')).toHaveTextContent('—')
    expect(row('Build subject from Active Directory').querySelector('dd.v .badge.muted')).toHaveTextContent('Disabled')
    expect(row('Common name pattern (Windows enrollment)').querySelector('dd.absent')).toBeTruthy()
    fireEvent.click(within(dock).getByRole('tab', { name: 'Enrollment' }))
    expect(row('Allow autoenrollment').querySelector('dd.v .badge.muted')).toHaveTextContent('Disabled')
    expect(row('Pinned subject fields').querySelector('dd.absent')).toHaveTextContent('None pinned')
  })
})

describe('Template words', () => {
  it('names the digest SHA-256 as the certificates do, in the panel and in the form', async () => {
    const { container } = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Web Server' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    expect(within(dock).getByText('Digest', { selector: 'dt' }).closest('.row')).toHaveTextContent('SHA-256')
    fireEvent.click(screen.getByRole('button', { name: 'Create Template' }))
    const digest = await screen.findByLabelText('Digest')
    expect([...digest.options].map((o) => o.textContent)).toEqual(['SHA-256', 'SHA-384', 'SHA-512'])
  })
})

describe('Template dock in the URL', () => {
  let where
  function Where() { const l = useLocation(); where = l.pathname + l.search; return null }
  const at = (url) => render(<MemoryRouter initialEntries={[url]}><TemplatesPage /><Where /></MemoryRouter>)

  it('opens the template and section a link names (a reload)', async () => {
    at('/templates?item=1&section=enrollment')
    const dock = await screen.findByRole('complementary', { name: /Templates/ })
    expect(within(dock).getByRole('tab', { name: 'Enrollment' })).toHaveAttribute('aria-selected', 'true')
    expect(dock).toHaveTextContent('PKI-Users')
  })

  it('opens the template of a palette result (?selected=)', async () => {
    at('/templates?selected=2')
    const dock = await screen.findByRole('complementary', { name: /Templates/ })
    expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('Archive')
  })

  it('writes the open template and its section into the URL', async () => {
    at('/templates')
    fireEvent.click(await screen.findByRole('button', { name: 'Web Server' }))
    expect(where).toBe('/templates?item=1')
    const dock = screen.getByRole('complementary', { name: /Templates/ })
    fireEvent.click(within(dock).getByRole('tab', { name: 'Enrollment' }))
    expect(where).toBe('/templates?item=1&section=enrollment')
  })
})
