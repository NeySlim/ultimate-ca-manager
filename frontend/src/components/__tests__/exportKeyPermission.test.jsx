/**
 * Private-key export: one rule, taken from the server (DUP-CONTRACT-001).
 *
 * A frontend guard is never a security boundary — the route decides. These
 * predicates exist only so no surface offers a key export the API will refuse,
 * and none hides one it would accept. The gates they mirror:
 *
 *   certificate       backend/api/v2/certificates/export.py  read:private_keys
 *   ca                backend/api/v2/cas/export.py           write:cas + read:private_keys, 409 on HSM
 *   user_certificate  backend/api/v2/user_certificates.py    no key scope at all
 *
 * The built-in Operator role holds write:certificates but not read:private_keys
 * (private_keys is admin-only, backend/auth/permissions.py), so it is the state
 * that told the surfaces apart: the row dialog hid PKCS#12, the detail panel
 * offered it, and the server answered 403.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  // i18next takes either a string default or an options object carrying
  // `defaultValue` plus interpolation values; a mock that only understands
  // the first returns the options object itself as the translation.
  useTranslation: () => ({
    t: (key, fallback) => {
      if (typeof fallback === 'string') return fallback
      if (fallback && typeof fallback === 'object') {
        const template = fallback.defaultValue || key
        return String(template).replace(
          /\{\{(\w+)\}\}/g,
          (_m, name) => (fallback[name] !== undefined ? fallback[name] : `{{${name}}}`),
        )
      }
      return key
    },
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

vi.mock('../deploy/CertDeploySection', () => ({
  CertDeploySection: () => null,
}))

vi.mock('../CertificateLintModal', () => ({
  CertificateLintModal: () => null,
}))

import { CertificateDetails } from '../CertificateDetails'
import { ExportModal } from '../ExportModal'
import { canExportPrivateKey } from '../../lib/exportPermissions'

// Verbatim from backend/auth/permissions.py.
const OPERATOR_PERMISSIONS = [
  'read:certificates', 'write:certificates',
  'read:user_certificates', 'write:user_certificates', 'delete:user_certificates',
  'read:cas', 'write:cas',
  'read:csrs', 'write:csrs', 'delete:csrs',
  'read:templates',
  'read:truststore', 'write:truststore',
  'read:crl', 'write:crl',
  'read:acme', 'write:acme', 'delete:acme',
  'read:scep', 'read:est', 'read:xcep', 'read:wstep',
  'read:kerberos', 'read:ad_connector', 'read:hsm',
  'read:ssh', 'write:ssh', 'delete:ssh',
  'read:policies', 'read:approvals', 'write:approvals',
  'read:key_recovery', 'write:key_recovery',
  'read:audit',
  'read:settings', 'write:settings',
  'read:groups', 'write:groups',
]

// The same matching usePermission applies, so the test judges the predicate
// and not a hand-rolled stand-in.
const permissionApi = (permissions) => {
  const hasPermission = (required) => {
    if (!required) return true
    if (!permissions.length) return false
    if (permissions.includes('*')) return true
    if (permissions.includes(required)) return true
    if (required.includes(':')) {
      const [category] = required.split(':')
      if (permissions.includes(`${category}:*`)) return true
    }
    return false
  }
  return { hasPermission, canWrite: (resource) => hasPermission(`write:${resource}`) }
}

const CERT = {
  id: 7,
  common_name: 'web.example.com',
  subject: 'CN=web.example.com',
  has_private_key: true,
  serial_number: '42',
  valid_to: '2030-01-01T00:00:00Z',
}

const KEY_FORMATS = ['P12 / PKCS#12', 'JKS']

describe('canExportPrivateKey mirrors the server gate', () => {
  it('requires read:private_keys for a managed certificate', () => {
    const operator = permissionApi(OPERATOR_PERMISSIONS)
    expect(canExportPrivateKey('certificate', operator)).toBe(false)
    const admin = permissionApi(['*'])
    expect(canExportPrivateKey('certificate', admin)).toBe(true)
    const scoped = permissionApi(['read:certificates', 'read:private_keys'])
    expect(canExportPrivateKey('certificate', scoped)).toBe(true)
  })

  it('requires write:cas and read:private_keys for a CA, and never an HSM-held key', () => {
    const operator = permissionApi(OPERATOR_PERMISSIONS)
    expect(canExportPrivateKey('ca', operator)).toBe(false)
    const admin = permissionApi(['*'])
    expect(canExportPrivateKey('ca', admin)).toBe(true)
    expect(canExportPrivateKey('ca', { ...admin, usesHsm: true })).toBe(false)
    const scoped = permissionApi(['read:cas', 'write:cas', 'read:private_keys'])
    expect(canExportPrivateKey('ca', scoped)).toBe(true)
    const keysOnly = permissionApi(['read:cas', 'read:private_keys'])
    expect(canExportPrivateKey('ca', keysOnly)).toBe(false)
  })

  it('asks for no key scope on a user certificate, as the route does not', () => {
    const viewer = permissionApi(['read:certificates', 'read:user_certificates'])
    expect(canExportPrivateKey('user_certificate', viewer)).toBe(true)
  })

  it('refuses an entity type it does not know', () => {
    expect(canExportPrivateKey('mystery', permissionApi(['*']))).toBe(false)
  })
})

describe('certificate surfaces agree on the same state', () => {
  const operator = permissionApi(OPERATOR_PERMISSIONS)

  it('hides PKCS#12 and JKS in the row dialog for an Operator', () => {
    render(
      <ExportModal
        open
        onClose={() => {}}
        entityType="certificate"
        entityName={CERT.common_name}
        hasPrivateKey
        canExportKey={canExportPrivateKey('certificate', operator)}
        onExport={vi.fn()}
      />
    )
    KEY_FORMATS.forEach(label => expect(screen.queryByText(label)).toBeNull())
    expect(screen.getByText('PEM')).toBeInTheDocument()
  })

  it('hides them in the detail panel too, for that same Operator', () => {
    render(
      <CertificateDetails
        certificate={CERT}
        onExport={vi.fn()}
        canWrite={operator.canWrite('certificates')}
        canExportKey={canExportPrivateKey('certificate', operator)}
        canDelete={false}
      />
    )
    fireEvent.click(screen.getByTitle('export.title'))
    KEY_FORMATS.forEach(label => expect(screen.queryByText(label)).toBeNull())
    // The panel still exports the certificate itself.
    expect(screen.getByText('PEM')).toBeInTheDocument()
  })

  it('offers them on both surfaces to a holder of read:private_keys', () => {
    const admin = permissionApi(['*'])
    const { unmount } = render(
      <ExportModal
        open
        onClose={() => {}}
        entityType="certificate"
        entityName={CERT.common_name}
        hasPrivateKey
        canExportKey={canExportPrivateKey('certificate', admin)}
        onExport={vi.fn()}
      />
    )
    KEY_FORMATS.forEach(label => expect(screen.getByText(label)).toBeInTheDocument())
    unmount()

    render(
      <CertificateDetails
        certificate={CERT}
        onExport={vi.fn()}
        canWrite
        canExportKey={canExportPrivateKey('certificate', admin)}
        canDelete={false}
      />
    )
    fireEvent.click(screen.getByTitle('export.title'))
    KEY_FORMATS.forEach(label => expect(screen.getByText(label)).toBeInTheDocument())
  })
})
