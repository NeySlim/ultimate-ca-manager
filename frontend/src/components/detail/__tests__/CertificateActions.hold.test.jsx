/**
 * A certificate on hold can still be revoked for good (RFC 5280 §5.2.4): its
 * Revoke button stays; a certificate revoked for good has none.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import en from '../../i18n/locales/en.json'
import { isOnHold } from '../../lib/utils'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => lookup(key) ?? (typeof opts === 'string' ? opts : key) }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
vi.mock('../deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))
vi.mock('../CertificateLintModal', () => ({ CertificateLintModal: () => null }))

import { CertificateDetails } from '../CertificateDetails'

const base = {
  id: 21, common_name: 'held.example.com', subject: 'CN=held.example.com', serial_number: '42',
  valid_to: '2030-01-01T00:00:00Z', key_algorithm: 'EC-P256', key_type: 'EC-P256',
  signature_algorithm: 'ecdsa-with-SHA256',
}
const revokeLabel = en.certificates.revokeCertificate

describe('Revoke on a revoked certificate', () => {
  it.each([
    ['valid', { revoked: false }, true],
    ['on hold', { revoked: true, revoke_reason: 'certificateHold', status: 'revoked' }, true],
    ['revoked for good', { revoked: true, revoke_reason: 'keyCompromise', status: 'revoked' }, false],
  ])('%s', (_name, state, offered) => {
    render(<CertificateDetails certificate={{ ...base, ...state }} onRevoke={vi.fn()} canWrite />)
    expect(!!screen.queryByLabelText(revokeLabel)).toBe(offered)
  })
})

describe('isOnHold', () => {
  it.each([
    [{ revoked: true, revoke_reason: 'certificateHold' }, true],
    [{ revoked: true, revoke_reason: 'certificate_hold' }, true],
    [{ revoked: true, revoke_reason: 'superseded' }, false],
    [{ revoked: false, revoke_reason: 'certificateHold' }, false],
    [null, false],
  ])('%j', (cert, held) => expect(isOnHold(cert)).toBe(held))
})
