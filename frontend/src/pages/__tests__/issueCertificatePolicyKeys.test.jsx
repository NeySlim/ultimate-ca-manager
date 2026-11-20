/**
 * The issue form offers only the key types the policies of the selected CA and
 * template allow (#397), and falls back to the first allowed one.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ getEffective: vi.fn() }))

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getForCA: vi.fn().mockResolvedValue({ data: [] }),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: mocks.getEffective },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn() }),
}))

import { IssueCertificateForm } from '../certificates/IssueCertificateForm'
import { LABEL, choose, field, optionValues, reviewAndIssue, type } from '../certificates/__tests__/issueFormTestUtils'

const t = (key) => key

function renderForm(effective, onSubmit = vi.fn().mockResolvedValue(undefined)) {
  mocks.getEffective.mockResolvedValue({ data: effective })
  render(
    <IssueCertificateForm
      cas={[{ id: 3, descr: 'Issuing CA', has_private_key: true }]}
      onSubmit={onSubmit} onCancel={() => {}} t={t}
    />
  )
  choose(LABEL.ca, '3')
  return onSubmit
}

describe('IssueCertificateForm policy key types (#397)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps every key type when the policies do not restrict them', async () => {
    renderForm({ allowed_key_types: null, allowed_digests: null, default_key_type: 'RSA-2048' })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalledWith({ ca_id: '3', template_id: undefined }))
    await waitFor(() => expect(field(LABEL.key).value).toBe('RSA-2048'))
    expect(optionValues(LABEL.key)).toEqual(['RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521',
      'EC-BP256', 'EC-BP384', 'EC-BP512', 'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87'])
  })

  it('switches to the first allowed key and submits it', async () => {
    const onSubmit = renderForm({ allowed_key_types: ['RSA-4096', 'EC-P384'], allowed_digests: null })
    await waitFor(() => expect(optionValues(LABEL.key)).toEqual(['RSA-4096', 'EC-P384']))
    await waitFor(() => expect(field(LABEL.key).value).toBe('RSA-4096'))
    choose(LABEL.key, 'EC-P384')
    type(LABEL.cn, 'host.example.test')
    expect(await reviewAndIssue(onSubmit)).toMatchObject({ key_type: 'ecdsa', key_size: '384' })
  })

  it('says so and blocks the review when no key type is allowed', async () => {
    const onSubmit = vi.fn()
    renderForm({ allowed_key_types: ['ED25519'], allowed_digests: null }, onSubmit)
    expect(await screen.findAllByText('certificates.noKeyTypeAllowedByPolicy')).toBeTruthy()
    // The list and its hint say it too: no server default is offered that the policies refuse
    expect(optionValues(LABEL.key)).toEqual([''])
    expect(field(LABEL.key).value).toBe('')
    expect(screen.getAllByText('certificates.issueForm.hintAlgorithmsNone').length).toBeGreaterThanOrEqual(2)
    type(LABEL.cn, 'host.example.test')
    fireEvent.click(screen.getByRole('button', { name: /issueForm.toReview/ }))
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByTestId('issue-review')).toBeNull()
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
