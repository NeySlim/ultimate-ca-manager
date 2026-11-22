/**
 * Certificats SSH as the mockup's ssh module draws it: the state chips carry the server's counts
 * and ask the server for that state, the type filter and the sortable headers reach the server,
 * the dock opens on its overview with the grants and the certificate in further tabs, and the
 * revocation dialog is the mockup's narrow dialog with its danger action.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const stable = vi.hoisted(() => ({
  i18n: { t: (k) => k, i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} } },
  notify: { showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {}, showConfirm: () => Promise.resolve(false) },
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../contexts', () => ({ useNotification: () => stable.notify, useMobile: () => ({ isMobile: false }) }))
const m = vi.hoisted(() => ({ write: true }))
vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks')
  return {
    ...actual,
    usePermission: () => ({ canWrite: () => m.write, canDelete: () => m.write, hasPermission: () => true, canRead: () => true }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})
const getAll = vi.fn()
const getById = vi.fn()
vi.mock('../../services', () => ({
  sshCertificatesService: {
    getAll: (...a) => getAll(...a), getById: (...a) => getById(...a),
    getStats: () => Promise.resolve({ data: { certificates: { valid: 3, expired: 1, revoked: 2, total: 6 } } }),
    generate: vi.fn(), sign: vi.fn(), importCertificate: vi.fn(), revoke: vi.fn(),
  },
  sshCasService: { getAll: () => Promise.resolve({ data: [{ id: 4, name: 'Users CA', descr: 'Users CA', ca_type: 'user' }] }) },
}))

import { renderAtUrl } from '../../test/dockUrl'
import SSHCertificatesPage from '../SSHCertificatesPage'

const ALICE = { id: 1, key_id: 'alice', cert_type: 'user', principals: ['ops', 'dba', 'web'], ca_name: 'Users CA', serial: 7,
  valid_to: '2099-01-01T00:00:00Z', extensions: ['permit-pty'], critical_options: { 'force-command': '/bin/true' }, certificate: 'ssh-ed25519-cert-v01 AAAA' }
const lastParams = () => getAll.mock.calls.at(-1)[0]
const page = () => render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  m.write = true
  getAll.mockResolvedValue({ data: [ALICE], meta: { total: 1 } })
  getById.mockResolvedValue({ data: ALICE })
})

describe('the SSH certificate list', () => {
  it('counts each state from the server and asks the server for the chosen one', async () => {
    page()
    await screen.findByRole('button', { name: 'alice' })
    const chips = screen.getByRole('group', { name: 'sshCertificates.filterByState' })
    await waitFor(() => expect([...chips.querySelectorAll('.counter')].map((c) => c.textContent)).toEqual(['6', '3', '1', '2']))
    fireEvent.click(within(chips).getByRole('button', { name: /sshCertificates\.statusRevoked/ }))
    await waitFor(() => expect(lastParams()).toMatchObject({ status: ['revoked'], page: 1 }))
  })

  it('sends the type and the CA filters, and sorts by the name and the expiry on the server', async () => {
    page()
    await screen.findByRole('button', { name: 'alice' })
    fireEvent.change(screen.getByRole('combobox', { name: 'sshCertificates.certType' }), { target: { value: 'host' } })
    await waitFor(() => expect(lastParams()).toMatchObject({ type: ['host'] }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'sshCertificates.caName' }), { target: { value: '4' } })
    await waitFor(() => expect(lastParams()).toMatchObject({ ca_id: ['4'] }))
    // The nearest expiry first by default: a click reverses it
    expect(lastParams()).toMatchObject({ sort_by: 'valid_to', sort_order: 'asc' })
    fireEvent.click(screen.getByRole('button', { name: 'certificates.expiry' }))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'valid_to', sort_order: 'desc' }))
    fireEvent.click(screen.getByRole('button', { name: 'certificates.expiry' }))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'valid_to', sort_order: 'asc' }))
  })

  it('links to the SSH authorities at their registered address', async () => {
    page()
    await screen.findByRole('button', { name: 'alice' })
    expect(screen.getByRole('link', { name: 'sshCas.title' })).toHaveAttribute('href', '/ssh/cas')
  })

  it('keeps a long principal list whole in its cell and its title, the ellipsis shortening it (L6)', async () => {
    page()
    const row = (await screen.findByRole('button', { name: 'alice' })).closest('tr')
    const cell = within(row).getByText('ops, dba, web').closest('td')
    expect(cell).toHaveAttribute('title', 'ops, dba, web')
  })
})

describe('the SSH certificate dock', () => {
  it('opens on the overview, then the grants and the certificate', async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'alice' }))
    await waitFor(() => expect(getById).toHaveBeenCalledWith(1))
    const dock = container.querySelector('aside#inspector')
    expect(within(dock).getAllByRole('tab').map((tab) => tab.textContent))
      .toEqual(['atelier.overview', 'sshCertificates.grants', 'sshCertificates.certificate'])
    fireEvent.click(within(dock).getByRole('tab', { name: 'sshCertificates.grants' }))
    expect(within(dock).getByText('ops, dba, web')).toBeInTheDocument()
    expect(within(dock).getByText('/bin/true')).toBeInTheDocument()
    fireEvent.click(within(dock).getByRole('tab', { name: 'sshCertificates.certificate' }))
    expect(within(dock).getByText('ssh-ed25519-cert-v01 AAAA')).toBeInTheDocument()
  })

  it('revokes from a narrow dialog with a danger action, and offers neither to a reader', async () => {
    const { container, unmount } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'alice' }))
    const dock = await waitFor(() => { const d = container.querySelector('aside#inspector'); expect(d).toBeTruthy(); return d })
    fireEvent.click(await within(dock).findByRole('button', { name: 'sshCertificates.revokeCertificate' }))
    const dialog = document.querySelector('dialog')
    expect(dialog).toHaveClass('narrow')
    expect(dialog.querySelector('.modal-actions .btn.danger')).toHaveTextContent('sshCertificates.revokeCertificate')
    unmount()

    m.write = false
    const again = page()
    fireEvent.click(await screen.findByRole('button', { name: 'alice' }))
    await waitFor(() => expect(again.container.querySelector('aside#inspector')).toBeTruthy())
    expect(within(again.container.querySelector('aside#inspector')).queryByRole('button', { name: 'sshCertificates.revokeCertificate' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'sshCertificates.issueCertificate' })).toBeNull()
  })
})

describe('the SSH certificate dock in the URL', () => {
  it('reopens the certificate and section of the URL off the list\'s page, and writes the section', async () => {
    getAll.mockResolvedValue({ data: [], meta: { total: 40 } })
    const r = renderAtUrl(<SSHCertificatesPage />, '/ssh/certificates?item=1&section=grants')
    const dock = await r.dock()
    await waitFor(() => expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('alice'))
    expect(within(dock).getByRole('tab', { name: 'sshCertificates.grants' })).toHaveAttribute('aria-selected', 'true')
    expect(getById).toHaveBeenCalledWith(1)
    fireEvent.click(within(dock).getByRole('tab', { name: 'sshCertificates.certificate' }))
    expect(r.where()).toBe('/ssh/certificates?item=1&section=certificate')
  })
})

describe('the SSH certificate dock in typed rows (KV-3)', () => {
  const FP = 'SHA256:9fT1bW0x3hJp2Lq7Vz8Kc5Nd4Rm6Ys1Ae0Gu2Io3Pk'
  const BOB = { ...ALICE, id: 2, key_id: 'bob', principals: [], extensions: [], fingerprint: FP, ca_fingerprint: 'SHA256:caFP', key_type: null }
  const rowIn = (dock, label) => within(dock).getByText(label, { selector: 'dt' }).closest('div.row')
  let writeText
  beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
    getAll.mockResolvedValue({ data: [BOB], meta: { total: 1 } })
    getById.mockResolvedValue({ data: BOB })
  })
  const openBob = async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'bob' }))
    return waitFor(() => { const d = container.querySelector('aside#inspector'); expect(within(d).getByText('sshCertificates.fingerprint')).toBeTruthy(); return d })
  }

  it('copies the fingerprint whole from its chip, no button left in a value', async () => {
    const dock = await openBob()
    expect(dock.querySelector('dl.props')).toBeNull()
    const fp = rowIn(dock, 'sshCertificates.fingerprint')
    expect(fp.querySelector('dd.v .code-value')).toHaveTextContent(FP)
    fireEvent.click(within(fp).getByRole('button', { name: 'protocols.copyValue' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(FP))
    expect(rowIn(dock, 'sshCertificates.serial').querySelector('dd.v .code-value')).toHaveTextContent('7')
    expect(rowIn(dock, 'sshCertificates.caFingerprint').querySelector('dd.v .code-value')).toHaveTextContent('SHA256:caFP')
    expect(rowIn(dock, 'common.keyType').querySelector('dd.absent')).toHaveTextContent('—')
    expect(dock.querySelectorAll('dd.v button:not(.cp)')).toHaveLength(0)
  })

  it('greys an empty grant and puts a critical option in a chip', async () => {
    const dock = await openBob()
    fireEvent.click(within(dock).getByRole('tab', { name: 'sshCertificates.grants' }))
    expect(rowIn(dock, 'sshCertificates.principals').querySelector('dd.absent')).toHaveTextContent('—')
    expect(rowIn(dock, 'sshCertificates.extensions').querySelector('dd.absent')).toHaveTextContent('—')
    expect(rowIn(dock, 'force-command').querySelector('dd.v .code-value')).toHaveTextContent('/bin/true')
  })
})
