/**
 * An approval request in the inspector: what it asks for (protocol, identity,
 * CSR), its state in the user's language, its log, and a decision taken there
 * that reads the request again and tells the queue.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const stable = vi.hoisted(() => ({ i18n: null, canWrite: true }))
vi.mock('react-i18next', () => ({ useTranslation: () => stable.i18n, Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }))
import { frI18n } from '../../../components/work/__tests__/frI18n'
stable.i18n = frI18n

const notify = { showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn() }
const openEntity = vi.fn()
vi.mock('../../../contexts', () => ({ useNotification: () => notify, useInspector: () => ({ openEntity }) }))
vi.mock('../../../hooks', () => ({
  usePermission: () => ({ canWrite: () => stable.canWrite, canRead: () => true, hasPermission: () => stable.canWrite }),
}))
const api = vi.hoisted(() => ({ approve: vi.fn(), reject: vi.fn(), getById: vi.fn() }))
vi.mock('../../../services', () => ({ approvalsService: api }))

import { ApprovalDetail } from '../ApprovalDetail'

const PROTOCOL = {
  id: 51, request_type: 'est_enroll', status: 'pending', requester_username: 'est:basic:device', policy_name: 'Équipements',
  created_at: '2026-11-07T16:20:00Z', expires_at: '2026-11-14T16:20:00Z', approvals: [], required_approvals: 1,
  request_summary: {
    cn: 'device.example', protocol: 'est', operation: 'enroll', identity: 'basic:device',
    csr: '-----BEGIN CERTIFICATE REQUEST-----\nMIIB\n-----END CERTIFICATE REQUEST-----',
  },
}
const show = (req, section = 'request', props = {}) => render(
  <MemoryRouter>
    <ApprovalDetail data={req} objectKey="approval:51" title="Enrôlement EST : device.example" section={section} onSection={() => {}} {...props} />
  </MemoryRouter>,
)

beforeEach(() => { vi.clearAllMocks(); stable.canWrite = true })

describe('ApprovalDetail', () => {
  it('shows the protocol, its identity and the CSR of a held enrolment', () => {
    show(PROTOCOL)
    expect(screen.getByRole('heading', { level: 2, name: 'Enrôlement EST : device.example' })).toBeInTheDocument()
    expect(screen.getAllByText('En attente').length).toBeGreaterThan(0)
    expect(screen.getByText('EST (enroll)')).toBeInTheDocument()
    expect(screen.getByText('basic:device')).toBeInTheDocument()
    expect(screen.getByText(/BEGIN CERTIFICATE REQUEST/)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Demande' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Journal' })).toBeInTheDocument()
  })

  it('shows a decided request in French, with its decision', () => {
    show({ ...PROTOCOL, status: 'rejected', resolved_at: '2026-11-08T10:00:00Z',
      approvals: [{ username: 'bob', action: 'reject', comment: 'Mauvais profil', timestamp: '2026-11-08T10:00:00Z' }] })
    expect(screen.getAllByText('Refusée').length).toBeGreaterThan(0)
    expect(screen.getByText('Mauvais profil')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Approuver/ })).toBeNull()
  })

  it('lists the log, newest first', () => {
    show({ ...PROTOCOL, approvals: [{ username: 'alice', action: 'approve', comment: 'ok', timestamp: '2026-11-08T09:00:00Z' }] }, 'log')
    const items = screen.getAllByRole('listitem').map((li) => li.querySelector('strong').textContent)
    expect(items).toEqual(['Approuvée', 'Demande déposée'])
  })

  it('offers no decision without write:approvals', () => {
    stable.canWrite = false
    show(PROTOCOL)
    expect(screen.queryByRole('button', { name: /Approuver/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Refuser/ })).toBeNull()
  })

  it('approves from the inspector, then reads the request again and tells the queue', async () => {
    const onChanged = vi.fn()
    const heard = vi.fn()
    window.addEventListener('ucm:data-changed', heard)
    api.approve.mockResolvedValue({ data: { certificate_issued: false, deferred: true } })
    api.getById.mockResolvedValue({ data: { ...PROTOCOL, status: 'approved' } })
    show(PROTOCOL, 'request', { onChanged })
    fireEvent.click(screen.getByRole('button', { name: 'Approuver Enrôlement EST : device.example' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByTestId('decision-confirm'))
    await waitFor(() => expect(api.approve).toHaveBeenCalledWith(51, undefined))
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: 'approved' })))
    expect(heard.mock.calls.some(([e]) => e.detail?.type === 'approval')).toBe(true)
    window.removeEventListener('ucm:data-changed', heard)
  })
})
