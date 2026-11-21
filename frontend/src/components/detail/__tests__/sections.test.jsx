/**
 * Every panel renders the headings of the requested `section` and none of the
 * others; `all` renders the union.
 */
import { render, screen, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
vi.mock('../../deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))
vi.mock('../../cas/CACrlSection', () => ({ CACrlSection: () => null }))
vi.mock('../../cas/CrossCertificatesSection', () => ({ CrossCertificatesSection: () => null }))
vi.mock('../../cas/ChainUsageSection', () => ({ ChainUsageSection: () => null }))
vi.mock('../../cas/SignatureSchemeField', () => ({ SignatureSchemeField: () => null }))
vi.mock('../../cas/ComplianceProfileField', () => ({ ComplianceProfileField: () => null }))
vi.mock('../../cas/IssuanceVisibilityField', () => ({ IssuanceVisibilityField: () => null }))

import { CertificatePanel } from '../CertificatePanel'
import { CAPanel } from '../CAPanel'
import { TrustCertPanel } from '../TrustCertPanel'
import { CSRPanel } from '../CSRPanel'
import { DETAIL_SECTIONS } from '../sections'

const PEM = '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----'
const FUTURE = '2090-01-01T00:00:00Z'

const CERT = {
  id: 1, common_name: 'web.example.com', subject: 'CN=web.example.com', issuer: 'CN=Test CA',
  serial_number: '42', valid_from: '2024-01-01T00:00:00Z', valid_to: FUTURE, status: 'valid',
  key_algorithm: 'EC-P256', key_type: 'EC-P256', has_private_key: true, pem: PEM,
  thumbprint_sha256: 'aa', thumbprint_sha1: 'bb', created_at: '2024-01-01T00:00:00Z',
  ct_scts: [], compliance: { grade: 'A', score: 90 },
  chain_status: { status: 'complete', chain: [] },
  revoked: true, revoked_at: '2025-01-01T00:00:00Z', revoke_reason: 'superseded',
  extensions: {
    key_usage: { usages: ['digitalSignature'] },
    subject_alt_names: { entries: [{ type: 'DNS', value: 'web.example.com' }] },
  },
}
const CA = {
  id: 2, common_name: 'Sub CA', subject: 'CN=Sub CA', issuer: 'CN=Root', is_root: false,
  serial_number: '7', valid_from: '2024-01-01T00:00:00Z', valid_to: FUTURE, key_type: 'RSA 3072',
  has_private_key: true, pem: PEM, thumbprint_sha256: 'aa', thumbprint_sha1: 'bb',
  path_length: 0, cdp_enabled: true, cdp_url: 'http://crl', created_at: '2024-01-01T00:00:00Z',
  extensions: { key_usage: { usages: ['keyCertSign'] } },
}
const TRUST = {
  id: 3, name: 'Root', subject: 'CN=Root', issuer: 'CN=Root', serial_number: '1',
  not_before: '2024-01-01T00:00:00Z', not_after: FUTURE, key_type: 'RSA 2048',
  certificate_pem: PEM, fingerprint_sha256: 'aa', fingerprint_sha1: 'bb', added_at: '2024-01-01T00:00:00Z',
}
const CSR = {
  id: 4, common_name: 'csr.example.com', key_algorithm: 'RSA', key_size: 2048,
  created_at: '2024-01-01T00:00:00Z', sans: ['csr.example.com'], pem: PEM,
}
const SIGNED = {
  id: 5, common_name: 'signed.example.com', signed_by: 'CA', valid_from: '2024-01-01T00:00:00Z',
  valid_to: FUTURE, days_remaining: 100, key_algorithm: 'RSA', key_size: 2048,
}

const OVERVIEW_CERT = ['common.subject', 'common.validity', 'common.technicalDetails', 'details.subjectAltNames',
  'certificates.ctScts', 'common.issuer', 'compliance.title', 'common.fingerprints', 'details.revocationDetails', 'details.metadata']
const OVERVIEW_CA = ['common.subject', 'common.issuer', 'common.validity', 'common.technicalDetails',
  'cas.rfc5280Constraints', 'details.revocationConfig', 'common.fingerprints', 'details.metadata']
const OVERVIEW_TRUST = ['common.subject', 'common.issuer', 'common.validity', 'common.technicalDetails',
  'common.fingerprints', 'details.metadata']

const PANELS = [
  { name: 'CertificatePanel', ui: (section) => <CertificatePanel certificate={CERT} section={section} />,
    expected: { overview: OVERVIEW_CERT, chain: ['common.issuer', 'details.chainValidation'],
      extensions: ['details.extensions'], pem: ['details.pemCertificate'] } },
  { name: 'CAPanel', ui: (section) => <CAPanel ca={CA} section={section} />,
    expected: { overview: OVERVIEW_CA, chain: ['common.issuer'],
      extensions: ['details.extensions'], pem: ['details.pemCertificate'] } },
  { name: 'TrustCertPanel', ui: (section) => <TrustCertPanel cert={TRUST} section={section} />,
    expected: { overview: OVERVIEW_TRUST, chain: ['common.issuer'], extensions: [], pem: ['details.pemCertificate'] } },
  { name: 'CSRPanel (pending)', ui: (section) => <CSRPanel csr={CSR} section={section} />,
    expected: { overview: ['common.subject', 'common.keyInformation', 'common.subjectAltNames', 'common.timeline'],
      chain: [], extensions: [], pem: ['details.csrPem'] } },
  { name: 'CSRPanel (signed)', ui: (section) => <CSRPanel csr={SIGNED} variant="signed" section={section} />,
    expected: { overview: ['common.signingDetails', 'common.subject', 'common.keyInformation', 'common.timeline'],
      chain: [], extensions: [], pem: [] } },
]

afterEach(cleanup)

describe.each(PANELS)('$name sections', ({ ui, expected }) => {
  const every = [...new Set(Object.values(expected).flat())]

  it.each(DETAIL_SECTIONS.filter(s => s !== 'all'))('%s renders its headings and no other', (section) => {
    render(ui(section))
    for (const heading of every) {
      const shown = screen.queryAllByText(heading).length > 0
      expect(shown, `${heading} in section ${section}`).toBe(expected[section].includes(heading))
    }
  })

  it('all renders the union', () => {
    render(ui('all'))
    for (const heading of every) {
      expect(screen.queryAllByText(heading).length, heading).toBeGreaterThan(0)
    }
  })

  it('defaults to all', () => {
    render(ui(undefined))
    for (const heading of every) {
      expect(screen.queryAllByText(heading).length, heading).toBeGreaterThan(0)
    }
  })
})
