/**
 * A member of a hybrid pair (RFC 9763) shows a "Linked" badge with its role and
 * a link to the other member; its export offers the hybrid bundle. Records follow
 * the API contract: related_certificate_id (nullable) and hybrid_role.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import en from '../../../i18n/locales/en.json'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => {
      const vars = typeof opts === 'object' && opts ? opts : {}
      const template = lookup(key) ?? (typeof opts === 'string' ? opts : vars.defaultValue ?? key)
      return String(template).replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
    },
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
vi.mock('../../deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))
vi.mock('../../CertificateLintModal', () => ({ CertificateLintModal: () => null }))

import { CertificatePanel } from '../CertificatePanel'

const H = en.certificates.hybrid
const base = {
  id: 11, common_name: 'pair.example.com', subject: 'CN=pair.example.com', serial_number: '42',
  valid_to: '2030-01-01T00:00:00Z', has_private_key: true, status: 'valid',
  key_algorithm: 'EC-P256', key_type: 'EC-P256', signature_algorithm: 'ecdsa-with-SHA256',
}
const classical = { ...base, related_certificate_id: 12, hybrid_role: 'classical' }
const pq = {
  ...base, id: 12, key_algorithm: 'ML-DSA-65', key_type: 'ML-DSA-65', security_level: 3,
  post_quantum: true, related_certificate_id: 11, hybrid_role: 'pq',
}
const single = { ...base, related_certificate_id: null, hybrid_role: null }

describe('CertificatePanel of a hybrid pair member', () => {
  it('links to the other member and opens it', () => {
    const onOpenRelated = vi.fn()
    render(<CertificatePanel certificate={classical} onOpenRelated={onOpenRelated} />)
    const link = screen.getByRole('link', { name: H.openRelated.replace('{{id}}', '12') })
    expect(link).toHaveAttribute('href', '/certificates/12')
    // The link names the other member's role, not this one's
    expect(link).toHaveTextContent(`#12 (${H.rolePq})`)
    fireEvent.click(link)
    expect(onOpenRelated).toHaveBeenCalledWith(12)
  })

  it('stays a working link when no opener is given', () => {
    render(<CertificatePanel certificate={pq} />)
    expect(screen.getByRole('link', { name: H.openRelated.replace('{{id}}', '11') }))
      .toHaveAttribute('href', '/certificates/11')
  })

  it.each([[classical, H.roleClassical], [pq, H.rolePq]])('badges the member with its role', (cert, role) => {
    render(<CertificatePanel certificate={cert} />)
    expect(screen.getByTestId('hybrid-linked-badge')).toHaveTextContent(H.linked)
    expect(screen.getByTestId('hybrid-linked-badge')).toHaveAttribute('title', role)
  })

  it('shows none of it on a single certificate', () => {
    render(<CertificatePanel certificate={single} />)
    expect(screen.queryByTestId('hybrid-linked-badge')).toBeNull()
    expect(screen.queryByText(H.relatedCertificate)).toBeNull()
  })
})
