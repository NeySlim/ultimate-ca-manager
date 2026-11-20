/**
 * The issue dialog: its title follows the step, an issuance closes it and opens the result,
 * a request held for approval stays in the Review step, a CSR is uploaded once and signed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LABEL, P, choose, reviewAndIssue, type } from './issueFormTestUtils'

const mocks = vi.hoisted(() => ({
  create: vi.fn(), renew: vi.fn(), upload: vi.fn(), sign: vi.fn(), decodeCsr: vi.fn(),
  notify: { showSuccess: vi.fn(), showWarning: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() },
  scopes: [],
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, o) => (o?.policy ? `${key}:${o.policy}` : key) }),
}))
vi.mock('../../../contexts', () => ({ useNotification: () => mocks.notify }))
vi.mock('../../../hooks', () => ({ usePermission: () => ({ hasPermission: (s) => mocks.scopes.includes(s) }) }))
vi.mock('../../../services', () => ({
  certificatesService: { create: mocks.create, renew: mocks.renew },
  csrsService: { upload: mocks.upload, sign: mocks.sign },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }), getForCA: vi.fn().mockResolvedValue({ data: [] }) },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: vi.fn().mockResolvedValue({ data: { allowed_key_types: null } }) },
  toolsService: { decodeCsr: mocks.decodeCsr },
}))

import { IssueCertificateDialog } from '../IssueCertificateDialog'

const CAS = [{ id: 3, descr: 'Services CA', has_private_key: true }]
const heading = () => screen.getByRole('heading', { level: 2 }).textContent

function renderDialog(props = {}) {
  const onOpenChange = vi.fn()
  const onIssued = vi.fn()
  render(<IssueCertificateDialog open onOpenChange={onOpenChange} cas={CAS} onIssued={onIssued} {...props} />)
  return { onOpenChange, onIssued }
}

describe('IssueCertificateDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.scopes = []
  })

  it('names the step in its title, closes after an issuance and hands over the certificate', async () => {
    mocks.create.mockResolvedValue({ data: { id: 41, cn: 'service.example.com' } })
    const { onOpenChange, onIssued } = renderDialog()
    expect(heading()).toBe(`${P}titleIssue`)
    choose(LABEL.ca, '3')
    type(LABEL.cn, 'service.example.com')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    await screen.findByTestId('issue-review')
    expect(heading()).toBe(`${P}titleReview`)
    fireEvent.click(screen.getByTestId('issue-submit'))
    await waitFor(() => expect(onIssued).toHaveBeenCalledWith({ id: 41, cn: 'service.example.com' }))
    expect(mocks.create.mock.calls[0][0]).toMatchObject({ ca_id: '3', cn: 'service.example.com' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(mocks.notify.showSuccess).toHaveBeenCalledWith('messages.success.create.certificate')
  })

  it('stays open in the Review step when a policy holds the request for approval', async () => {
    mocks.create.mockResolvedValue({ data: { approval_required: true, approval_id: 7, policy_name: 'Four eyes' } })
    const { onOpenChange, onIssued } = renderDialog()
    choose(LABEL.ca, '3')
    type(LABEL.cn, 'service.example.com')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    fireEvent.click(await screen.findByTestId('issue-submit'))
    expect((await screen.findByTestId('approval-sent')).textContent).toContain('Four eyes')
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(onIssued).not.toHaveBeenCalled()
  })

  it('uploads a CSR once and signs it, also when a refused signature is tried again', async () => {
    mocks.scopes = ['write:csrs']
    mocks.decodeCsr.mockResolvedValue({ data: { subject: 'CN=device.example.com' } })
    mocks.upload.mockResolvedValue({ data: { id: 55 } })
    mocks.sign.mockRejectedValueOnce(new Error('Policy refuses RSA-1024')).mockResolvedValueOnce({ data: { id: 56 } })
    const { onIssued } = renderDialog()
    choose(LABEL.ca, '3')
    fireEvent.click(screen.getByLabelText(new RegExp(`${P}keyCsr`)))
    type(`${P}csr`, '-----BEGIN CERTIFICATE REQUEST-----\nMIIB\n-----END CERTIFICATE REQUEST-----')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    fireEvent.click(await screen.findByTestId('issue-submit'))
    expect((await screen.findByRole('alert')).textContent).toContain('Policy refuses RSA-1024')
    fireEvent.click(screen.getByTestId('issue-submit'))
    await waitFor(() => expect(onIssued).toHaveBeenCalledWith({ id: 56 }))
    expect(mocks.upload).toHaveBeenCalledTimes(1)
    expect(mocks.sign).toHaveBeenCalledTimes(2)
    expect(mocks.sign.mock.calls[1].slice(0, 4)).toEqual([55, '3', 365, 'server'])
  })

  it('renews: the title says so and only the duration travels', async () => {
    mocks.renew.mockResolvedValue({ data: { id: 12 } })
    const certificate = { id: 12, cn: 'old.example.com', valid_from: '2026-01-01T00:00:00Z', valid_to: '2026-04-01T00:00:00Z' }
    const { onIssued } = renderDialog({ mode: 'renew', certificate, cas: undefined })
    expect(heading()).toBe(`${P}titleRenew`)
    type(LABEL.days, '30')
    await reviewAndIssue(mocks.renew)
    expect(mocks.renew).toHaveBeenCalledWith(12, { validity_days: 30 })
    await waitFor(() => expect(onIssued).toHaveBeenCalled())
    expect(mocks.notify.showSuccess).toHaveBeenCalledWith('certificates.renewed')
  })
})
