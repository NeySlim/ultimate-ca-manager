/**
 * Autorités SSH as the mockup's ssh module draws it: the list (Nom, Type, Clé, Certificats,
 * Créée) with its type chips and search, the one-object dock and its tabs, the setup commands,
 * the row actions each permission allows, and the import and create dialogs in the mockup's frame.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
const stable = vi.hoisted(() => ({
  i18n: { t: (k) => k, i18n: { language: 'fr', changeLanguage: () => {}, on: () => {}, off: () => {} } },
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn(), showConfirm: vi.fn().mockResolvedValue(false) },
}))
const m = vi.hoisted(() => ({ getAll: vi.fn(), write: true, del: true, copy: vi.fn(), mobile: false }))
vi.mock('../../contexts', () => ({ useNotification: () => stable.notify, useMobile: () => ({ isMobile: m.mobile }) }))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: m.mobile }) }))
vi.mock('../../hooks', async () => {
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  return {
    useCRUDPage: crud.useCRUDPage,
    useClipboard: () => ({ copy: m.copy, isCopied: () => false }),
    usePermission: () => ({ canWrite: () => m.write, canDelete: () => m.del, canRead: () => true, hasPermission: () => true }),
  }
})
vi.mock('../../services', () => ({
  sshCasService: { getAll: (...a) => m.getAll(...a), create: vi.fn(), importCA: vi.fn() },
  hsmService: { getProviders: vi.fn(), getSigningKeys: vi.fn() },
  policiesService: { getEffective: vi.fn().mockResolvedValue({ data: {} }) },
}))

import { renderAtUrl } from '../../test/dockUrl'
import { sortKeys, sortedHeaders, absorbing, numberHeads, recordFacts } from '../../test/listColumns'
import { PATHS } from '../../components/atelier/icons'
import SSHCAsPage from '../SSHCAsPage'

const USERS = { id: 1, refid: 'r-users', descr: 'Users CA', ca_type: 'user', key_type: 'ssh-ed25519', fingerprint: 'SHA256:aaa', cert_count: 7,
  default_ttl: '16h', allowed_principals: ['ops'], default_extensions: ['permit-pty'], public_key: 'ssh-ed25519 AAAA users' }
const HOSTS = { id: 2, refid: 'r-hosts', descr: 'Hosts CA', ca_type: 'host', key_type: 'ecdsa-sha2-nistp384', key_source: 'hsm', hsm_key_label: 'piv-sign', cert_count: 5 }

const page = () => render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  m.write = true
  m.del = true
  m.mobile = false
  m.getAll.mockResolvedValue({ data: [USERS, HOSTS] })
})

describe('the SSH CA list', () => {
  it('draws the module columns and the type chips with their counters', async () => {
    page()
    await screen.findByRole('button', { name: 'Users CA' })
    expect([...document.querySelectorAll('.module-table thead th')].map((h) => h.textContent))
      .toEqual(['atelier.name', 'sshCas.caType', 'sshCas.keyType', 'sshCas.stats.certificates', 'certificates.creationColumn', 'common.actions'])
    const chips = screen.getByRole('group', { name: 'sshCas.filterByType' })
    expect([...chips.querySelectorAll('.view-btn')].map((b) => b.textContent)).toEqual(['common.all2', 'sshCas.typeUser1', 'sshCas.typeHost1'])
    // an HSM key says so beside its type
    const hosts = screen.getByRole('button', { name: 'Hosts CA' }).closest('tr')
    expect(within(hosts).getByText('HSM')).toBeInTheDocument()
  })

  it('narrows by type and by search, and puts both back from the no-match block', async () => {
    page()
    await screen.findByRole('button', { name: 'Users CA' })
    fireEvent.click(screen.getByRole('button', { name: /sshCas\.typeHost/ }))
    expect(screen.queryByRole('button', { name: 'Users CA' })).toBeNull()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'nothing-here' } })
    fireEvent.click(await screen.findByRole('button', { name: 'table.clearFilters' }))
    expect(screen.getByRole('button', { name: 'Users CA' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hosts CA' })).toBeInTheDocument()
  })

  it('sorts its columns from their headers and pages a long list, back to page one on a chip', async () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ ...HOSTS, id: 10 + i, refid: `r${i}`, descr: `Host ${String(i + 1).padStart(2, '0')}`, cert_count: i }))
    m.getAll.mockResolvedValue({ data: [USERS, ...many] })
    const { container } = page()
    await screen.findByRole('button', { name: 'Host 01' })
    const footer = container.querySelector('footer.table-footer')
    const names = () => [...container.querySelectorAll('tbody .entity-name')].map((b) => b.textContent)
    expect(names()).toHaveLength(25)
    expect(screen.getByRole('columnheader', { name: 'atelier.name' })).toHaveAttribute('aria-sort', 'ascending')
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    expect(names()).toEqual(['Host 26', 'Host 27', 'Host 28', 'Host 29', 'Host 30', 'Users CA'])
    fireEvent.click(container.querySelector('[data-status="host"]'))
    expect(footer).toHaveTextContent('1 / 2')
    fireEvent.click(screen.getByRole('button', { name: 'sshCas.stats.certificates' }))
    fireEvent.click(screen.getByRole('button', { name: 'sshCas.stats.certificates' }))
    expect(names()[0]).toBe('Host 30')
    for (const name of ['sshCas.caType', 'sshCas.keyType', 'certificates.creationColumn']) {
      fireEvent.click(screen.getByRole('button', { name }))
      expect(screen.getByRole('columnheader', { name })).toHaveAttribute('aria-sort', 'ascending')
    }
  })

  it('opens on the name ascending, the name taking the room left, the count at the right', async () => {
    const { container } = page()
    await screen.findByRole('button', { name: 'Users CA' })
    expect(sortedHeaders(container)).toEqual([['atelier.name', 'ascending']])
    expect(sortKeys(container)).toEqual(['name', 'type', 'key', 'certs', 'created'])
    expect(absorbing(container)).toEqual(['atelier.name'])
    expect(numberHeads(container)).toEqual(['sshCas.stats.certificates'])
  })

  it('keeps another sort in the address and reads it back', async () => {
    const at = renderAtUrl(<SSHCAsPage />, '/ssh/cas')
    await screen.findByRole('button', { name: 'Users CA' })
    fireEvent.click(at.container.querySelector('[data-sort="certs"]'))
    expect(at.where()).toBe('/ssh/cas?sort=certs&order=asc')
    at.unmount()
    const again = renderAtUrl(<SSHCAsPage />, '/ssh/cas?sort=certs&order=desc')
    await screen.findByRole('button', { name: 'Users CA' })
    expect(sortedHeaders(again.container)).toEqual([['sshCas.stats.certificates', 'descending']])
    expect(again.container.querySelector('tbody .entity-name')).toHaveTextContent('Users CA')
  })

  it('draws a phone record whose count is said', async () => {
    m.mobile = true
    page()
    await screen.findByRole('button', { name: 'Users CA' })
    const record = [...document.querySelectorAll('article.mobile-record')].find((r) => r.textContent.includes('Users CA'))
    expect(recordFacts(record)).toContain('sshCas.stats.certificates 7')
  })

  it('links to the SSH certificates at their registered address', async () => {
    page()
    await screen.findByRole('button', { name: 'Users CA' })
    expect(screen.getByRole('link', { name: 'sshCertificates.title' })).toHaveAttribute('href', '/ssh/certificates')
  })

  it('keeps the link to the certificates and Importer on a phone, in the page actions menu', async () => {
    m.mobile = true
    const at = renderAtUrl(<SSHCAsPage />, '/ssh/cas')
    await screen.findAllByRole('button', { name: 'Users CA' })
    fireEvent.click(screen.getByRole('button', { name: 'atelier.pageActions' }))
    const menu = screen.getByTestId('inspector-actions-dialog')
    expect(within(menu).getAllByRole('button').map((b) => b.textContent).filter(Boolean)).toEqual(['sshCertificates.title', 'common.import'])
    fireEvent.click(within(menu).getByRole('button', { name: 'common.import' }))
    expect(await screen.findByText('sshCas.importCA')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'atelier.pageActions' }))
    fireEvent.click(within(screen.getByTestId('inspector-actions-dialog')).getByRole('button', { name: 'sshCertificates.title' }))
    expect(at.where()).toBe('/ssh/certificates')
  })

  it('gives a reader no create, import, edit or delete', async () => {
    m.write = false
    m.del = false
    page()
    const row = (await screen.findByRole('button', { name: 'Users CA' })).closest('tr')
    expect(screen.queryByText('sshCas.createCA')).toBeNull()
    expect(screen.queryByText('common.import')).toBeNull()
    expect(within(row).queryByTitle('common.edit')).toBeNull()
    expect(within(row).queryByTitle('common.delete')).toBeNull()
    expect(within(row).getByTitle('sshCas.downloadPublicKey')).toBeInTheDocument()
  })
})

describe('the SSH CA dock', () => {
  it('opens on the overview, then shows the setup commands, the configuration and the key', async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Users CA' }))
    const dock = container.querySelector('aside#inspector')
    expect(within(dock).getAllByRole('tab').map((tab) => tab.textContent))
      .toEqual(['atelier.overview', 'sshCas.quickInstall', 'sshCas.configuration', 'sshCas.publicKey'])
    expect(within(dock).getByText('SHA256:aaa')).toBeInTheDocument()

    fireEvent.click(within(dock).getByRole('tab', { name: 'sshCas.quickInstall' }))
    const command = within(dock).getByText(/\/ssh\/setup\/r-users \| sudo bash$/)
    fireEvent.click(within(command.closest('.command-line')).getByRole('button', { name: 'common.copy' }))
    await waitFor(() => expect(m.copy).toHaveBeenCalledWith(expect.stringContaining('/ssh/setup/r-users'), 'curl'))

    fireEvent.click(within(dock).getByRole('tab', { name: 'sshCas.configuration' }))
    expect(within(dock).getByText('16h')).toBeInTheDocument()
    expect(within(dock).getByText('ops')).toBeInTheDocument()

    fireEvent.click(within(dock).getByRole('tab', { name: 'sshCas.publicKey' }))
    expect(within(dock).getByText('ssh-ed25519 AAAA users')).toBeInTheDocument()
  })

  it('keeps two everyday actions on the panel, the others in its « ⋯ » menu, deletion last in red', async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Users CA' }))
    const dock = container.querySelector('aside#inspector')
    const actions = dock.querySelector('.dock-heading .actions') || dock
    expect(actions.querySelector('#ssh-ca-pubkey')).toBeTruthy()
    expect(actions.querySelector('#ssh-ca-copy')).toBeTruthy()
    for (const id of ['#ssh-ca-krl', '#ssh-ca-edit', '#ssh-ca-delete']) expect(dock.querySelector(id)).toBeNull()
    expect(dock.querySelector('.btn.danger')).toBeNull()
    fireEvent.click(dock.querySelector('[data-ssh-ca-menu]'))
    const menu = await screen.findByTestId('inspector-actions-dialog')
    const items = [...menu.querySelectorAll('.columns-list > .btn')]
    expect(items.map((b) => b.dataset.action)).toEqual(['cert-krl', 'cert-edit', 'cert-delete'])
    expect(items.at(-1)).toHaveClass('danger')
  })

  it('draws a deletion with one icon, the cross of the CSR and template menus, not the « revoked » sign', async () => {
    const { container } = page()
    const row = (await screen.findByRole('button', { name: 'Users CA' })).closest('tr')
    const drawing = (name) => { const div = document.createElement('div'); div.innerHTML = `<svg>${PATHS[name]}</svg>`; return div.querySelector('svg').innerHTML }
    expect(within(row).getByTitle('common.delete').querySelector('svg').innerHTML).toBe(drawing('close'))
    fireEvent.click(await screen.findByRole('button', { name: 'Users CA' }))
    fireEvent.click(container.querySelector('aside#inspector [data-ssh-ca-menu]'))
    const remove = (await screen.findByTestId('inspector-actions-dialog')).querySelector('[data-action="cert-delete"]')
    expect(remove.querySelector('svg').innerHTML).toBe(drawing('close'))
  })

  it('opens the import dialog in the mockup frame, its key in monospace', async () => {
    page()
    await screen.findByRole('button', { name: 'Users CA' })
    fireEvent.click(screen.getByRole('button', { name: 'common.import' }))
    const dialog = document.querySelector('dialog')
    expect(dialog).toHaveClass('wide')
    expect(within(dialog).getByLabelText('sshCas.privateKey')).toHaveClass('mono')
    expect(dialog.querySelector('.modal-actions .btn.primary')).toHaveTextContent('common.import')
  })
})

describe('the SSH CA dock in the URL', () => {
  it('reopens the authority and section of the URL, then writes the one opened', async () => {
    const r = renderAtUrl(<SSHCAsPage />, '/ssh/cas?item=2&section=config')
    const dock = await r.dock()
    expect(within(dock).getByRole('tab', { name: 'sshCas.configuration' })).toHaveAttribute('aria-selected', 'true')
    expect(within(dock).getByRole('heading', { level: 2 })).toHaveTextContent('Hosts CA')
    fireEvent.click(screen.getByRole('button', { name: 'Users CA' }))
    expect(r.where()).toBe('/ssh/cas?item=1')
    fireEvent.click(within(await r.dock()).getByRole('tab', { name: 'sshCas.quickInstall' }))
    expect(r.where()).toBe('/ssh/cas?item=1&section=install')
  })
})

describe('the SSH CA dock in typed rows', () => {
  const rowIn = (dock, label) => within(dock).getByText(label, { selector: 'dt' }).closest('div.row')
  const openUsers = async () => {
    const { container } = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Users CA' }))
    return waitFor(() => { const d = container.querySelector('aside#inspector'); expect(within(d).getByText('sshCas.fingerprint')).toBeTruthy(); return d })
  }

  it('puts the fingerprint in a copyable chip and an unknown author in grey', async () => {
    const dock = await openUsers()
    expect(dock.querySelector('dl.props')).toBeNull()
    expect(rowIn(dock, 'sshCas.fingerprint').querySelector('dd.v .code-value')).toHaveTextContent('SHA256:aaa')
    expect(rowIn(dock, 'sshCas.fingerprint').querySelector('.code-value.hex')).toBeNull()
    expect(within(rowIn(dock, 'sshCas.fingerprint')).getByRole('button', { name: 'protocols.copyValue' })).toBeInTheDocument()
    expect(rowIn(dock, 'common.createdBy').querySelector('dd.absent')).toHaveTextContent('—')
    expect(rowIn(dock, 'sshCas.stats.certificates').querySelector('dd.v')).toHaveTextContent('7')
  })

  it('greys an unset lifetime (0 included) and gives the principal rule as a pill', async () => {
    m.getAll.mockResolvedValue({ data: [{ ...USERS, allowed_principals: [], allow_any_principal: false, max_ttl: 0 }] })
    const dock = await openUsers()
    fireEvent.click(within(dock).getByRole('tab', { name: 'sshCas.configuration' }))
    expect(rowIn(dock, 'sshCas.defaultTtl').querySelector('dd.v')).toHaveTextContent('16h')
    expect(rowIn(dock, 'sshCas.maxTtl').querySelector('dd.absent')).toHaveTextContent('—')
    expect(rowIn(dock, 'sshCas.allowedPrincipals').querySelector('dd.v .badge.bad')).toHaveTextContent('sshCas.noPrincipalSignsNothing')
    expect(rowIn(dock, 'sshCas.defaultExtensions')).toHaveClass('long')
    expect(rowIn(dock, 'sshCertificates.keyId')).toHaveClass('long')
  })
})
