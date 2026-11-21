/**
 * PoliciesPage: editing a policy sends back the rule keys the form does not
 * show (set through the API), since the update replaces the rules as a whole.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mocks = vi.hoisted(() => ({ create: vi.fn(), list: vi.fn(), update: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))

vi.mock('../../services', () => ({
  policiesService: { list: mocks.list, create: mocks.create, update: mocks.update },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  groupsService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}))

vi.mock('../../hooks', async () => {
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  const { useState } = await vi.importActual('react')
  return {
    useCRUDPage: crud.useCRUDPage,
    usePersistedState: (_key, initial) => useState(initial),
    usePermission: () => ({ canRead: () => true, canWrite: () => true, canDelete: () => true, hasPermission: () => true }),
  }
})


import PoliciesPage from '../PoliciesPage'

async function editedRules(rules) {
  mocks.list.mockResolvedValue({ data: [{ id: 9, name: 'Api', operations: ['issuance'], rules }] })
  mocks.update.mockResolvedValue({ data: { id: 9 } })
  render(<MemoryRouter><PoliciesPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'Api' }))
  fireEvent.click(await screen.findByRole('button', { name: 'common.edit' }))
  fireEvent.click(screen.getByText('SHA-512'))
  fireEvent.submit(screen.getByLabelText('policies.policyName').closest('form'))
  await waitFor(() => expect(mocks.update).toHaveBeenCalled())
  return mocks.update.mock.calls[0][1].rules
}

describe('PoliciesPage keeps the rules it does not show', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends back allowed_signature_schemes and other API-only keys', async () => {
    const rules = await editedRules({
      allowed_digests: ['sha384'],
      allowed_signature_schemes: ['ml_dsa'],
      require_hsm_ca_key: true,
      san_restrictions: { max_dns_names: 5, dns_pattern: '*.example.com', ip_allowed: false },
    })
    expect(rules.allowed_signature_schemes).toEqual(['ml_dsa'])
    expect(rules.require_hsm_ca_key).toBe(true)
    expect(rules.san_restrictions.ip_allowed).toBe(false)
    expect(rules.allowed_digests).toEqual(['sha384', 'sha512'])
  })
})
