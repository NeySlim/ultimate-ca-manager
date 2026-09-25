/**
 * #373: a template's subject Email now prefills the Subject Details field
 * (skipped when it is the literal `{email}` placeholder), and per the
 * documented behaviour, on an email/combined cert that Email also becomes a
 * SAN via getAutoSansFromCn.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

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

beforeAll(() => {
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
  Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {})
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {})
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
})

const t = (key) => key

const selectTemplate = async (user, container, name) => {
  const templateTrigger = container.querySelectorAll('[role="combobox"]')[0]
  await user.click(templateTrigger)
  await user.click(await screen.findByRole('option', { name }))
}

const openSubjectDetails = async (user) => {
  await user.click(screen.getByText('certificates.subjectDetails'))
}

describe('IssueCertificateForm template Email prefill (#373)', () => {
  it('case 6a: a real template email fills the subject Email field', async () => {
    const { IssueCertificateForm } = await import('../certificates/IssueCertificateForm')
    const user = userEvent.setup()
    const { container } = render(
      <IssueCertificateForm cas={[{ id: 1, descr: 'Test CA', subject: 'CN=Test CA' }]} onSubmit={vi.fn()} onCancel={() => {}} t={t} />
    )

    await screen.findByText('certificates.templateOptional')
    // Selecting a template with a real subject email auto-opens the section.
    await selectTemplate(user, container, 'Real Email Template')

    const emailInput = await screen.findByPlaceholderText('certificates.emailPlaceholder')
    expect(emailInput.value).toBe('pki@example.com')
  }, 15000)

  it('case 6b: a {email} placeholder template leaves the subject Email field empty', async () => {
    const { IssueCertificateForm } = await import('../certificates/IssueCertificateForm')
    const user = userEvent.setup()
    const { container } = render(
      <IssueCertificateForm cas={[{ id: 1, descr: 'Test CA', subject: 'CN=Test CA' }]} onSubmit={vi.fn()} onCancel={() => {}} t={t} />
    )

    await screen.findByText('certificates.templateOptional')
    await openSubjectDetails(user)
    await selectTemplate(user, container, 'Placeholder Email Template')

    const emailInput = await screen.findByPlaceholderText('certificates.emailPlaceholder')
    expect(emailInput.value).toBe('')
  }, 15000)

  it('case 7: the template Email also lands as a SAN on the submitted payload', async () => {
    const { IssueCertificateForm } = await import('../certificates/IssueCertificateForm')
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const { container } = render(
      <IssueCertificateForm cas={[{ id: 1, descr: 'Test CA', subject: 'CN=Test CA' }]} onSubmit={onSubmit} onCancel={() => {}} t={t} />
    )

    await screen.findByText('certificates.templateOptional')
    await selectTemplate(user, container, 'Real Email Template')

    await user.type(screen.getByPlaceholderText('certificates.sanEmailPlaceholder'), 'someone@example.test')
    await user.click(container.querySelector('button[type="submit"]'))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const payload = onSubmit.mock.calls[0][0]
    expect(payload.email).toBe('pki@example.com')
    expect(payload.san_email).toContain('pki@example.com')
  }, 15000)
})
