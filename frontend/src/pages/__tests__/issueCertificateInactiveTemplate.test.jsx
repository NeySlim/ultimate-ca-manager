/**
 * A deactivated template, a system one included, is not offered by the issue
 * form (#430 follow-up).
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const TEMPLATES = [
  { id: 1, name: 'Web Server', template_type: 'web_server', is_system: true, is_active: true, key_type: 'RSA-2048', dn_template: {}, extensions_template: {} },
  { id: 2, name: 'Code Signing', template_type: 'code_signing', is_system: true, is_active: false, key_type: 'RSA-2048', dn_template: {}, extensions_template: {} },
]

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn().mockResolvedValue({ data: TEMPLATES }),
    getForCA: vi.fn().mockResolvedValue({ data: TEMPLATES }),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn() }),
}))

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
  Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {})
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {})
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
})

describe('IssueCertificateForm deactivated templates', () => {
  it('offers the active template only', async () => {
    const { IssueCertificateForm } = await import('../certificates/IssueCertificateForm')
    const user = userEvent.setup()
    const { container } = render(
      <IssueCertificateForm cas={[{ id: 1, descr: 'Test CA', has_private_key: true }]}
        onSubmit={vi.fn()} onCancel={() => {}} t={(key) => key} />
    )
    await screen.findByText('certificates.templateOptional')
    await user.click(container.querySelectorAll('[role="combobox"]')[0])
    expect(await screen.findByRole('option', { name: 'Web Server' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Code Signing' })).toBeNull()
  }, 15000)
})
