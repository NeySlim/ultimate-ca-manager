/**
 * #373: a template's subject Email prefills the subject Email field (Advanced)
 * (skipped when it is the literal `{email}` placeholder), and per the
 * documented behaviour, on an email/combined cert that Email also becomes a
 * SAN via getAutoSansFromCn.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { LABEL, P, choose, field, optionValues, reviewAndIssue, type } from '../certificates/__tests__/issueFormTestUtils'

const REAL_EMAIL_TEMPLATE = {
  id: 1, name: 'Real Email Template', template_type: 'email',
  validity_days: 365, dn_template: { emailAddress: 'pki@example.com' },
  extensions_template: { extended_key_usage: ['emailProtection'] },
}
const PLACEHOLDER_TEMPLATE = {
  id: 2, name: 'Placeholder Email Template', template_type: 'email',
  validity_days: 365, dn_template: { emailAddress: '{email}' },
  extensions_template: { extended_key_usage: ['emailProtection'] },
}

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [REAL_EMAIL_TEMPLATE, PLACEHOLDER_TEMPLATE] }),
    getForCA: vi.fn().mockResolvedValue({ data: [REAL_EMAIL_TEMPLATE, PLACEHOLDER_TEMPLATE] }),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn() }),
}))

const t = (key) => key
const CAS = [{ id: 1, descr: 'Test CA', subject: 'CN=Test CA', has_private_key: true }]

async function renderWithTemplate(id, onSubmit = vi.fn().mockResolvedValue(undefined)) {
  const { IssueCertificateForm } = await import('../certificates/IssueCertificateForm')
  render(<IssueCertificateForm cas={CAS} onSubmit={onSubmit} onCancel={() => {}} t={t} />)
  choose(LABEL.ca, '1')
  await waitFor(() => expect(optionValues(LABEL.template)).toContain(String(id)))
  choose(LABEL.template, String(id))
  return onSubmit
}

describe('IssueCertificateForm template Email prefill (#373)', () => {
  it('case 6a: a real template email fills the subject Email field and opens Advanced', async () => {
    await renderWithTemplate(1)
    await waitFor(() => expect(field('common.email').value).toBe('pki@example.com'))
    expect(field('common.email').closest('[hidden]')).toBeNull()
  }, 15000)

  it('case 6b: a {email} placeholder template leaves the subject Email field empty', async () => {
    await renderWithTemplate(2)
    await waitFor(() => expect(field(`${P}template`).value).toBe('2'))
    expect(field('common.email').value).toBe('')
  }, 15000)

  it('case 7: the template Email also lands as a SAN on the submitted payload', async () => {
    const onSubmit = await renderWithTemplate(1)
    type(LABEL.cn, 'someone@example.test')
    const payload = await reviewAndIssue(onSubmit)
    expect(payload.email).toBe('pki@example.com')
    expect(payload.san_email).toContain('pki@example.com')
  }, 15000)
})
