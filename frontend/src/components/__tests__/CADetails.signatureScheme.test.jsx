/**
 * The floating CA window shows the RSA signature scheme and its switch,
 * which needs write:cas alone (not the template pins scope).
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ update: vi.fn(), showConfirm: vi.fn(), onChanged: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }) }))
vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: mocks.showConfirm }),
}))
vi.mock('../../services', () => ({ casService: { update: mocks.update } }))
vi.mock('../cas/CACrlSection', () => ({ CACrlSection: () => null }))

const { CADetails } = await import('../CADetails')

const CA = { id: 3, descr: 'Window CA', key_type: 'RSA 3072', signature_scheme: 'pss', valid_to: '2030-01-01T00:00:00Z' }

describe('CADetails signature scheme', () => {
  it('switches back to v1.5 with write:cas', async () => {
    mocks.showConfirm.mockResolvedValue(true)
    mocks.update.mockResolvedValue({ data: { ...CA, signature_scheme: 'pkcs1v15' } })
    render(<CADetails ca={CA} embedded canWriteCas onCaChanged={mocks.onChanged} />)
    expect(screen.getByText('cas.signatureSchemePss')).toBeInTheDocument()
    fireEvent.click(screen.getByText('cas.signatureSchemeUseV15'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(3, { signatureScheme: 'pkcs1v15' }))
    expect(mocks.onChanged).toHaveBeenCalledWith(expect.objectContaining({ signature_scheme: 'pkcs1v15' }))
  })

  it('shows the scheme without a switch otherwise', () => {
    render(<CADetails ca={CA} embedded />)
    expect(screen.getByText('cas.signatureSchemePss')).toBeInTheDocument()
    expect(screen.queryByText('cas.signatureSchemeUseV15')).not.toBeInTheDocument()
  })
})
