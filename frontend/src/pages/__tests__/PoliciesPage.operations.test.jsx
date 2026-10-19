/**
 * PoliciesPage: a policy governs the operations ticked (issuance, renewal,
 * revocation); one left with none says so.
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
  fireEvent.change(screen.getByLabelText('policies.policyName'), { target: { value: 'Ops' } })
}

const form = () => screen.getByLabelText('policies.policyName').closest('form')
const tick = (key) => fireEvent.click(screen.getByText(key).closest('label').querySelector('input'))

describe('PoliciesPage operations', () => {
  beforeEach(() => vi.clearAllMocks())

  it('governs issuance by default', async () => {
    await openCreate()
    fireEvent.submit(form())
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    expect(mocks.create.mock.calls[0][0].operations).toEqual(['issuance'])
  })

  it('sends the operations ticked', async () => {
    await openCreate()
    tick('policies.policyType.issuance')
    tick('policies.policyType.revocation')
    tick('policies.policyType.renewal')
    fireEvent.submit(form())
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    expect(mocks.create.mock.calls[0][0].operations).toEqual(['revocation', 'renewal'])
  })

  it('refuses a policy without operation', async () => {
    await openCreate()
    tick('policies.policyType.issuance')
    expect(screen.getByText('policies.operationsRequired')).toBeTruthy()
    fireEvent.submit(form())
    await new Promise(r => setTimeout(r, 0))
    expect(mocks.create).not.toHaveBeenCalled()
  })

  it('says when an old policy governs nothing', async () => {
    mocks.list.mockResolvedValue({ data: [{ id: 3, name: 'Old revocation', policy_type: 'revocation', operations: [], rules: {} }] })
    render(<PoliciesPage />)
    fireEvent.click(await screen.findByText('row-Old revocation'))
    expect(await screen.findByText('policies.noOperation')).toBeTruthy()
  })
})
