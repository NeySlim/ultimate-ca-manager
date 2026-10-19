/**
 * PoliciesPage: a policy can restrict the signature hashes (#397); a new
 * policy restricts no hash and no key type, and the EdDSA key types can be allowed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

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
    usePermission: () => ({ canRead: () => true, canWrite: () => true, canDelete: () => true }),
  }
})

vi.mock('../../components', () => ({
  ResponsiveLayout: ({ children, actions, slideOverContent }) => <div>{actions}{children}{slideOverContent}</div>,
  ResponsiveDataTable: ({ data, onRowClick }) => (data || []).map(r => (
    <button key={r.id} onClick={() => onRowClick(r)}>{`row-${r.name}`}</button>
  )),
  Card: ({ children }) => <div>{children}</div>,
  Badge: ({ children }) => <span>{children}</span>,
  LoadingSpinner: () => null,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, ...props }) => <input aria-label={label} {...props} />,
  Textarea: ({ label, ...props }) => <textarea aria-label={label} {...props} />,
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Select: () => null,
}))

import PoliciesPage from '../PoliciesPage'

async function openCreate() {
  mocks.list.mockResolvedValue({ data: [] })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  render(<PoliciesPage />)
  fireEvent.click(await screen.findByText('policies.createPolicy'))
  fireEvent.change(screen.getByLabelText('policies.policyName'), { target: { value: 'FIPS' } })
}

async function submitted() {
  fireEvent.submit(screen.getByLabelText('policies.policyName').closest('form'))
  await waitFor(() => expect(mocks.create).toHaveBeenCalled())
  return mocks.create.mock.calls[0][0].rules
}

describe('PoliciesPage signature hash rule (#397)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('restricts no hash by default', async () => {
    await openCreate()
    expect((await submitted()).allowed_digests).toEqual([])
  })

  it('restricts no key type by default', async () => {
    await openCreate()
    expect((await submitted()).allowed_key_types).toEqual([])
  })

  it('keeps a policy without key types unrestricted when edited', async () => {
    mocks.list.mockResolvedValue({ data: [{ id: 7, name: 'Hashes', policy_type: 'issuance', rules: { allowed_digests: ['sha384'] } }] })
    mocks.update.mockResolvedValue({ data: { id: 7 } })
    render(<PoliciesPage />)
    fireEvent.click(await screen.findByText('row-Hashes'))
    fireEvent.click(await screen.findByText('common.edit'))
    fireEvent.submit(screen.getByLabelText('policies.policyName').closest('form'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    expect(mocks.update.mock.calls[0][1].rules.allowed_key_types).toEqual([])
  })

  it('sends the hashes and EdDSA key types the operator ticks', async () => {
    await openCreate()
    fireEvent.click(screen.getByText('SHA-384'))
    fireEvent.click(screen.getByText('SHA-512'))
    fireEvent.click(screen.getByText('common.keyTypes.ed25519'))
    const rules = await submitted()
    expect(rules.allowed_digests).toEqual(['sha384', 'sha512'])
    expect(rules.allowed_key_types).toContain('ED25519')
  })
})

describe('PoliciesPage rules nothing enforced', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends neither required extensions nor approval for external names', async () => {
    await openCreate()
    const rules = await submitted()
    expect(rules).not.toHaveProperty('required_extensions')
    expect(rules.san_restrictions).not.toHaveProperty('require_approval_for_external')
  })
})
