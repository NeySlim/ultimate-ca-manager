import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ confirmParent: vi.fn(), withdrawParent: vi.fn(), showSuccess: vi.fn(), showError: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
}))
vi.mock('../../../services', () => ({
  casService: { confirmParent: mocks.confirmParent, withdrawParent: mocks.withdrawParent },
}))
vi.mock('../../Modal', () => ({ Modal: ({ open, children }) => (open ? <div role="dialog">{children}</div> : null) }))

import { ParentConfirmationSection } from '../ParentConfirmationSection'

const ORPHAN = { id: 5, parent_candidate: { id: 2, name: 'Gost Root', algorithm: 'GOST2012-256' } }
const LINKED = { id: 5, caref: 'r', parent_confirmed_by: 'admin', parent_confirmed_at: '2026-11-13T10:00:00Z' }

describe('ParentConfirmationSection', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows nothing for a CA with neither a proposal nor a confirmed link', () => {
    const { container } = render(<ParentConfirmationSection ca={{ id: 1 }} canWrite />)
    expect(container.textContent).toBe('')
  })

  it('links the proposed parent only once the confirmation is ticked', async () => {
    mocks.confirmParent.mockResolvedValue({ data: { id: 5, caref: 'r' } })
    const onChanged = vi.fn()
    render(<ParentConfirmationSection ca={ORPHAN} canWrite onChanged={onChanged} />)
    expect(screen.getByTestId('parent-candidate')).toBeInTheDocument()
    fireEvent.click(screen.getByText('cas.linkToParent'))
    const submit = screen.getAllByText('cas.linkToParent').at(-1).closest('button')
    expect(submit).toBeDisabled()
    fireEvent.click(screen.getByTestId('parent-confirm-check'))
    expect(submit).not.toBeDisabled()
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.confirmParent).toHaveBeenCalledWith(5, 2))
    expect(onChanged).toHaveBeenCalledWith({ id: 5, caref: 'r' })
  })

  it('offers no button to a reader', () => {
    render(<ParentConfirmationSection ca={ORPHAN} />)
    expect(screen.queryByText('cas.linkToParent')).toBeNull()
  })

  it('withdraws a link confirmed by hand', async () => {
    mocks.withdrawParent.mockResolvedValue({ data: { id: 5, caref: null } })
    render(<ParentConfirmationSection ca={LINKED} canWrite onChanged={vi.fn()} />)
    expect(screen.getByTestId('parent-confirmed')).toBeInTheDocument()
    fireEvent.click(screen.getByText('cas.withdrawParentLink'))
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.withdrawParent).toHaveBeenCalledWith(5))
  })

  it('shows the refusal and keeps the dialog open', async () => {
    mocks.confirmParent.mockRejectedValue(new Error('not the proposed parent'))
    render(<ParentConfirmationSection ca={ORPHAN} canWrite />)
    fireEvent.click(screen.getByText('cas.linkToParent'))
    fireEvent.click(screen.getByTestId('parent-confirm-check'))
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith('not the proposed parent'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
