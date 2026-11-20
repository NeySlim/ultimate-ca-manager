/**
 * KeyRecoveryPage as a work queue: requests to approve, then keys to recover,
 * the closed ones in the history; ?request=N shows and opens that request even
 * past the 500 the list holds; the actions follow the separation of roles.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

configure({ asyncUtilTimeout: 5000 })

const stable = vi.hoisted(() => ({
  i18n: null,
  notify: { showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {} },
  perms: [], username: 'bob',
}))
vi.mock('react-i18next', () => ({ useTranslation: () => stable.i18n, Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }))
import { frI18n } from '../../components/work/__tests__/frI18n'
stable.i18n = frI18n

const openEntity = vi.fn()
vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, screenWidth: 1600, sidebarOpen: true, setSidebarOpen: () => {} }),
  useInspector: () => ({ openEntity, activeKey: null }),
}))
vi.mock('../../hooks', () => ({
  usePermission: () => ({
    canWrite: () => true, canRead: () => true, canDelete: () => true,
    hasPermission: (p) => stable.perms.includes(p), username: stable.username,
  }),
}))
const api = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), approve: vi.fn(), reject: vi.fn(), recover: vi.fn() }))
vi.mock('../../services', () => ({ keyRecoveryService: api }))

import KeyRecoveryPage from '../KeyRecoveryPage'

const ADMIN = ['admin:key_recovery', 'write:key_recovery', 'read:key_recovery']
const req = (id, status, cn, by = 'alice') => ({ id, status, cert_id: id, cert_cn: cn, reason: 'lost', requested_by: by, requested_at: new Date(Date.now() - 3 * 3600000).toISOString() })
let rows
let dual
const renderPage = (path = '/key-recovery') => render(<MemoryRouter initialEntries={[path]}><KeyRecoveryPage /></MemoryRouter>)
const group = (name) => screen.getByRole('heading', { level: 2, name: new RegExp(`^${name}`) }).closest('section')
const rowOf = (cn) => screen.getByText(cn).closest('li')

beforeEach(() => {
  vi.clearAllMocks()
  stable.perms = ADMIN
  stable.username = 'bob'
  dual = true
  rows = [req(1, 'pending', 'cn-one'), req(2, 'approved', 'cn-two'), req(3, 'pending', 'cn-mine', 'bob'), req(4, 'recovered', 'cn-done'), req(900, 'pending', 'cn-linked')]
  // The list stops before the linked request, as past the 500 it holds
  api.list.mockImplementation(async () => ({ data: { requests: rows.filter((r) => r.id !== 900).map((r) => ({ ...r })), dual_control: dual } }))
  api.get.mockImplementation(async (id) => ({ data: { ...rows.find((r) => String(r.id) === String(id)) } }))
})

describe('KeyRecoveryPage queue', () => {
  it('puts the requests to approve, then the keys to recover, the closed ones in the history', async () => {
    renderPage()
    await screen.findByText('cn-one')
    expect(within(group('À approuver par un autre administrateur')).getAllByText(/^cn-/).map((e) => e.textContent)).toEqual(['cn-one', 'cn-mine'])
    expect(within(group('À récupérer')).getByText('cn-two')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Traitées récemment/ })).toHaveTextContent('1')
    expect(screen.getByText('3 en cours')).toBeInTheDocument()
  })

  it('keeps the place of Approve… on one\'s own request, so the due dates of a group line up', async () => {
    renderPage()
    await screen.findByText('cn-one')
    const slot = rowOf('cn-mine').querySelector('.wk-action > :first-child')
    expect(slot).toHaveClass('is-placeholder')
    expect(slot).toHaveAttribute('aria-hidden', 'true')
    expect(within(rowOf('cn-mine')).queryByRole('button', { name: /Approuver/ })).toBeNull()
    expect(rowOf('cn-one').querySelector('.is-placeholder')).toBeNull()
    // A key to recover keeps the check column, empty: its text lines up with the group above
    expect(rowOf('cn-two')).not.toHaveClass('no-check')
    expect(within(rowOf('cn-two')).queryByRole('checkbox')).toBeNull()
  })

  it('says which request a decision was for, and ends a bulk one that went through on one message', async () => {
    const success = vi.spyOn(stable.notify, 'showSuccess')
    api.reject.mockResolvedValue({})
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Refuser la récupération de cn-one' }))
    let dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByTestId('recovery-confirm')).toHaveTextContent('Refuser')
    fireEvent.change(within(dialog).getByLabelText('Motif'), { target: { value: 'Clé encore utilisée' } })
    fireEvent.click(within(dialog).getByTestId('recovery-confirm'))
    await waitFor(() => expect(success).toHaveBeenCalledWith('Demande #1 refusée'))
    expect(api.reject).toHaveBeenCalledWith(1, 'Clé encore utilisée')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tout sélectionner : À approuver par un autre administrateur' }))
    fireEvent.click(within(screen.getByRole('group', { name: 'Actions groupées' })).getByRole('button', { name: /Refuser/ }))
    dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Motif'), { target: { value: 'Clé encore utilisée' } })
    fireEvent.click(within(dialog).getByTestId('recovery-confirm'))
    await waitFor(() => expect(success).toHaveBeenCalledWith('2 demandes refusées'))
    expect(screen.queryByTestId('bulk-outcome')).toBeNull()
    success.mockRestore()
  })

  it('refuses a rejection without a reason of five characters, as every refusal of the queues', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Refuser la récupération de cn-one' }))
    const dialog = await screen.findByRole('dialog')
    const reason = within(dialog).getByLabelText('Motif')
    expect(reason).toHaveAttribute('maxlength', '200')
    expect(within(dialog).getByText('Obligatoire pour un refus : ajouté au journal avec la décision.')).toBeInTheDocument()
    fireEvent.change(reason, { target: { value: 'non' } })
    fireEvent.click(within(dialog).getByTestId('recovery-confirm'))
    expect(await within(dialog).findByText('Indiquez le motif du refus, 5 caractères au moins.')).toBeInTheDocument()
    expect(reason).toHaveAttribute('aria-invalid', 'true')
    expect(reason).toHaveFocus()
    expect(api.reject).not.toHaveBeenCalled()
  })

  it('puts the password error between the field and its hint, as the mockup\'s fields', async () => {
    rows = [{ ...req(2, 'approved', 'cn-two'), decided_by: 'carol' }]
    renderPage()
    // The facts of the row name who decided, as the request reads
    expect(await screen.findByText(/· Décidée par carol$/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Récupérer la clé de cn-two' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Mot de passe PKCS#12'), { target: { value: 'court' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Télécharger .p12' }))
    const error = await within(dialog).findByText('Le mot de passe doit faire au moins 8 caractères.')
    const field = error.closest('.wk-field')
    expect([...field.children].map((el) => el.tagName)).toEqual(['LABEL', 'INPUT', 'P', 'SMALL'])
    expect(within(field).getByText('Au moins 8 caractères.')).toBeInTheDocument()
    expect(api.recover).not.toHaveBeenCalled()
  })

  it('names the approval note in the feminine, optional', async () => {
    dual = false
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Approuver la récupération de cn-one' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('facultative').closest('label')).toHaveTextContent('Note facultative')
    expect(within(dialog).getByText('Conservée avec la décision.')).toBeInTheDocument()
  })

  it('gives the focus back to the row button when a decision is left with Escape', async () => {
    renderPage()
    const button = await screen.findByRole('button', { name: 'Refuser la récupération de cn-one' })
    button.focus()
    fireEvent.click(button)
    const dialog = await screen.findByRole('dialog')
    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(button).toHaveFocus())
  })

  it('names the group plainly when dual control is off', async () => {
    dual = false
    renderPage()
    await screen.findByText('cn-one')
    expect(group('À approuver')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: /autre administrateur/ })).toBeNull()
  })

  it('with dual control, offers no approval of one\'s own request, only its rejection', async () => {
    renderPage()
    await screen.findByText('cn-mine')
    expect(within(rowOf('cn-mine')).queryByRole('button', { name: /^Approuver/ })).toBeNull()
    expect(within(rowOf('cn-mine')).getByRole('button', { name: 'Refuser la récupération de cn-mine' })).toBeInTheDocument()
    expect(within(rowOf('cn-one')).getByRole('button', { name: 'Approuver la récupération de cn-one' })).toBeInTheDocument()
  })

  it('selects only the requests a bulk decision can reach: pending ones, not the keys to recover', async () => {
    renderPage()
    await screen.findByText('cn-two')
    expect(within(rowOf('cn-one')).getByRole('checkbox')).toBeInTheDocument()
    expect(within(rowOf('cn-two')).queryByRole('checkbox')).toBeNull()
  })

  it('gives no decision and no selection without admin:key_recovery; the requester still recovers', async () => {
    stable.perms = ['write:key_recovery', 'read:key_recovery']
    stable.username = 'alice'
    renderPage()
    await screen.findByText('cn-one')
    expect(screen.queryByRole('button', { name: /^Approuver|^Refuser/ })).toBeNull()
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
    expect(within(rowOf('cn-two')).getByRole('button', { name: 'Récupérer la clé de cn-two' })).toBeInTheDocument()
  })

  it('does not offer the recovery to someone else than the requester or an administrator', async () => {
    stable.perms = ['write:key_recovery', 'read:key_recovery']
    stable.username = 'carol'
    renderPage()
    await screen.findByText('cn-two')
    expect(within(rowOf('cn-two')).queryByRole('button', { name: /Récupérer/ })).toBeNull()
  })

  it('approves with a note', async () => {
    api.approve.mockResolvedValue({})
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Approuver la récupération de cn-one' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/Note/), { target: { value: 'vu au téléphone' } })
    fireEvent.click(within(dialog).getByTestId('recovery-confirm'))
    await waitFor(() => expect(api.approve).toHaveBeenCalledWith(1, 'vu au téléphone'))
  })

  it('recovers with a password of eight characters at least', async () => {
    api.recover.mockResolvedValue(new Blob(['p12']))
    URL.createObjectURL = vi.fn(() => 'blob:x'); URL.revokeObjectURL = vi.fn()
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Récupérer la clé de cn-two' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/Mot de passe/), { target: { value: 'short' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /Télécharger/ }))
    expect(await within(dialog).findByRole('alert')).toBeInTheDocument()
    expect(api.recover).not.toHaveBeenCalled()
    fireEvent.change(within(dialog).getByLabelText(/Mot de passe/), { target: { value: 'Recover-pass-123' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /Télécharger/ }))
    await waitFor(() => expect(api.recover).toHaveBeenCalledWith(2, 'Recover-pass-123', false))
  })

  it('rejects several requests in turn and says which failed and why', async () => {
    api.reject.mockImplementation(async (id) => { if (id === 3) throw new Error('Request is not pending (status: rejected)'); return {} })
    renderPage()
    await screen.findByText('cn-one')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tout sélectionner : À approuver par un autre administrateur' }))
    fireEvent.click(within(screen.getByRole('group', { name: 'Actions groupées' })).getByRole('button', { name: /Refuser/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Motif'), { target: { value: 'Clé encore utilisée' } })
    fireEvent.click(within(dialog).getByTestId('recovery-confirm'))
    const outcome = await within(dialog).findByTestId('bulk-outcome')
    expect(within(outcome).getByRole('status')).toHaveTextContent('1 réussie, 1 échouée')
    expect(within(outcome).getByText(/cn-mine/).closest('li')).toHaveTextContent('Request is not pending (status: rejected)')
  })
})

describe('KeyRecoveryPage linked request', () => {
  it('shows a linked request outside the list and opens it in the inspector', async () => {
    renderPage('/key-recovery?request=900')
    expect(await screen.findByText('cn-linked')).toBeInTheDocument()
    await waitFor(() => expect(openEntity).toHaveBeenCalledWith('key_recovery', 900, { data: expect.objectContaining({ id: 900 }) }))
    expect(rowOf('cn-linked')).toHaveClass('is-opened')
  })

  it('the listed copy of the linked request wins over the copy read on opening', async () => {
    api.list.mockImplementation(async () => ({ data: { requests: rows.map((r) => (r.id === 900 ? { ...r, status: 'approved' } : { ...r })), dual_control: true } }))
    renderPage('/key-recovery?request=900')
    await waitFor(() => expect(openEntity).toHaveBeenCalled())
    expect(within(group('À récupérer')).getByText('cn-linked')).toBeInTheDocument()
    expect(screen.getAllByText('cn-linked')).toHaveLength(1)
  })
})
