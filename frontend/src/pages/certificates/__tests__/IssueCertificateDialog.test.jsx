/**
 * The issue dialog: its title follows the step, an issuance ends on a result screen that opens
 * the certificate on demand, a request held for approval says so and links to it, a CSR is
 * uploaded once and signed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
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
const result = () => screen.getByTestId('issue-result')
const button = (name) => screen.getByRole('button', { name })
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

function Where() { const l = useLocation(); return <p data-testid="where">{l.pathname + l.search}</p> }

function renderDialog(props = {}) {
  const onOpenChange = vi.fn()
  const onIssued = vi.fn()
  const onOpen = vi.fn()
  render(
    <MemoryRouter initialEntries={['/certificates']}>
      <Routes><Route path="*" element={<Where />} /></Routes>
      <IssueCertificateDialog open onOpenChange={onOpenChange} cas={CAS} onIssued={onIssued} onOpen={onOpen} {...props} />
    </MemoryRouter>,
  )
  return { onOpenChange, onIssued, onOpen }
}

describe('IssueCertificateDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.scopes = []
  })

  it('names the step in its title, ends on a result screen and opens the certificate on demand', async () => {
    mocks.create.mockResolvedValue({ data: { id: 41, cn: 'service.example.com' } })
    const { onOpenChange, onIssued, onOpen } = renderDialog()
    expect(heading()).toBe(`${P}titleIssue`)
    type(LABEL.cn, 'service.example.com')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    await screen.findByTestId('issue-review')
    expect(heading()).toBe(`${P}titleReview`)
    // The Review step gives the focus to the close button, as the Atelier does
    await waitFor(() => expect(document.activeElement).toBe(button(`${P}close`)))
    fireEvent.click(screen.getByTestId('issue-submit'))
    await screen.findByTestId('issue-result')
    expect(mocks.create.mock.calls[0][0]).toMatchObject({ ca_id: '3', cn: 'service.example.com' })
    // The list reloads at once; the dialog stays on its result, without a toast
    expect(onIssued).toHaveBeenCalledWith({ id: 41, cn: 'service.example.com' })
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(mocks.notify.showSuccess).not.toHaveBeenCalled()
    expect(heading()).toBe(`${P}result.issued.head`)
    expect(result().textContent).toContain(`${P}result.issued.title`)
    expect(button('common.close')).toBeTruthy()
    fireEvent.click(button(`${P}resultViewCertificate`))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onOpen).toHaveBeenCalledWith({ id: 41, cn: 'service.example.com' })
  })

  it('says when a policy holds the request for approval and links to the request', async () => {
    mocks.scopes = ['read:approvals']
    mocks.create.mockResolvedValue({ data: { approval_required: true, approval_id: 7, policy_name: 'Four eyes' } })
    const { onOpenChange, onIssued } = renderDialog()
    type(LABEL.cn, 'service.example.com')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    fireEvent.click(await screen.findByTestId('issue-submit'))
    await screen.findByTestId('issue-result')
    expect(heading()).toBe(`${P}result.approval.head`)
    expect(result().textContent).toContain(`${P}result.approval.copy:Four eyes`)
    expect(screen.queryByRole('button', { name: `${P}resultViewCertificate` })).toBeNull()
    expect(onIssued).not.toHaveBeenCalled()
    fireEvent.click(button(`${P}resultViewApproval`))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(screen.getByTestId('where').textContent).toBe('/approvals?id=7')
  })

  it('offers no link to the request to an operator who may not read approvals', async () => {
    mocks.create.mockResolvedValue({ data: { approval_required: true, approval_id: 7, policy_name: 'Four eyes' } })
    renderDialog()
    type(LABEL.cn, 'service.example.com')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    fireEvent.click(await screen.findByTestId('issue-submit'))
    await screen.findByTestId('issue-result')
    expect(screen.queryByRole('button', { name: `${P}resultViewApproval` })).toBeNull()
    expect(button('common.close')).toBeTruthy()
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
    await screen.findByTestId('issue-result')
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
    await screen.findByTestId('issue-result')
    expect(heading()).toBe(`${P}result.renewed.head`)
  })

  it('renews a certificate longer than the bound of a typed duration when its duration is left as is', async () => {
    mocks.renew.mockResolvedValue({ data: { id: 12 } })
    // 3 969 days: the server keeps an original duration it would refuse as a typed one
    const certificate = { id: 12, cn: 'ad.example.com', valid_from: '2016-01-01T00:00:00Z', valid_to: '2026-11-13T00:00:00Z' }
    renderDialog({ mode: 'renew', certificate, cas: undefined })
    expect(screen.getByLabelText(LABEL.days).value).toBe('3969')
    await reviewAndIssue(mocks.renew)
    expect(mocks.renew).toHaveBeenCalledWith(12, {})
  })

  it('refuses a typed renewal duration beyond the bound, even under a longer original one', async () => {
    const certificate = { id: 12, cn: 'ad.example.com', valid_from: '2016-01-01T00:00:00Z', valid_to: '2026-11-13T00:00:00Z' }
    renderDialog({ mode: 'renew', certificate, cas: undefined })
    type(LABEL.days, '3971')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    expect(await screen.findByText(`${P}validityTooLong`)).toBeTruthy()
    expect(screen.queryByTestId('issue-review')).toBeNull()
  })

  it('does not close while the request is out: Escape and the close button wait for the answer', async () => {
    let answer
    mocks.create.mockReturnValue(new Promise((resolve) => { answer = resolve }))
    const { onOpenChange } = renderDialog()
    type(LABEL.cn, 'service.example.com')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    fireEvent.click(await screen.findByTestId('issue-submit'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    fireEvent.keyDown(document.activeElement || document.body, { key: 'Escape' })
    fireEvent.click(button(`${P}close`))
    expect(onOpenChange).not.toHaveBeenCalled()
    answer({ data: { id: 41, cn: 'service.example.com' } })
    await screen.findByTestId('issue-result')
    // Once the answer is shown, Escape closes again
    fireEvent.keyDown(document.activeElement || document.body, { key: 'Escape' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
