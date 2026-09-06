/**
 * Revocation reason dialog (issue #334).
 *
 * Manual revocations used to go through a plain confirm and were recorded as
 * `unspecified`. The dialog now offers the RFC 5280 reason codes, defaults to
 * unspecified, explains the selected code and hands the choice to onConfirm.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RevokeCertificateModal, REVOCATION_REASONS } from '../RevokeCertificateModal'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

describe('RevokeCertificateModal', () => {
  it('offers every RFC 5280 reason, unspecified first and selected', () => {
    render(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'web.example.com' }} />)
    const select = screen.getByTestId('revoke-reason')
    const values = Array.from(select.querySelectorAll('option')).map(o => o.value)
    expect(values).toEqual(REVOCATION_REASONS)
    expect(values[0]).toBe('unspecified')
    expect(select.value).toBe('unspecified')
    expect(screen.getByText('revocation.hints.unspecified')).toBeInTheDocument()
    expect(screen.getByText('web.example.com')).toBeInTheDocument()
  })

  it('hands the chosen reason to onConfirm and shows its hint', () => {
    const onConfirm = vi.fn()
    render(<RevokeCertificateModal open onClose={() => {}} onConfirm={onConfirm} certificate={{ name: 'x' }} />)
    fireEvent.change(screen.getByTestId('revoke-reason'), { target: { value: 'keyCompromise' } })
    expect(screen.getByText('revocation.hints.keyCompromise')).toBeInTheDocument()
    fireEvent.submit(screen.getByTestId('revoke-form'))
    expect(onConfirm).toHaveBeenCalledWith('keyCompromise')
  })

  it('shows the Microsoft CA warning only for AD CS certificates', () => {
    const { rerender } = render(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x', source: 'msca' }} />)
    expect(screen.getByText('certificates.revokeMscaWarning')).toBeInTheDocument()
    rerender(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x', source: 'acme' }} />)
    expect(screen.queryByText('certificates.revokeMscaWarning')).toBeNull()
  })

  it('resets to unspecified when reopened', () => {
    const { rerender } = render(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x' }} />)
    fireEvent.change(screen.getByTestId('revoke-reason'), { target: { value: 'superseded' } })
    rerender(<RevokeCertificateModal open={false} onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x' }} />)
    rerender(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x' }} />)
    expect(screen.getByTestId('revoke-reason').value).toBe('unspecified')
  })
})
