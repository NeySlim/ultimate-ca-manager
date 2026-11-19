/**
 * CertificateCompareModal: a caller that hands both certificates (two rows ticked
 * in a list) gets the comparison at once; with one, the other is left to choose.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
}))

import { CertificateCompareModal } from '../CertificateCompareModal'

const cert = (id, cn, serial) => ({
  id, common_name: cn, status: 'valid', issuer: 'CN=CA', key_type: 'EC', serial_number: serial,
  valid_from: '2026-01-01T00:00:00Z', valid_to: '2027-01-01T00:00:00Z',
})
const A = cert(7, 'web.example.com', 'AA01')
const B = cert(8, 'api.example.com', 'BB02')
const C = cert(9, 'db.example.com', 'CC03')
const mount = (props) => render(<CertificateCompareModal open onClose={() => {}} certificates={[A, B, C]} {...props} />)

describe('CertificateCompareModal with the certificates of a selection', () => {
  it('compares the two it is handed', () => {
    mount({ initialCert: A, secondCert: C })
    expect(screen.getByText('AA01')).toBeInTheDocument()
    expect(screen.getByText('CC03')).toBeInTheDocument()
    expect(screen.queryByText('BB02')).toBeNull()
  })

  it('waits for the second when it is handed one', () => {
    mount({ initialCert: A })
    expect(screen.queryByText('AA01')).toBeNull()
    expect(screen.queryByText('common.serialNumber')).toBeNull()
  })

  it('follows a new pair while it stays mounted', () => {
    const { rerender } = mount({ initialCert: A, secondCert: C })
    rerender(<CertificateCompareModal open onClose={() => {}} certificates={[A, B, C]} initialCert={A} secondCert={B} />)
    expect(screen.getByText('BB02')).toBeInTheDocument()
    expect(screen.queryByText('CC03')).toBeNull()
    // Back to one certificate: the second side empties instead of keeping the last one
    rerender(<CertificateCompareModal open onClose={() => {}} certificates={[A, B, C]} initialCert={A} secondCert={null} />)
    expect(screen.queryByText('BB02')).toBeNull()
  })
})
