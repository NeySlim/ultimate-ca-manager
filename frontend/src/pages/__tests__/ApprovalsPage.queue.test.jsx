/**
 * ApprovalsPage as a work queue: groups from the real deadline, decisions with
 * the reason the server requires, bulk decisions ending on a line-by-line
 * outcome, nothing to act on without write:approvals, the decided ones in the history.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

configure({ asyncUtilTimeout: 5000 })

const stable = vi.hoisted(() => ({
  i18n: null,
  notify: { showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {} },
  canWrite: true,
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
    canWrite: () => stable.canWrite, canRead: () => true, canDelete: () => false,
    hasPermission: () => stable.canWrite,
  }),
}))
const api = vi.hoisted(() => ({ list: vi.fn(), approve: vi.fn(), reject: vi.fn(), getById: vi.fn(), getStats: vi.fn() }))
vi.mock('../../services', () => ({ approvalsService: api, casService: { getAll: async () => ({ data: [{ id: 4, common_name: 'Services CA G2' }] }) } }))

import ApprovalsPage from '../ApprovalsPage'

const HOUR = 3600000
const at = (h) => new Date(Date.now() + h * HOUR).toISOString()
const req = (id, cn, extra = {}) => ({
  id, request_type: 'csr', status: 'pending', requester_username: 'equipe-paiement', policy_name: 'Serveur TLS',
  created_at: at(-20), expires_at: at(28), approvals: [], required_approvals: 1,
  request_summary: { cn, ca_id: 4 }, ...extra,
})
let rows
const renderPage = () => render(<MemoryRouter><ApprovalsPage /></MemoryRouter>)
const group = (label) => screen.getByRole('heading', { level: 2, name: new RegExp(`^${label}`) }).closest('section')

beforeEach(() => {
  vi.clearAllMocks()
  stable.canWrite = true
  rows = [
    req(118, 'payments.example.com'),
    req(119, 'later.example.com', { expires_at: at(24 * 4 + 2) }),
    // No expires_at: the server's seven days from creation, here 12 h from now
    req(120, 'nodeadline.example.com', { expires_at: null, created_at: at(12 - 7 * 24) }),
    req(90, 'refused.example.com', { status: 'rejected', resolved_at: at(-30),
      approvals: [{ username: 'bob', action: 'reject', comment: 'Mauvais modèle', timestamp: at(-30) }] }),
  ]
  api.list.mockImplementation(async () => ({ data: rows }))
})

describe('ApprovalsPage queue', () => {
  it('heads the page like the mockup: title, pending count, intent', async () => {
    renderPage()
    expect(await screen.findByText('3 en attente')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Approbations' })).toBeInTheDocument()
    expect(screen.getByText('Demandes en attente de validation.')).toBeInTheDocument()
  })

  it('groups the open requests by their real deadline, soonest first', async () => {
    renderPage()
    await screen.findByText('payments.example.com')
    const soon = group('À traiter sous 48 h')
    expect([...soon.querySelectorAll('.wk-subject')].map((b) => b.textContent))
      .toEqual(['CSR à signer : nodeadline.example.com', 'CSR à signer : payments.example.com'])
    expect(within(group('Plus tard')).getByText('later.example.com')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^En retard/ })).toBeNull()
  })

  it('draws a row as the mockup: type pill, requester, policy and authority, due date', async () => {
    renderPage()
    const li = (await screen.findByText('payments.example.com')).closest('li')
    expect(within(li).getByText('Approbation · CSR')).toBeInTheDocument()
    await waitFor(() => expect(within(li).getByText('Demandée par equipe-paiement il y a 20 h · Serveur TLS · Services CA G2')).toBeInTheDocument())
    expect(within(li).getByText('dans 28 h')).toBeInTheDocument()
  })

  it('draws the mockup\'s simple check on Approve…, in the row and in the dialog', async () => {
    renderPage()
    const button = await screen.findByRole('button', { name: 'Approuver CSR à signer : payments.example.com' })
    expect(button.querySelector('svg path')).toHaveAttribute('d', 'm5 12 4 4L19 6')
    fireEvent.click(button)
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByTestId('decision-confirm').querySelector('svg path')).toHaveAttribute('d', 'm5 12 4 4L19 6')
  })

  it('refuses a rejection without a reason, as the server would', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Refuser CSR à signer : payments.example.com' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Refuser la demande')).toBeInTheDocument()
    // The mockup's field: 200 characters at most
    expect(within(dialog).getByLabelText('Motif')).toHaveAttribute('maxlength', '200')
    fireEvent.click(within(dialog).getByTestId('decision-confirm'))
    expect(await within(dialog).findByText('Indiquez le motif du refus, 5 caractères au moins.')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Motif')).toHaveAttribute('aria-invalid', 'true')
    expect(api.reject).not.toHaveBeenCalled()
    // Four characters are not a reason yet, as the mockup counts
    fireEvent.change(within(dialog).getByLabelText('Motif'), { target: { value: 'Non.' } })
    fireEvent.click(within(dialog).getByTestId('decision-confirm'))
    expect(within(dialog).getByLabelText('Motif')).toHaveAttribute('aria-invalid', 'true')
    expect(api.reject).not.toHaveBeenCalled()
    fireEvent.change(within(dialog).getByLabelText('Motif'), { target: { value: 'Mauvais modèle' } })
    api.reject.mockResolvedValue({ data: {} })
    fireEvent.click(within(dialog).getByTestId('decision-confirm'))
    await waitFor(() => expect(api.reject).toHaveBeenCalledWith(118, 'Mauvais modèle'))
  })

  it('approves several requests in turn and says which went through and why the others did not', async () => {
    api.approve.mockImplementation(async (id) => {
      if (id === 120) throw new Error('You have already voted on this request')
      if (id === 118) return { data: { certificate_issued: false, issue_error: 'CA offline' } }
      return { data: { certificate_issued: true, certificate: { id: 7 } } }
    })
    renderPage()
    await screen.findByText('payments.example.com')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tout sélectionner : À traiter sous 48 h' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner CSR à signer : later.example.com' }))
    const bar = screen.getByRole('group', { name: 'Actions groupées' })
    expect(within(bar).getByText('3 éléments sélectionnés')).toBeInTheDocument()
    fireEvent.click(within(bar).getByRole('button', { name: /Approuver…/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Approuver les demandes')).toBeInTheDocument()
    expect(within(dialog).getAllByRole('listitem')).toHaveLength(3)
    fireEvent.click(within(dialog).getByTestId('decision-confirm'))
    const outcome = await within(dialog).findByTestId('bulk-outcome')
    expect(api.approve.mock.calls.map((c) => c[0])).toEqual([120, 118, 119])
    expect(within(outcome).getByRole('status')).toHaveTextContent('1 réussie, 2 échouées')
    expect(within(outcome).getByText(/nodeadline/).closest('li')).toHaveTextContent('You have already voted on this request')
    expect(within(outcome).getByText(/payments/).closest('li')).toHaveTextContent('CA offline')
    expect(within(outcome).getByText(/later/).closest('li')).toHaveClass('is-ok')
  })

  it('gives the focus back to the row button when a decision is left with Escape', async () => {
    renderPage()
    const button = await screen.findByRole('button', { name: 'Approuver CSR à signer : payments.example.com' })
    button.focus()
    fireEvent.click(button)
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Demande #118')).toBeInTheDocument()
    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(button).toHaveFocus())
  })

  it('ends a bulk decision that went through on one message, without an outcome screen', async () => {
    const success = vi.spyOn(stable.notify, 'showSuccess')
    api.reject.mockResolvedValue({ data: {} })
    renderPage()
    await screen.findByText('payments.example.com')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tout sélectionner : À traiter sous 48 h' }))
    fireEvent.click(within(screen.getByRole('group', { name: 'Actions groupées' })).getByRole('button', { name: /Refuser…/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('2 demandes')).toBeInTheDocument()
    // The notice is the one sentence of the decision, as the mockup's
    expect(dialog.querySelector('.wk-notice')).toHaveTextContent(/^Les demandes quittent la file, la barre d’état et la carte À traiter\.$/)
    fireEvent.change(within(dialog).getByLabelText('Motif'), { target: { value: 'Mauvais modèle' } })
    fireEvent.click(within(dialog).getByTestId('decision-confirm'))
    await waitFor(() => expect(success).toHaveBeenCalledWith('2 demandes refusées'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.queryByTestId('bulk-outcome')).toBeNull()
    success.mockRestore()
  })

  it('says which request a single rejection was for', async () => {
    const success = vi.spyOn(stable.notify, 'showSuccess')
    api.reject.mockResolvedValue({ data: {} })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Refuser CSR à signer : payments.example.com' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Motif'), { target: { value: 'Mauvais modèle' } })
    fireEvent.click(within(dialog).getByTestId('decision-confirm'))
    await waitFor(() => expect(success).toHaveBeenCalledWith('Demande #118 refusée'))
    success.mockRestore()
  })

  it('offers neither decisions nor selection without write:approvals', async () => {
    stable.canWrite = false
    renderPage()
    await screen.findByText('payments.example.com')
    expect(screen.queryByRole('button', { name: /^Approuver/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Refuser/ })).toBeNull()
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
    expect(screen.getByText('Un sujet ouvre le détail.')).toBeInTheDocument()
  })

  it('keeps the decided requests in the folded history, with who, when and why', async () => {
    renderPage()
    const toggle = await screen.findByRole('button', { name: /^Traitées récemment/ })
    expect(toggle).toHaveTextContent('Traitées récemment1')
    fireEvent.click(toggle)
    const li = screen.getByText('refused.example.com').closest('li')
    expect(within(li).getByText('Refusée')).toBeInTheDocument()
    expect(li).toHaveTextContent(/bob · .* · Mauvais modèle/)
  })

  it('opens a request in the inspector from its subject', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'CSR à signer : payments.example.com' }))
    expect(openEntity).toHaveBeenCalledWith('approval', 118, { data: expect.objectContaining({ id: 118 }) })
  })

  it('says the queue is empty with the mockup sentence and points to the policies', async () => {
    rows = []
    renderPage()
    expect(await screen.findByText('Aucune demande en attente')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Voir les politiques' })).toHaveAttribute('href', '/policies')
  })

  it('shows a load failure with Retry, which reads again', async () => {
    api.list.mockRejectedValueOnce(new Error('HTTP 503'))
    renderPage()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('HTTP 503')
    fireEvent.click(within(alert).getByRole('button', { name: 'Réessayer' }))
    expect(await screen.findByText('payments.example.com')).toBeInTheDocument()
  })
})
