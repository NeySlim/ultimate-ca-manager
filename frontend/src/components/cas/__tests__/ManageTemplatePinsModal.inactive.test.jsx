/**
 * A pinned template that was deactivated stays in the pin dialog, marked
 * Inactive, so its pin can still be removed (#430 follow-up).
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getAllForCA: vi.fn(),
  unpinFromCA: vi.fn(),
}))

vi.mock('../../../services', () => ({
  templatesService: { getAllForCA: mocks.getAllForCA, unpinFromCA: mocks.unpinFromCA, pinToCA: vi.fn() },
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}))

import { ManageTemplatePinsModal } from '../ManageTemplatePinsModal'

describe('ManageTemplatePinsModal', () => {
  it('lists a deactivated pinned template and lets its pin go', async () => {
    mocks.getAllForCA.mockResolvedValue({ data: [
      { id: 7, name: 'Smartcard Logon', is_pinned: true, is_active: false },
      { id: 8, name: 'Web Server', is_pinned: false, is_active: true },
    ] })
    mocks.unpinFromCA.mockResolvedValue({})
    render(<ManageTemplatePinsModal open onOpenChange={() => {}} ca={{ id: 3, descr: 'Issuing CA' }} t={(k) => k} />)
    expect(await screen.findByText('Smartcard Logon')).toBeInTheDocument()
    expect(mocks.getAllForCA).toHaveBeenCalledWith(3)
    expect(screen.getByText('common.inactive')).toBeInTheDocument()
    fireEvent.click(screen.getByText('templates.unpinFromCA'))
    await waitFor(() => expect(mocks.unpinFromCA).toHaveBeenCalledWith(3, 7))
  })

  it('offers no pin for a deactivated template that is not pinned', async () => {
    mocks.getAllForCA.mockResolvedValue({ data: [
      { id: 7, name: 'Smartcard Logon', is_pinned: false, is_active: false },
      { id: 8, name: 'Web Server', is_pinned: false, is_active: true },
    ] })
    render(<ManageTemplatePinsModal open onOpenChange={() => {}} ca={{ id: 3, descr: 'Issuing CA' }} t={(k) => k} />)
    expect(await screen.findByText('Smartcard Logon')).toBeInTheDocument()
    expect(screen.getAllByText('templates.pinToCA')).toHaveLength(1)
  })
})
