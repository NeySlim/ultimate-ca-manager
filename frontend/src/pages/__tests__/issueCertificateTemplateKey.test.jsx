/**
 * #318: selecting an EC certificate template must carry its curve into the
 * issue form.
 * The template's key and a key picked by hand both reach the request as a full
 * pair (key_type and key_size), never a type with an empty size.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { LABEL, choose, optionValues, reviewAndIssue, type } from '../certificates/__tests__/issueFormTestUtils'

const EC_TEMPLATE = {
  id: 1,
  name: 'EC Web Server',
  template_type: 'web_server',
  key_type: 'EC-P256',
  validity_days: 397,
  dn_template: {},
  extensions_template: { extended_key_usage: ['serverAuth'] },
}

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [EC_TEMPLATE] }),
    getForCA: vi.fn().mockResolvedValue({ data: [EC_TEMPLATE] }),
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

describe('IssueCertificateForm EC template key size (#318)', () => {
  const CAS = [{ id: 1, descr: 'Test CA', subject: 'CN=Test CA', has_private_key: true }]

  it('carries the template curve into the submitted payload', async () => {
    const { IssueCertificateForm } = await import('../certificates/IssueCertificateForm')
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<IssueCertificateForm cas={CAS} onSubmit={onSubmit} onCancel={() => {}} t={t} />)
    choose(LABEL.ca, '1')
    await waitFor(() => expect(optionValues(LABEL.template)).toContain('1'))
    choose(LABEL.template, '1')
    type(LABEL.cn, 'ec-host.example.test')
    const payload = await reviewAndIssue(onSubmit)
    expect(payload.key_type).toBe('ecdsa')
    expect(payload.key_size).toBe('256')
    expect(payload.validity_days).toBe(397)
  }, 15000)

  it('sends a full pair for a key picked by hand', async () => {
    const { IssueCertificateForm } = await import('../certificates/IssueCertificateForm')
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<IssueCertificateForm cas={CAS} onSubmit={onSubmit} onCancel={() => {}} t={t} />)
    choose(LABEL.ca, '1')
    choose(LABEL.key, 'EC-P256')
    type(LABEL.cn, 'manual-ec.example.test')
    const payload = await reviewAndIssue(onSubmit)
    expect(payload.key_type).toBe('ecdsa')
    expect(payload.key_size).toBe('256')
  }, 15000)
})
