/**
 * Revocation reason dialog (issue #334).
 *
 * Manual revocations used to go through a plain confirm and were recorded as
 * `unspecified`. The dialog now offers the RFC 5280 reason codes, defaults to
 * unspecified, explains the selected code and hands the choice to onConfirm.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RevokeDialog as RevokeCertificateModal } from '../RevokeDialog'
import { REVOCATION_REASONS } from '../../../../lib/revocationReasons'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

describe('RevokeDialog', () => {
  it('offers every RFC 5280 reason, unspecified first and selected', () => {
    render(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'web.example.com' }} />)
    const select = screen.getByTestId('revoke-reason')
    const values = Array.from(select.querySelectorAll('option')).map(o => o.value)
    expect(values).toEqual(REVOCATION_REASONS)
    expect(values[0]).toBe('unspecified')
    expect(select.value).toBe('unspecified')
    expect(screen.getByText('revocation.hints.unspecified', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('web.example.com')).toBeInTheDocument()
  })

  it('hands the chosen reason to onConfirm and shows its hint', () => {
    const onConfirm = vi.fn()
    render(<RevokeCertificateModal open onClose={() => {}} onConfirm={onConfirm} certificate={{ name: 'x' }} />)
    fireEvent.change(screen.getByTestId('revoke-reason'), { target: { value: 'keyCompromise' } })
    expect(screen.getByText('revocation.hints.keyCompromise', { exact: false })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'revocation.confirm' }))
    expect(onConfirm).toHaveBeenCalledWith('keyCompromise')
  })

  it('shows the Microsoft CA warning only for AD CS certificates', () => {
    const { rerender } = render(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x', source: 'msca' }} />)
    expect(screen.getByText('certificates.revokeMscaWarning', { exact: false })).toBeInTheDocument()
    rerender(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x', source: 'acme' }} />)
    expect(screen.queryByText('certificates.revokeMscaWarning', { exact: false })).toBeNull()
  })

  it('resets to unspecified when reopened', () => {
    const { rerender } = render(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x' }} />)
    fireEvent.change(screen.getByTestId('revoke-reason'), { target: { value: 'superseded' } })
    rerender(<RevokeCertificateModal open={false} onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x' }} />)
    rerender(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'x' }} />)
    expect(screen.getByTestId('revoke-reason').value).toBe('unspecified')
  })

  it('is the mockup dialog: its question, an amber notice, the name, « Motif » and one note', () => {
    render(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'web.example.com' }} />)
    expect(screen.getByRole('dialog', { name: 'revocation.dialogTitle' })).toHaveClass('narrow')
    expect(screen.getByText('revocation.notice', { exact: false }).closest('.notice')).toHaveClass('warn')
    expect(screen.getByLabelText('revocation.reason').closest('label')).toHaveClass('field')
    const note = screen.getByText('revocation.hints.unspecified', { exact: false })
    expect(note).toHaveClass('small', 'muted')
    expect(note).toHaveTextContent('revocation.reasonHelp')
    expect(screen.getByRole('button', { name: 'revocation.confirm' })).toHaveClass('btn', 'danger')
  })

  it('keeps the title and notice a CA revocation passes', () => {
    render(<RevokeCertificateModal open onClose={() => {}} onConfirm={() => {}} certificate={{ name: 'Sub CA' }}
      title="Revoke CA" warning="CA warning" allowHold={false} />)
    expect(screen.getByRole('heading', { name: 'Revoke CA' })).toBeInTheDocument()
    expect(screen.getByText('CA warning', { exact: false }).closest('.notice')).toHaveClass('warn')
    expect(screen.queryByRole('option', { name: 'revocation.reasons.certificateHold' })).toBeNull()
    expect(screen.getByText('revocation.reasonHelpNoHold', { exact: false })).toBeInTheDocument()
  })
})
