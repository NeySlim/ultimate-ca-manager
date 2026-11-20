/**
 * The issue form says how many CAs it leaves out instead of hiding them in silence (#426).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

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
import { LABEL, optionValues } from '../certificates/__tests__/issueFormTestUtils'

const t = (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key)

function renderForm(cas) {
  mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: null, allowed_digests: null } })
  mocks.getAll.mockResolvedValue({ data: [] })
  mocks.getForCA.mockResolvedValue({ data: [] })
  render(<IssueCertificateForm cas={cas} onSubmit={vi.fn()} onCancel={() => {}} t={t} />)
}

describe('IssueCertificateForm CAs that cannot sign (#426)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists the signing CA and counts the root imported without its key', () => {
    renderForm([
      { id: 3, descr: 'Issuing CA', has_private_key: true },
      { id: 4, descr: 'Imported root', is_root: true, certificate_only: true, has_private_key: false },
    ])
    // The only CA that can sign is the choice: nothing to pick
    expect(optionValues(LABEL.ca)).toEqual(['3'])
    expect(screen.getByTestId('unlisted-cas')).toHaveTextContent('certificates.issueForm.hintExcluded:1')
  })

  it('says nothing when every CA can sign', () => {
    renderForm([{ id: 3, descr: 'Issuing CA', has_private_key: true }])
    expect(screen.queryByTestId('unlisted-cas')).toBeNull()
  })
})
