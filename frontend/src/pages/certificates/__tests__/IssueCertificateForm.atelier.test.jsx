/**
 * The issue form measured against the Atelier: what it chooses by itself at the opening, what a
 * template keeps of the user's entry, where the focus goes on rows, the renewal as the same form,
 * and the Review rows in the Atelier's order.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { LABEL, P, choose, field, optionValues, toReview, type } from './issueFormTestUtils'

const mocks = vi.hoisted(() => ({ templates: [], getEffective: vi.fn() }))

vi.mock('../../../services', () => ({
  templatesService: {
    getAll: vi.fn(() => Promise.resolve({ data: mocks.templates })),
    getForCA: vi.fn(() => Promise.resolve({ data: mocks.templates })),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: mocks.getEffective },
  toolsService: { decodeCsr: vi.fn() },
}))

import { IssueCertificateForm } from '../IssueCertificateForm'

const t = (key, o) => (o && Object.keys(o).length ? `${key}:${JSON.stringify(o)}` : key)
const soon = new Date(Date.now() + 100 * 86400000).toISOString()
const CAS = [
  { id: 1, descr: 'Root CA', has_private_key: true },
  { id: 3, descr: 'Services CA', has_private_key: true, parent_id: 1 },
  { id: 5, descr: 'Short CA', has_private_key: true, parent_id: 1, valid_to: soon },
]
const TLS = { id: 7, name: 'Serveur TLS', template_type: 'web_server', validity_days: 90, dn_template: { O: 'Example' }, extensions_template: {} }
const CLIENT = { id: 8, name: 'Client TLS', template_type: 'client_auth', validity_days: 30, dn_template: {}, extensions_template: {} }

const renderForm = (props = {}) => {
  const onSubmit = props.onSubmit || vi.fn().mockResolvedValue(undefined)
  render(<IssueCertificateForm cas={CAS} onCancel={() => {}} t={t} {...props} onSubmit={onSubmit} />)
  return onSubmit
}
const advancedToggle = () => screen.getByRole('button', { name: new RegExp(`${P}advanced`) })
const announced = () => screen.getByRole('status').textContent

describe('IssueCertificateForm against the Atelier', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.templates = []
    mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: null, default_key_type: 'RSA-2048' } })
  })

  it('leaves the authority to choose when there are several', async () => {
    renderForm()
    expect(field(LABEL.ca).value).toBe('')
    expect(optionValues(LABEL.ca)[0]).toBe('')
  })

  it('chooses the only authority and the only template, and keeps no draft for them', async () => {
    mocks.templates = [TLS]
    render(<IssueCertificateForm cas={[CAS[1]]} onCancel={() => {}} t={t} onSubmit={vi.fn()} />)
    await waitFor(() => expect(field(LABEL.template).value).toBe('7'))
    expect(field(LABEL.ca).value).toBe('3')
    expect(field(LABEL.days).value).toBe('90')
  })

  it('takes the authority the opening names', () => {
    renderForm({ initialData: { ca_id: 3 } })
    expect(field(LABEL.ca).value).toBe('3')
  })

  it('keeps Advanced folded when a template fills its subject, and says so on the folded line', async () => {
    mocks.templates = [TLS]
    renderForm()
    choose(LABEL.ca, '3')
    await waitFor(() => expect(optionValues(LABEL.template)).toContain('7'))
    choose(LABEL.template, '7')
    expect(advancedToggle().getAttribute('aria-expanded')).toBe('false')
    expect(advancedToggle().textContent).toContain(`${P}advancedHintTemplate`)
    expect(field('common.organization').value).toBe('Example')
  })

  it('keeps a validity the user typed through a template change, and says it', async () => {
    mocks.templates = [TLS, CLIENT]
    renderForm()
    choose(LABEL.ca, '3')
    await waitFor(() => expect(optionValues(LABEL.template)).toContain('7'))
    type(LABEL.days, '60')
    choose(LABEL.template, '7')
    expect(field(LABEL.days).value).toBe('60')
    expect(announced()).toContain(`${P}keptValidity`)
    // Back to no template: its subject leaves with it, the type returns to the default
    choose(LABEL.template, '')
    expect(field('common.organization').value).toBe('')
    expect(field(LABEL.certType).value).toBe('server')
  })

  it('follows the template validity until the user types one', async () => {
    mocks.templates = [TLS, CLIENT]
    renderForm()
    choose(LABEL.ca, '3')
    await waitFor(() => expect(optionValues(LABEL.template)).toContain('8'))
    choose(LABEL.template, '8')
    expect(field(LABEL.days).value).toBe('30')
    choose(LABEL.template, '7')
    expect(field(LABEL.days).value).toBe('90')
  })

  it('brings a typed validity down to what the chosen authority allows, and says so', () => {
    renderForm()
    type(LABEL.days, '300')
    choose(LABEL.ca, '5')
    const max = Number(field(LABEL.days).value)
    expect(max).toBeGreaterThanOrEqual(98)
    expect(max).toBeLessThanOrEqual(100)
    expect(announced()).toContain(`${P}validityFitted`)
    // Too long against that authority: the message names it
    type(LABEL.days, String(max + 5))
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    expect(screen.getByText(new RegExp(`${P}validityTooLongCa`))).toBeTruthy()
    expect(announced()).toBe(`${P}fixErrors:{"count":2}`)
  })

  it('gives the focus to a new SAN row, then to its neighbour or the add button on removal', async () => {
    renderForm()
    fireEvent.click(screen.getByRole('button', { name: `${P}addSan` }))
    const values = screen.getAllByLabelText(new RegExp(`${P}sanValue`))
    await waitFor(() => expect(document.activeElement).toBe(values[1]))
    fireEvent.click(screen.getAllByRole('button', { name: new RegExp(`${P}removeSan`) })[1])
    await waitFor(() => expect(document.activeElement).toBe(screen.getAllByLabelText(new RegExp(`${P}sanValue`))[0]))
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}removeSan`) }))
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: `${P}addSan` })))
  })

  it('offers the pinned templates and the full list in the list itself', async () => {
    mocks.templates = [{ ...TLS, is_pinned: true }, CLIENT]
    renderForm()
    choose(LABEL.ca, '3')
    await waitFor(() => expect(optionValues(LABEL.template)).toEqual(['', '7', '__pins__']))
    choose(LABEL.template, '__pins__')
    expect(optionValues(LABEL.template)).toEqual(['', '7', '8', '__pins__'])
    expect(field(LABEL.template).value).toBe('')
  })

  it('refuses a custom extension UCM sets itself, on its OID', async () => {
    renderForm()
    choose(LABEL.ca, '3')
    type(LABEL.cn, 'service.example.com')
    fireEvent.click(advancedToggle())
    fireEvent.click(screen.getByText('customExtensions.add'))
    type(new RegExp(`${P}extOid`), '2.5.29.17')
    type(new RegExp(`${P}extValue`), '0500')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    expect(screen.getByText(new RegExp(`${P}extOidReserved`))).toBeTruthy()
  })

  it('names a SAN error with the words of its type', () => {
    renderForm()
    choose(LABEL.ca, '3')
    type(LABEL.cn, 'service.example.com')
    type(new RegExp(`${P}sanValue`), 'bad host!')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    expect(screen.getByText(`${P}sanInvalid.dns`)).toBeTruthy()
  })

  it('reads the Review rows in the Atelier order, the subject and the type after Advanced', async () => {
    mocks.templates = [TLS]
    renderForm()
    choose(LABEL.ca, '3')
    await waitFor(() => expect(optionValues(LABEL.template)).toContain('7'))
    choose(LABEL.template, '7')
    type(LABEL.cn, 'service.example.com')
    fireEvent.click(advancedToggle())
    fireEvent.click(screen.getByText(`${P}eku.clientAuth`))
    const review = await toReview()
    const ids = [...review.querySelectorAll('[data-row]')].map((r) => r.dataset.row)
    expect(ids).toEqual(['operation', 'template', 'ca', 'description', 'keySource', 'key', 'validity', 'sans', 'advanced', 'subject', 'ekus'])
    const ekus = review.querySelector('[data-row="ekus"]')
    expect(within(ekus).getByText(`${P}ekuRow`)).toBeTruthy()
    // Every EKU by its name: the template's and the added one
    expect(ekus.textContent).toContain(`${P}eku.serverAuth`)
    expect(ekus.textContent).toContain(`${P}eku.clientAuth`)
    expect(review.querySelector('[data-row="advanced"]').textContent).toContain(`${P}advancedChanged`)
  })
})

describe('IssueCertificateForm renewal', () => {
  const CERT = {
    id: 12, cn: 'fw.lan', issuer_name: 'Services CA', caref: 'svc', key_algorithm: 'RSA', key_type: 'RSA 2048',
    descr: 'Web GUI', signature_algorithm: 'SHA256-RSA', cert_type: 'server_cert', organization: 'Example',
    valid_from: '2026-01-01T00:00:00Z', valid_to: '2026-04-01T00:00:00Z', san_dns: '["fw.lan"]', san_ip: '["192.0.2.1"]',
  }

  beforeEach(() => vi.clearAllMocks())

  it('is the issue form, the values it cannot change shown read-only', () => {
    render(<IssueCertificateForm mode="renew" certificate={CERT} cas={[{ ...CAS[1], refid: 'svc' }, CAS[0]]}
      onCancel={() => {}} t={t} onSubmit={vi.fn()} />)
    for (const label of [LABEL.template, LABEL.ca, LABEL.cn, LABEL.key]) {
      expect(field(label).readOnly).toBe(true)
      expect(field(label).disabled).toBe(false)
    }
    // The whole algorithm, never its family alone
    expect(field(LABEL.key).value).toBe('RSA 2048')
    expect(field(new RegExp(`^${P}description`)).value).toBe('Web GUI')
    expect(screen.getAllByLabelText(new RegExp(`${P}sanValue`)).map((i) => i.value)).toEqual(['fw.lan', '192.0.2.1'])
    expect(screen.queryByRole('button', { name: `${P}addSan` })).toBeNull()
    expect(field(LABEL.days).readOnly).toBe(false)
    expect(screen.getByLabelText(new RegExp(`${P}keyCsr`)).disabled).toBe(true)
    expect(advancedToggle().getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(advancedToggle())
    expect(field(`${P}hash`).value).toBe('SHA-256')
    expect(field('common.organization').value).toBe('Example')
    const hint = screen.getByTestId('issue-hint')
    expect(hint.textContent).toContain('RSA 2048')
    expect(hint.textContent).toContain(`${P}hintCsrRenew`)
  })

  it('reviews the renewal with its description, the issuer level and the end date', async () => {
    render(<IssueCertificateForm mode="renew" certificate={CERT} cas={[{ ...CAS[1], refid: 'svc' }, CAS[0]]}
      onCancel={() => {}} t={t} onSubmit={vi.fn()} />)
    const review = await toReview()
    expect(review.querySelector('[data-row="description"]').textContent).toContain('Web GUI')
    expect(review.querySelector('[data-row="ca"]').textContent).toContain(`${P}caLevelUnder`)
    expect(review.querySelector('[data-row="key"]').textContent).toContain('RSA 2048')
    expect(review.querySelector('[data-row="validity"]').textContent).toContain(`${P}validityUntil`)
  })
})
