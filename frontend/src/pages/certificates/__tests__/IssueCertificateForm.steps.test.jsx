/**
 * The issue form of the Atelier: Configure then Review, Issue only from Review, the Review
 * step reading exactly the request, the draft kept per operation, errors kept in their step.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { LABEL, P, choose, field, openAdvanced, reviewAndIssue, toReview, type } from './issueFormTestUtils'
import { DRAFT_FIELDS, keepDraft, takeDraft } from '../issue/issueDrafts'

const mocks = vi.hoisted(() => ({ getEffective: vi.fn(), decodeCsr: vi.fn(), templates: [] }))

vi.mock('../../../services', () => ({
  templatesService: {
    getAll: vi.fn(() => Promise.resolve({ data: mocks.templates })),
    getForCA: vi.fn(() => Promise.resolve({ data: mocks.templates })),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: mocks.getEffective },
  toolsService: { decodeCsr: mocks.decodeCsr },
}))

import { IssueCertificateForm } from '../IssueCertificateForm'

// Parameters show only where a test reads them
const t = (key, o) => {
  if (o && 'name' in o) return `${key}:${o.name}`
  return o && ('level' in o || 'policy' in o || 'list' in o) ? `${key}:${JSON.stringify(o)}` : key
}
const CAS = [
  { id: 1, descr: 'Root CA', has_private_key: true },
  { id: 3, descr: 'Services CA', has_private_key: true, parent_id: 1 },
]
const TEMPLATE = {
  id: 7, name: 'Serveur TLS', description: 'Services web', template_type: 'web_server', key_type: 'EC-P256',
  validity_days: 90, digest: 'sha256', dn_template: {}, enforce_san_types: true,
  extensions_template: { extended_key_usage: ['serverAuth'], san_types: ['dns', 'ip'] },
}

function renderForm(props = {}) {
  const onSubmit = props.onSubmit || vi.fn().mockResolvedValue(undefined)
  const view = render(<IssueCertificateForm cas={CAS} onCancel={() => {}} t={t} {...props} onSubmit={onSubmit} />)
  return { ...view, onSubmit }
}

const fill = () => {
  choose(LABEL.ca, '3')
  type(LABEL.cn, 'service.example.com')
}

describe('IssueCertificateForm steps', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.templates = []
    mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: null, default_key_type: 'EC-P256' } })
  })

  it('reviews before issuing: Issue exists only in the Review step, and going back keeps the entry', async () => {
    const { onSubmit } = renderForm()
    expect(screen.queryByTestId('issue-submit')).toBeNull()
    fill()
    type(new RegExp(`^${P}description`), 'Front door')
    const review = await toReview()
    expect(within(review).getByRole('heading').textContent).toBe('service.example.com')
    expect(onSubmit).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}back`) }))
    expect(field(LABEL.cn).value).toBe('service.example.com')
    expect(field(new RegExp(`^${P}description`)).value).toBe('Front door')
    expect(field(LABEL.ca).value).toBe('3')
  })

  it('names in the Review step every field of the request it sends', async () => {
    mocks.templates = [TEMPLATE]
    const { onSubmit } = renderForm()
    fill()
    await waitFor(() => expect(within(field(LABEL.template)).getAllByRole('option').map((o) => o.value)).toContain('7'))
    choose(LABEL.template, '7')
    type(new RegExp(`^${P}description`), 'Front door')
    type(`${P}sanValue`, '192.0.2.10')
    choose(`${P}sanType`, 'ip')
    openAdvanced()
    type('common.organization', 'Example')
    fireEvent.click(screen.getByLabelText('certificates.ocspMustStaple'))
    fireEvent.click(screen.getByText(`${P}eku.clientAuth`))
    fireEvent.click(screen.getByText('customExtensions.add'))
    type(`${P}extOid`, '1.3.6.1.4.1.32473.1')
    type(`${P}extValue`, '0500')
    const review = await toReview()
    const shown = review.dataset.fields.split(' ')
    fireEvent.click(screen.getByTestId('issue-submit'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const body = onSubmit.mock.calls[0][0]
    for (const key of Object.keys(body)) if (key !== 'cn') expect(shown).toContain(key)
    expect(body).toMatchObject({
      ca_id: '3', cn: 'service.example.com', description: 'Front door', organization: 'Example', template_id: 7,
      key_type: 'ecdsa', key_size: '256', validity_days: 90, san_dns: ['service.example.com'], san_ip: ['192.0.2.10'],
      ocsp_must_staple: true, extra_ekus: ['1.3.6.1.5.5.7.3.2'],
      custom_extensions: [{ oid: '1.3.6.1.4.1.32473.1', critical: false, value: '0500' }],
    })
    // What each row says is read from the same body
    expect(review.textContent).toContain('IP : 192.0.2.10')
    expect(review.textContent).toContain('Services CA')
    expect(review.textContent).toContain(`${P}caLevelUnder:{"level":2,"parent":"Root CA"}`)
    expect(review.textContent).toContain('1.3.6.1.4.1.32473.1 = 0500')
  })

  it('offers a new SAN row only the types the template allows', async () => {
    mocks.templates = [TEMPLATE]
    renderForm()
    fill()
    await waitFor(() => expect(within(field(LABEL.template)).getAllByRole('option').map((o) => o.value)).toContain('7'))
    choose(LABEL.template, '7')
    expect(within(field(`${P}sanType`)).getAllByRole('option').map((o) => o.value)).toEqual(['dns', 'ip'])
  })

  it('keeps the entry and shows the refusal in the Review step when the API refuses', async () => {
    const onSubmit = vi.fn().mockRejectedValueOnce(new Error('CA is offline; restore it before issuing'))
      .mockResolvedValueOnce(undefined)
    renderForm({ onSubmit })
    fill()
    await reviewAndIssue(onSubmit)
    expect((await screen.findByRole('alert')).textContent).toContain('CA is offline')
    expect(screen.getByTestId('issue-submit')).not.toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}back`) }))
    expect(field(LABEL.cn).value).toBe('service.example.com')
    await reviewAndIssue(onSubmit)
    expect(onSubmit).toHaveBeenCalledTimes(2)
  })

  it('says in the Review step that the request now waits for approval', async () => {
    const onSubmit = vi.fn().mockResolvedValue({ approval: 'Four eyes' })
    renderForm({ onSubmit })
    fill()
    await reviewAndIssue(onSubmit)
    expect((await screen.findByTestId('approval-sent')).textContent).toContain('"policy":"Four eyes"')
    expect(screen.queryByTestId('issue-submit')).toBeNull()
  })

  it('keeps the draft of a form closed without issuing and offers it at the next opening', async () => {
    const { unmount } = renderForm()
    fill()
    unmount()
    const { unmount: again } = renderForm()
    expect(screen.getByTestId('draft-note')).toBeTruthy()
    expect(field(LABEL.cn).value).toBe('service.example.com')
    fireEvent.click(screen.getByText(`${P}draftReset`))
    expect(field(LABEL.cn).value).toBe('')
    expect(screen.queryByTestId('draft-note')).toBeNull()
    again()
    renderForm()
    expect(screen.queryByTestId('draft-note')).toBeNull()
  })

  it('keeps no draft once the request went out', async () => {
    const { onSubmit, unmount } = renderForm()
    fill()
    await reviewAndIssue(onSubmit)
    unmount()
    renderForm()
    expect(screen.queryByTestId('draft-note')).toBeNull()
    expect(field(LABEL.cn).value).toBe('')
  })

  it('keeps one draft per operation', async () => {
    const certificate = { id: 12, cn: 'old.example.com', valid_from: '2026-01-01T00:00:00Z', valid_to: '2026-04-01T00:00:00Z' }
    const { unmount } = renderForm({ mode: 'renew', certificate })
    type(LABEL.days, '30')
    unmount()
    renderForm()
    expect(screen.queryByTestId('draft-note')).toBeNull()
    expect(takeDraft('renew:12')).toMatchObject({ validity_days: '30' })
  })

  it('never keeps a private key or a password in a draft', () => {
    keepDraft('issue', { cn: 'a.example.com', private_key: '-----BEGIN PRIVATE KEY-----', password: 'secret', passphrase: 'x' })
    const kept = takeDraft('issue')
    expect(kept).toEqual({ cn: 'a.example.com' })
    expect(DRAFT_FIELDS.some((f) => /key_pem|private|password|passphrase/i.test(f))).toBe(false)
  })

  it('renews in two steps: only the duration can change, and an unchanged one is not sent', async () => {
    const certificate = {
      id: 12, cn: 'old.example.com', issuer_name: 'Services CA', key_algorithm: 'ECDSA P-256',
      valid_from: '2026-01-01T00:00:00Z', valid_to: '2026-04-01T00:00:00Z', san_dns: '["old.example.com"]',
    }
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    renderForm({ mode: 'renew', certificate, onSubmit })
    expect(field(LABEL.cn).readOnly).toBe(true)
    expect(field(LABEL.days).value).toBe('90')
    expect(await reviewAndIssue(onSubmit)).toEqual({})
    expect(onSubmit.mock.calls[0][1]).toMatchObject({ kind: 'renew' })
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}back`) }))
    type(LABEL.days, '30')
    const review = await toReview()
    expect(review.textContent).toContain('DNS : old.example.com')
    fireEvent.click(screen.getByTestId('issue-submit'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2))
    expect(onSubmit.mock.calls[1][0]).toEqual({ validity_days: 30 })
  })

  it('signs a provided CSR: the card shows for an operator who may, the CSR is read before the review', async () => {
    mocks.decodeCsr.mockResolvedValue({ data: { subject: 'CN=device.example.com, O=Example', public_key: { type: 'ECDSA', curve: 'secp256r1' } } })
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    renderForm({ onSubmit, canUseCsr: true })
    choose(LABEL.ca, '3')
    fireEvent.click(screen.getByLabelText(new RegExp(`${P}keyCsr`)))
    type(`${P}csr`, 'not a csr')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    expect(await screen.findByText(`${P}csrInvalid`)).toBeTruthy()
    type(`${P}csr`, '-----BEGIN CERTIFICATE REQUEST-----\nMIIB\n-----END CERTIFICATE REQUEST-----')
    const review = await toReview()
    expect(within(review).getByRole('heading').textContent).toBe('device.example.com')
    fireEvent.click(screen.getByTestId('issue-submit'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const [body, info] = onSubmit.mock.calls[0]
    expect(info).toMatchObject({ kind: 'csr', csr: expect.stringContaining('BEGIN CERTIFICATE REQUEST') })
    expect(body).not.toHaveProperty('key_type')
    expect(body).not.toHaveProperty('cn')
    for (const key of Object.keys(body)) expect(review.dataset.fields.split(' ')).toContain(key)
  })

  it('offers no CSR card to an operator who may not upload one', () => {
    renderForm()
    expect(screen.queryByLabelText(new RegExp(`${P}keyCsr`))).toBeNull()
  })

  it('says in its column what the template and the policies impose, nothing more', async () => {
    mocks.templates = [TEMPLATE]
    mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: ['EC-P256', 'EC-P384'], allowed_digests: ['sha384'], default_key_type: 'EC-P256' } })
    renderForm()
    choose(LABEL.ca, '3')
    await waitFor(() => expect(screen.getByTestId('hint-algorithms').textContent).toBe('ECDSA P-256, ECDSA P-384'))
    await waitFor(() => expect(within(field(LABEL.template)).getAllByRole('option').map((o) => o.value)).toContain('7'))
    choose(LABEL.template, '7')
    const hint = screen.getByTestId('issue-hint')
    expect(hint.textContent).toContain('Serveur TLS')
    expect(hint.textContent).toContain('DNS, IP')
    expect(hint.textContent).toContain('SHA-256')
    expect(hint.textContent).toContain(`${P}hintDigestsAllowed:{"list":"SHA-384"}`)
    // No CSR row without the right to hand one in
    expect(hint.textContent).not.toContain(`${P}hintCsr`)
  })

  it('takes an end date instead of a duration and sends the days it makes', async () => {
    const { onSubmit } = renderForm()
    fill()
    fireEvent.click(screen.getByRole('button', { name: `${P}useDate` }))
    const end = new Date(Date.now() + 10 * 86400000).toISOString().split('T')[0]
    type(`${P}validityDate`, end)
    const body = await reviewAndIssue(onSubmit)
    expect(body.validity_days).toBeGreaterThanOrEqual(9)
    expect(body.validity_days).toBeLessThanOrEqual(11)
  })

  it('unfolds Advanced when an extension is in error, also behind an earlier error', async () => {
    renderForm()
    fill()
    openAdvanced()
    fireEvent.click(screen.getByText('customExtensions.add'))
    fireEvent.click(screen.getByText('customExtensions.add'))
    const [oid0, oid1] = screen.getAllByLabelText(`${P}extOid`)
    const values = screen.getAllByLabelText(`${P}extValue`)
    fireEvent.change(oid0, { target: { value: 'not.an.oid' } })
    fireEvent.change(oid1, { target: { value: '1.3.6.1.4.1.32473.1' } })
    openAdvanced()
    type(LABEL.days, '0')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    await waitFor(() => expect(document.activeElement).toBe(field(LABEL.days)))
    expect(screen.getByRole('button', { name: new RegExp(`${P}advanced`) }).getAttribute('aria-expanded')).toBe('true')
    expect(oid0.getAttribute('aria-invalid')).toBe('true')
    // An empty value is marked on the value, not on its OID
    expect(oid1.getAttribute('aria-invalid')).toBeNull()
    expect(values[1].getAttribute('aria-invalid')).toBe('true')
  })

  it('focuses the first field in error and marks it invalid', async () => {
    renderForm()
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    await waitFor(() => expect(document.activeElement).toBe(field(LABEL.ca)))
    expect(field(LABEL.ca).getAttribute('aria-invalid')).toBe('true')
    expect(field(LABEL.cn).getAttribute('aria-invalid')).toBe('true')
    expect(screen.getByRole('status').textContent).toBe(`${P}fixErrors`)
  })
})
