import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ restorePrimary: vi.fn(), showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError, showWarning: mocks.showWarning }),
}))
vi.mock('../../../services', () => ({ casService: { restorePrimary: mocks.restorePrimary } }))
vi.mock('../../Modal', () => ({ Modal: ({ open, children }) => (open ? <div role="dialog">{children}</div> : null) }))

import { RestorePrimaryModal } from '../RestorePrimaryModal'

const PEM = '-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----'

describe('RestorePrimaryModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends the pasted self-signed certificate for the chosen record', async () => {
    mocks.restorePrimary.mockResolvedValue({ data: { warnings: [] } })
    const onDone = vi.fn()
    render(<RestorePrimaryModal open onClose={vi.fn()} ca={{ id: 8, name: 'Dup' }} onDone={onDone} />)
    fireEvent.change(screen.getByPlaceholderText('-----BEGIN CERTIFICATE-----'), { target: { value: PEM } })
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.restorePrimary).toHaveBeenCalledWith(8, PEM))
    expect(onDone).toHaveBeenCalled()
  })

  it('shows the refusal and stays open', async () => {
    mocks.restorePrimary.mockRejectedValue(new Error('subject differs'))
    const onClose = vi.fn()
    render(<RestorePrimaryModal open onClose={onClose} ca={{ id: 8, name: 'Dup' }} />)
    fireEvent.change(screen.getByPlaceholderText('-----BEGIN CERTIFICATE-----'), { target: { value: PEM } })
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith('subject differs'))
    expect(onClose).not.toHaveBeenCalled()
  })
})
