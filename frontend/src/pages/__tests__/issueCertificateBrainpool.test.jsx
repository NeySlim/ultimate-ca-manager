/**
 * The issue form offers the Brainpool curves with a compatibility notice, maps a
 * Brainpool template onto them, and drops them in FIPS mode (phase 4.4).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ getEffective: vi.fn(), getAll: vi.fn(), getForCA: vi.fn() }))

vi.mock('../../services', () => ({
  templatesService: { getAll: mocks.getAll, getForCA: mocks.getForCA },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: mocks.getEffective },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn() }),
}))

import { IssueCertificateForm } from '../certificates/IssueCertificateForm'
import { LABEL, choose, optionValues, reviewAndIssue, type } from '../certificates/__tests__/issueFormTestUtils'

const t = (key) => key

function renderForm(effective, templates = []) {
  mocks.getEffective.mockResolvedValue({ data: effective })
  mocks.getAll.mockResolvedValue({ data: templates })
  mocks.getForCA.mockResolvedValue({ data: templates })
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  render(
    <IssueCertificateForm
      cas={[{ id: 3, descr: 'Issuing CA', has_private_key: true }]}
      onSubmit={onSubmit} onCancel={() => {}} t={t}
    />
  )
  choose(LABEL.ca, '3')
  return onSubmit
}

describe('IssueCertificateForm Brainpool', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists the curves and warns while one is selected', async () => {
    const onSubmit = renderForm({ allowed_key_types: null, allowed_digests: null })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    expect(optionValues(LABEL.key).filter((l) => l.startsWith('EC-'))).toEqual(
      ['EC-P256', 'EC-P384', 'EC-P521', 'EC-BP256', 'EC-BP384', 'EC-BP512'])
    expect(screen.queryByRole('note')).toBeNull()

    choose(LABEL.key, 'EC-BP384')
    expect(screen.getByRole('note').textContent).toContain('common.keyGroups.brainpoolWarning')

    type(LABEL.cn, 'host.example.test')
    expect(await reviewAndIssue(onSubmit)).toMatchObject({ key_type: 'ecdsa', key_size: 'brainpoolP384r1' })
  })

  it('follows a Brainpool template', async () => {
    renderForm({ allowed_key_types: null, allowed_digests: null },
      [{ id: 9, name: 'Bp', key_type: 'EC-BP512', template_type: 'custom' }])
    await waitFor(() => expect(optionValues(LABEL.template)).toContain('9'))
    choose(LABEL.template, '9')
    await waitFor(() => expect(screen.getByLabelText(LABEL.key).value).toBe('EC-BP512'))
  })

  it('drops the curves in FIPS mode', async () => {
    renderForm({ allowed_key_types: null, allowed_digests: null, fips: true })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    await waitFor(() => expect(optionValues(LABEL.key).filter((l) => l.startsWith('EC-'))).toEqual(['EC-P256', 'EC-P384', 'EC-P521']))
  })
})
