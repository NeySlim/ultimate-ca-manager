/**
 * PoliciesPage lists Brainpool under its own group (phase 4.4), with a
 * compatibility notice while one is ticked, and hides it in FIPS mode.
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

describe('PoliciesPage Brainpool key types', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers the three Brainpool curves under their own heading, with the notice once ticked', async () => {
    await openCreate({ allowed_key_types: null, allowed_digests: null })
    expect(screen.getByText('common.keyGroups.brainpool')).toBeTruthy()
    expect(screen.queryByRole('note')).toBeNull()
    for (const name of ['Brainpool P256r1', 'Brainpool P384r1', 'Brainpool P512r1']) {
      expect(screen.getByText(name)).toBeTruthy()
    }
    fireEvent.click(screen.getByText('Brainpool P384r1'))
    expect(screen.getByRole('note').textContent).toContain('common.keyGroups.brainpoolWarning')
  })

  it('stores the Brainpool label the backend accepts', async () => {
    await openCreate({ allowed_key_types: null, allowed_digests: null })
    mocks.create.mockResolvedValue({ data: { id: 1 } })
    fireEvent.click(screen.getByText('Brainpool P256r1'))
    fireEvent.change(screen.getByLabelText('policies.policyName'), { target: { value: 'Bp' } })
    fireEvent.submit(screen.getByLabelText('policies.policyName').closest('form'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    expect(mocks.create.mock.calls[0][0].rules.allowed_key_types).toEqual(['EC-BP256'])
  })

  it('hides Brainpool in FIPS mode', async () => {
    await openCreate({ allowed_key_types: ['RSA-2048'], allowed_digests: null, fips: true })
    await waitFor(() => expect(screen.queryByText('Brainpool P256r1')).toBeNull())
    expect(screen.queryByText('common.keyGroups.brainpool')).toBeNull()
    expect(screen.getByText('common.keyTypes.ecdsaP256')).toBeTruthy()
  })
})
