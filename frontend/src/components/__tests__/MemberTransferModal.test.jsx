/**
 * The members of a group, chosen in the mockup's dialog: one check line per user, the members
 * ticked, a search over name and address, the shown users ticked or cleared at once, and Save
 * only once something changed.
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, vars) => (vars ? `${key}:${JSON.stringify(vars)}` : key) }),
}))

import { MemberTransferModal } from '../MemberTransferModal'

const USERS = [
  { id: 1, username: 'a.martin', email: 'a@example.com' },
  { id: 2, username: 'c.durand', email: 'c@example.com', full_name: 'Claire Durand' },
  { id: 3, username: 'svc-backup', email: 'ops@example.com' },
]

const setup = (props = {}) => {
  const onSave = vi.fn()
  render(<MemberTransferModal open title="Members - pki-ops" allUsers={USERS} currentMembers={[{ id: 2, username: 'c.durand' }]} onSave={onSave} onClose={vi.fn()} {...props} />)
  return { onSave, save: () => screen.getByRole('button', { name: 'common.save' }) }
}

describe('MemberTransferModal', () => {
  it('ticks the current members, in the mockup dialog', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(dialog.closest('.atl')).not.toBeNull()
    expect(screen.getByRole('checkbox', { name: /c\.durand/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /a\.martin/ })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /a\.martin/ }).closest('label')).toHaveClass('checkbox-line')
  })

  it('reads a member given by user_id as well', () => {
    setup({ currentMembers: [{ user_id: 3 }] })
    expect(screen.getByRole('checkbox', { name: /svc-backup/ })).toBeChecked()
  })

  it('saves the ticked users once something changed', () => {
    const { onSave, save } = setup()
    expect(save()).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /a\.martin/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /c\.durand/ }))
    expect(save()).toBeEnabled()
    fireEvent.click(save())
    expect(onSave).toHaveBeenCalledWith([1])
  })

  it('searches name, address and full name, and ticks the shown users at once', () => {
    const { onSave, save } = setup()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'example.com' } })
    expect(screen.getAllByRole('checkbox', { name: /@example\.com/ })).toHaveLength(3)
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'claire' } })
    expect(screen.getAllByRole('checkbox', { name: /@example\.com/ })).toHaveLength(1)
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'nobody' } })
    expect(screen.getByText('members.noMatchingUsers')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'a' } })
    const all = screen.getByRole('checkbox', { name: /common\.selectAll/ })
    fireEvent.click(all)
    fireEvent.click(save())
    expect(onSave.mock.calls[0][0].sort()).toEqual([1, 2, 3])
  })

  it('keeps its buttons still while saving', () => {
    setup({ loading: true })
    const actions = screen.getByRole('dialog').querySelector('.modal-actions')
    expect(within(actions).getByRole('button', { name: 'common.cancel' })).toBeDisabled()
    expect(within(actions).getByRole('button', { name: 'common.saving' })).toBeDisabled()
  })
})
