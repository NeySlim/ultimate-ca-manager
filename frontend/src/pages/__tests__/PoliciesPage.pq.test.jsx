/**
 * PoliciesPage lists the registry's ML-DSA levels under the post-quantum
 * heading, stores their labels as the API names them, and hides them in FIPS mode.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { GROUP_PQ, KEY_ALGORITHMS } from '../../lib/keyAlgorithms'

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
  ResponsiveDataTable: () => null,
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

async function openCreate(effective) {
  mocks.list.mockResolvedValue({ data: [] })
  mocks.getEffective.mockResolvedValue({ data: effective })
  render(<PoliciesPage />)
  fireEvent.click(await screen.findByText('policies.createPolicy'))
  await waitFor(() => expect(mocks.getEffective).toHaveBeenCalled())
}

const PQ = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)
const nameOf = (a) => a.i18nKey || a.display

describe('PoliciesPage ML-DSA key types', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers the three ML-DSA levels under the post-quantum heading', async () => {
    expect(PQ.map(a => a.label)).toEqual(['ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87'])
    await openCreate({ allowed_key_types: null, allowed_digests: null })
    expect(screen.getByText('common.keyGroups.pq')).toBeTruthy()
    for (const a of PQ) expect(screen.getByText(nameOf(a))).toBeTruthy()
  })

  it('stores the ML-DSA label the backend accepts', async () => {
    await openCreate({ allowed_key_types: null, allowed_digests: null })
    mocks.create.mockResolvedValue({ data: { id: 1 } })
    fireEvent.click(screen.getByText(nameOf(PQ[1])))
    fireEvent.change(screen.getByLabelText('policies.policyName'), { target: { value: 'Pq' } })
    fireEvent.submit(screen.getByLabelText('policies.policyName').closest('form'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    expect(mocks.create.mock.calls[0][0].rules.allowed_key_types).toEqual(['ML-DSA-65'])
  })

  it('hides ML-DSA in FIPS mode', async () => {
    await openCreate({ allowed_key_types: ['RSA-2048'], allowed_digests: null, fips: true })
    await waitFor(() => expect(screen.queryByText('common.keyGroups.pq')).toBeNull())
    expect(screen.getByText('common.keyTypes.rsa2048')).toBeTruthy()
    for (const a of PQ) expect(screen.queryByText(nameOf(a))).toBeNull()
  })
})
