/**
 * PoliciesPage in FIPS mode (#399): a read-only notice names the system
 * policy, and EdDSA key types are offered only to be removed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn(), update: vi.fn(), getEffective: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))

vi.mock('../../services', () => ({
  policiesService: { list: mocks.list, create: mocks.create, update: mocks.update, getEffective: mocks.getEffective },
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

describe('PoliciesPage FIPS system policy (#399)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the read-only notice and hides EdDSA keys in FIPS mode', async () => {
    mocks.list.mockResolvedValue({ data: [] })
    mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: ['RSA-2048'], allowed_digests: ['sha256'], fips: true } })
    render(<PoliciesPage />)
    expect(await screen.findByText('policies.fipsRulesTitle')).toBeTruthy()
    fireEvent.click(screen.getByText('policies.createPolicy'))
    expect(screen.getByText('common.keyTypes.rsa2048')).toBeTruthy()
    expect(screen.queryByText('common.keyTypes.ed25519')).toBeNull()
    expect(screen.queryByText('common.keyTypes.ed448')).toBeNull()
  })

  it('keeps a ticked EdDSA key visible so it can be removed', async () => {
    mocks.list.mockResolvedValue({ data: [{ id: 3, name: 'Legacy', policy_type: 'issuance', rules: { allowed_key_types: ['RSA-2048', 'ED25519'] } }] })
    mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: ['RSA-2048'], allowed_digests: null, fips: true } })
    mocks.update.mockResolvedValue({ data: { id: 3 } })
    render(<PoliciesPage />)
    await screen.findByText('policies.fipsRulesTitle')
    fireEvent.click(await screen.findByText('row-Legacy'))
    fireEvent.click(await screen.findByText('common.edit'))
    expect(screen.queryByText('common.keyTypes.ed448')).toBeNull()
    fireEvent.click(screen.getByText('common.keyTypes.ed25519'))
    fireEvent.submit(screen.getByLabelText('policies.policyName').closest('form'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    expect(mocks.update.mock.calls[0][1].rules.allowed_key_types).toEqual(['RSA-2048'])
  })

  it('shows no notice and every key type outside FIPS mode', async () => {
    mocks.list.mockResolvedValue({ data: [] })
    mocks.getEffective.mockResolvedValue({ data: { allowed_key_types: null, allowed_digests: null } })
    render(<PoliciesPage />)
    fireEvent.click(await screen.findByText('policies.createPolicy'))
    await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
    expect(screen.getByText('common.keyTypes.ed25519')).toBeTruthy()
    expect(screen.queryByText('policies.fipsRulesTitle')).toBeNull()
  })
})
