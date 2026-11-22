/**
 * TrustStorePage as the mockup's truststore module: the usage read from the description, the type,
 * the state chips and the type filter, the dock's tabs and actions, the head actions and the rights.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', async () => {
  const { enI18n } = await import('../../test/enT')
  return { useTranslation: () => enI18n, Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }
})

const perms = vi.hoisted(() => ({ write: true, del: true }))
const mobile = vi.hoisted(() => ({ isMobile: false }))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn().mockResolvedValue(true), showPrompt: vi.fn(),
}))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => mobile,
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => mobile }))
vi.mock('../../hooks', async () => {
  const modals = await vi.importActual('../../hooks/useCommon')
  const { useState } = await vi.importActual('react')
  return {
    useModals: modals.useModals,
    usePersistedState: (_key, initial) => useState(initial),
    usePermission: () => ({ canWrite: () => perms.write, canDelete: () => perms.del, canRead: () => true, hasPermission: () => true }),
  }
})
const getAll = vi.fn()
const del = vi.fn()
const managed = vi.hoisted(() => ({ cas: [] }))
// The anchors a test lists instead of ROWS, read back by the dock
const listed = vi.hoisted(() => ({ rows: null }))
vi.mock('../../services', () => ({
  truststoreService: {
    getAll: (...a) => getAll(...a),
    getById: (id) => Promise.resolve({ data: (listed.rows || ROWS).find((r) => r.id === id) }),
    delete: (...a) => del(...a),
  },
  casService: { getAll: () => Promise.resolve({ data: managed.cas }) },
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import { renderAtUrl } from '../../test/dockUrl'
import { sortKeys, sortedHeaders, absorbing, recordFacts } from '../../test/listColumns'
import TrustStorePage from '../TrustStorePage'

const ROWS = [
  { id: 1, name: 'Bank Root', subject: 'CN=Bank Root,O=Bank', description: 'Chain of the bank client', purpose: 'root_ca',
    not_after: '2035-03-14T00:00:00Z', notes: 'Completes the imported chain', issuer: 'CN=Bank Root,O=Bank', serial_number: '0A0B',
    key_type: 'RSA 4096', signature_algorithm: 'SHA256-RSA', fingerprint_sha256: 'AB:CD', certificate_pem: '-----BEGIN CERTIFICATE-----' },
  { id: 2, name: 'Old proxy', subject: 'CN=Old proxy', description: '', purpose: 'custom', not_after: '2020-09-01T00:00:00Z' },
]
const renderPage = () => render(<MemoryRouter><TrustStorePage /></MemoryRouter>)

beforeEach(() => {
  perms.write = true; perms.del = true
  mobile.isMobile = false
  listed.rows = null
  getAll.mockReset().mockResolvedValue({ data: ROWS })
  del.mockReset().mockResolvedValue({})
  notify.showConfirm.mockClear()
})

describe('Trust Store list', () => {
  it('opens on the name ascending, the subject taking the room left, every column sorting (T1, T4, L7)', async () => {
    const { container } = renderPage()
    await screen.findByRole('button', { name: 'Bank Root' })
    expect(sortedHeaders(container)).toEqual([['Name', 'ascending']])
    expect(sortKeys(container)).toEqual(['name', 'subject', 'usage', 'type', 'not_after', 'state'])
    expect(absorbing(container)).toEqual(['Subject'])
  })

  it('keeps another sort in the address and reads it back (T9)', async () => {
    const at = renderAtUrl(<TrustStorePage />, '/truststore')
    await screen.findByRole('button', { name: 'Bank Root' })
    fireEvent.click(at.container.querySelector('[data-sort="not_after"]'))
    expect(at.where()).toBe('/truststore?sort=not_after&order=asc')
    at.unmount()
    const again = renderAtUrl(<TrustStorePage />, '/truststore?sort=not_after&order=asc')
    await screen.findByRole('button', { name: 'Bank Root' })
    expect(sortedHeaders(again.container)).toEqual([['Expiry', 'ascending']])
    expect(again.container.querySelector('tbody .entity-name')).toHaveTextContent('Old proxy')
  })

  it('draws a phone record by priority: the expiry after its label, then the type (R5)', async () => {
    mobile.isMobile = true
    const { container } = renderPage()
    await screen.findByRole('button', { name: 'Bank Root' })
    const record = [...container.querySelectorAll('article.mobile-record')].find((r) => r.textContent.includes('Bank Root'))
    const facts = recordFacts(record)
    expect(facts[0]).toMatch(/^Expiry \S/)
    expect(facts[1]).toBe('Root CA')
    expect(facts).toHaveLength(2)
  })

  it('shows the subject, the description as the usage, the type, the expiry and the state', async () => {
    const { container } = renderPage()
    const row = (await screen.findByRole('button', { name: 'Bank Root' })).closest('tr')
    expect(container.querySelector('.page-head .total')).toHaveTextContent('2 anchors')
    expect([...container.querySelectorAll('thead th')].map((th) => th.textContent).slice(1, 7)).toEqual(['Name', 'Subject', 'Usage', 'Type', 'Expiry', 'State'])
    expect(row).toHaveTextContent('CN=Bank Root,O=Bank')
    expect(row).toHaveTextContent('Chain of the bank client')
    expect(row).toHaveTextContent('Root CA')
    expect(row.querySelector('.badge.good')).toHaveTextContent('Valid')
    expect(screen.getByRole('button', { name: 'Old proxy' }).closest('tr').querySelector('.badge.bad')).toHaveTextContent('Expired')
    expect([...container.querySelectorAll('.views .view-btn')].map((b) => b.textContent)).toEqual(['All2', 'Valid1', 'Expired1'])
  })

  it('narrows by state chip and by type', async () => {
    const { container } = renderPage()
    await screen.findByRole('button', { name: 'Bank Root' })
    fireEvent.click(container.querySelector('[data-status="expired"]'))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Bank Root' })).toBeNull())
    fireEvent.click(container.querySelector('[data-status=""]'))
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter by type' }), { target: { value: 'root_ca' } })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Old proxy' })).toBeNull())
    expect(container.querySelector('.table-footer')).toHaveTextContent('1 of 2 anchors')
  })

  it('offers sync, import and add only with write:truststore, the bundle to anyone', async () => {
    perms.write = false
    const { container } = renderPage()
    await screen.findByRole('button', { name: 'Bank Root' })
    const head = container.querySelector('.page-head .actions')
    expect([...head.querySelectorAll('button')].map((b) => b.id)).toEqual(['truststore-bundle'])
  })
})

describe('Trust anchor dock', () => {
  it('shows the overview, the technical details and the PEM, and deletes the anchor', async () => {
    const { container } = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Bank Root' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    expect([...dock.querySelectorAll('[role=tab]')].map((x) => x.textContent)).toEqual(['Overview', 'Details', 'PEM'])
    expect(dock.querySelector('.summary')).toHaveTextContent('Completes the imported chain')
    fireEvent.click(within(dock).getByRole('tab', { name: 'Details' }))
    expect(dock).toHaveTextContent('0A:0B')
    expect(dock).toHaveTextContent('RSA 4096')
    fireEvent.click(within(dock).getByRole('tab', { name: 'PEM' }))
    expect(dock.querySelector('.code-preview')).toHaveTextContent('BEGIN CERTIFICATE')
    fireEvent.click(dock.querySelector('#truststore-delete'))
    await waitFor(() => expect(del).toHaveBeenCalledWith(1))
  })

  // KV-3: the dock's rows are typed (a DN long, a serial and a digest as hex chips copied whole, a missing value absent)
  it('types the rows of the overview and the details', async () => {
    const sha256 = 'cecddc905099d8dadfc5b1d209b737cbe2c18cfb2c10c0ff0bcf0d3286fc1aa2'
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
    listed.rows = [{ ...ROWS[0], fingerprint_sha256: sha256, fingerprint_sha1: '', added_by: null }]
    getAll.mockResolvedValue({ data: listed.rows })
    const { container } = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Bank Root' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    const row = (label) => within(dock).getByText(label, { selector: 'dt' }).closest('.row')
    expect(dock.querySelector('dl.props')).toBeNull()
    expect(row('Subject')).toHaveClass('long')
    expect(row('State').querySelector('dd.v .badge')).toBeTruthy()
    fireEvent.click(within(dock).getByRole('tab', { name: 'Details' }))
    expect(dock.querySelector('dl.props')).toBeNull()
    expect(row('Issuer')).toHaveClass('long', 'wide')
    expect(row('Issuer').querySelector('.mono')).toBeNull()
    expect(row('Serial Number').querySelector('dd.v .code-value.hex')).toHaveTextContent('0A:0B')
    // the stored digest in pairs of the certificate's form, 4 lines of 8 bytes, copied whole
    const digest = row('SHA-256')
    expect(digest.querySelectorAll('dd.v .code-value.hex .line')).toHaveLength(4)
    fireEvent.click(within(digest).getByRole('button', { name: 'Copy SHA-256' }))
    const paired = sha256.toUpperCase().match(/../g).join(':')
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(paired))
    expect(row('SHA-1').querySelector('dd.absent')).toHaveTextContent('—')
    expect(row('Added By').querySelector('dd.absent')).toHaveTextContent('—')
  })

  it('offers no deletion without delete:truststore', async () => {
    perms.del = false
    const { container } = renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Bank Root' }))
    const dock = await waitFor(() => { const d = container.querySelector('#inspector'); expect(d).toBeTruthy(); return d })
    expect(dock.querySelector('#truststore-delete')).toBeNull()
    expect(dock.querySelector('#truststore-export')).toBeTruthy()
  })
})

describe('the anchor dock in the URL', () => {
  it('reopens the anchor and section of the URL, then writes the one opened', async () => {
    const r = renderAtUrl(<TrustStorePage />, '/truststore?item=2&section=details')
    const dock = await r.dock()
    await waitFor(() => expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('Old proxy'))
    expect(within(dock).getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Bank Root' }))
    expect(r.where()).toBe('/truststore?item=1')
    fireEvent.click(within(await r.dock()).getByRole('tab', { name: 'PEM' }))
    expect(r.where()).toBe('/truststore?item=1&section=pem')
  })
})

describe('adding from the managed CAs', () => {
  it('names each CA root or intermediate from its own certificate, translated', async () => {
    managed.cas = [
      { id: 7, descr: 'Example Root CA', subject: 'CN=Example Root CA', issuer: 'CN=Example Root CA', is_root: true, type: 'root' },
      { id: 8, descr: 'Example Issuing CA', subject: 'CN=Example Issuing CA', issuer: 'CN=Example Root CA', is_root: false, type: 'intermediate' },
    ]
    renderPage()
    await screen.findByRole('button', { name: 'Bank Root' })
    fireEvent.click(document.querySelector('#truststore-add'))
    const dialog = await screen.findByTestId('truststore-add-dialog')
    const line = async (name) => (await within(dialog).findByText(name)).closest('label')
    expect(await line('Example Root CA')).toHaveTextContent('Root CA')
    expect(await line('Example Issuing CA')).toHaveTextContent('Intermediate CA')
    expect(await line('Example Issuing CA')).not.toHaveTextContent('Root CA')
    managed.cas = []
  })
})
