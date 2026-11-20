/**
 * IssueCertificateForm and ML-DSA (FIPS 204): a third key type sent as
 * key_type=ml-dsa key_size=<level>, kept when an ML-DSA template is picked.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { GROUP_PQ, KEY_ALGORITHMS, findAlgorithm } from '../../lib/keyAlgorithms'

const mocks = vi.hoisted(() => ({ getEffective: vi.fn(), templates: [] }))

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn(() => Promise.resolve({ data: mocks.templates })),
    getForCA: vi.fn(() => Promise.resolve({ data: mocks.templates })),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: mocks.getEffective },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn() }),
}))

import { IssueCertificateForm } from '../certificates/IssueCertificateForm'
import { LABEL, choose, field, optionValues, reviewAndIssue, type } from '../certificates/__tests__/issueFormTestUtils'

const PQ_ROWS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)
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

async function submit(onSubmit) {
  type(LABEL.cn, 'pq.example.test')
  return reviewAndIssue(onSubmit)
}

describe('IssueCertificateForm ML-DSA', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.templates = []
  })

  it('offers ml-dsa with its levels and sends key_type=ml-dsa key_size=65 by default', async () => {
    expect(PQ_ROWS).toHaveLength(3)
    const onSubmit = renderForm({ allowed_key_types: null, allowed_digests: null, default_key_type: 'RSA-2048' })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    expect(optionValues(LABEL.key).filter((l) => l.startsWith('ML-DSA'))).toEqual(PQ_ROWS.map(a => a.label))
    choose(LABEL.key, 'ML-DSA-65')
    expect(field(LABEL.key).value).toBe('ML-DSA-65')
    expect(await submit(onSubmit)).toMatchObject({ key_type: 'ml-dsa', key_size: '65' })
  })

  it('keeps an ML-DSA template as ML-DSA, never ECDSA', async () => {
    mocks.templates = [{ id: 9, name: 'PQ server', template_type: 'web_server', key_type: 'ML-DSA-87', dn_template: {} }]
    const onSubmit = renderForm({ allowed_key_types: null, allowed_digests: null, default_key_type: 'RSA-2048' })
    await waitFor(() => expect(optionValues(LABEL.template)).toContain('9'))
    choose(LABEL.template, '9')
    await waitFor(() => expect(field(LABEL.key).value).toBe('ML-DSA-87'))
    expect(findAlgorithm(field(LABEL.key).value).issue).toEqual(['ml-dsa', '87'])
    expect(await submit(onSubmit)).toMatchObject({ key_type: 'ml-dsa', key_size: '87' })
  })

  it('switches to ML-DSA when it is all the policies allow', async () => {
    const onSubmit = renderForm({ allowed_key_types: ['ML-DSA-44'], allowed_digests: null })
    await waitFor(() => expect(optionValues(LABEL.key)).toEqual(['ML-DSA-44']))
    // The forbidden key switches in an effect, one render after the options narrow
    await waitFor(() => expect(field(LABEL.key).value).toBe('ML-DSA-44'))
    expect(await submit(onSubmit)).toMatchObject({ key_type: 'ml-dsa', key_size: '44' })
  })

  it('offers no ML-DSA in FIPS mode', async () => {
    renderForm({ allowed_key_types: null, allowed_digests: null, fips: true })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    await waitFor(() => expect(optionValues(LABEL.key).some((l) => l.startsWith('ML-DSA'))).toBe(false))
    expect(optionValues(LABEL.key).length).toBeGreaterThan(1)
  })

  it('offers no ML-DSA on a build without it', async () => {
    renderForm({ allowed_key_types: null, allowed_digests: null, ml_dsa: false })
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    await waitFor(() => expect(optionValues(LABEL.key).some((l) => l.startsWith('ML-DSA'))).toBe(false))
    expect(optionValues(LABEL.key).filter(Boolean).every((l) => /^(RSA|EC)-/.test(l))).toBe(true)
  })
})
