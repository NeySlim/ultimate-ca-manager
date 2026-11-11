/**
 * Revoking a member of a hybrid pair (RFC 9763) asks whether to revoke the
 * other member too, checked by default, only when the server would do it:
 * the other member names this one back and is not revoked yet.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RevokeCertificateModal } from '../RevokeCertificateModal'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

const getById = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: { getById: (...args) => getById(...args) },
}))

const member = { id: 11, name: 'pair.example.com', related_certificate_id: 12, hybrid_role: 'classical' }
const renderModal = (certificate) => {
  const onConfirm = vi.fn()
  render(<RevokeCertificateModal open onClose={() => {}} onConfirm={onConfirm} certificate={certificate} />)
  return onConfirm
}
// Submit once the lookup of the other member is over
const submit = async () => {
  await waitFor(() => expect(screen.getByRole('button', { name: 'revocation.confirm' })).not.toBeDisabled())
  fireEvent.submit(screen.getByTestId('revoke-form'))
}

describe('RevokeCertificateModal and a hybrid pair', () => {
  beforeEach(() => { getById.mockReset() })

  it('revokes the linked certificate too unless unchecked', async () => {
    getById.mockResolvedValue({ data: { id: 12, related_certificate_id: 11, revoked: false } })
    const onConfirm = renderModal(member)
    const box = await screen.findByLabelText('revocation.revokeRelated')
    expect(getById).toHaveBeenCalledWith(12)
    expect(box).toBeChecked()
    await submit()
    expect(onConfirm).toHaveBeenLastCalledWith('unspecified', { revokeRelated: true })
    fireEvent.click(box)
    fireEvent.submit(screen.getByTestId('revoke-form'))
    expect(onConfirm).toHaveBeenLastCalledWith('unspecified', { revokeRelated: false })
  })

  it('does not offer it when the other certificate does not name this one back', async () => {
    getById.mockResolvedValue({ data: { id: 12, related_certificate_id: 99, revoked: false } })
    const onConfirm = renderModal(member)
    await submit()
    expect(screen.queryByLabelText('revocation.revokeRelated')).toBeNull()
    expect(onConfirm).toHaveBeenCalledWith('unspecified')
  })

  it('does not offer it when the other certificate is already revoked', async () => {
    getById.mockResolvedValue({ data: { id: 12, related_certificate_id: 11, revoked: true } })
    const onConfirm = renderModal(member)
    await submit()
    expect(screen.queryByLabelText('revocation.revokeRelated')).toBeNull()
    expect(onConfirm).toHaveBeenCalledWith('unspecified')
  })

  it('does not offer it when the other certificate was superseded', async () => {
    getById.mockResolvedValue({ data: { id: 12, related_certificate_id: 11, revoked: false, archived: true } })
    const onConfirm = renderModal(member)
    await submit()
    expect(screen.queryByLabelText('revocation.revokeRelated')).toBeNull()
    expect(onConfirm).toHaveBeenCalledWith('unspecified')
  })

  it('leaves the choice to the operator when the other certificate cannot be read', async () => {
    getById.mockImplementation(() => Promise.reject(new Error('forbidden')))
    renderModal(member)
    expect(await screen.findByLabelText('revocation.revokeRelated')).toBeChecked()
  })

  it('asks nothing about a single certificate', async () => {
    const onConfirm = renderModal({ id: 5, name: 'web.example.com', related_certificate_id: null })
    await submit()
    expect(getById).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('revocation.revokeRelated')).toBeNull()
    expect(onConfirm).toHaveBeenCalledWith('unspecified')
  })
})
