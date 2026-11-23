/**
 * The typed rows of a certificate's Aperçu outside « Identité et clé »: the open ACME failure and
 * « Plus de détails » in Facts, a DN on a long row, the CT logs and the references copyable whole, a
 * compliance criterion's reason under its score, nothing left in a bare dl.props.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import en from '../../../i18n/locales/en.json'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => {
      const vars = typeof opts === 'object' && opts ? opts : {}
      const template = lookup(key) ?? (typeof opts === 'string' ? opts : key)
      return String(template).replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
    },
  }),
}))
const acme = vi.hoisted(() => ({ allowed: false, getClientOrders: vi.fn() }))
vi.mock('../../../hooks', () => ({ usePermission: () => ({ hasPermission: () => acme.allowed }) }))
vi.mock('../../../services/acme.service', () => ({ acmeService: { getClientOrders: (...a) => acme.getClientOrders(...a) } }))
vi.mock('../../../components/deploy/CertDeploySection', () => ({ CertDeploySection: () => <section data-testid="cert-deploy" /> }))

import { OverviewPanel } from '../inspector/OverviewPanel'

const LOG = 'https://ct.googleapis.com/logs/us1/argon2026h2/'
const base = {
  id: 7, common_name: 'pc.example.com', subject: 'CN=pc.example.com,O=Example,C=FR', issuer: 'CN=Issuing CA,O=Example,C=FR',
  serial_number: '42', valid_to: '2030-01-01T00:00:00Z', has_private_key: true, status: 'valid', cert_type: 'server_cert',
  refid: '5f0c2a1e-9b7d-4c1e-8a20-3d6f1b2c9e44', caref: 'a1b2c3d4', created_at: '2026-01-01T00:00:00Z',
}
let writeText

beforeEach(() => {
  acme.allowed = false
  acme.getClientOrders.mockReset()
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
})

const more = () => {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(en.inspector.cert.moreDetails) }))
  return document.querySelector('.advanced-panel')
}
const section = (title) => within(more()).getByText(title, { selector: 'h3' }).closest('section')
const rowOf = (scope, label) => within(scope).getByText(label, { selector: 'dt' }).closest('div.row')

describe('« Plus de détails » in typed rows', () => {
  it('leaves no bare dl.props in the overview', () => {
    const { container } = render(<OverviewPanel cert={{ ...base, compliance: { breakdown: { key_strength: { score: 20, max: 25, reason: 'weak' } } } }} title="pc" />)
    more()
    expect(container.querySelector('dl.props')).toBeNull()
    expect(container.querySelectorAll('.advanced-panel dl.kv').length).toBe(4)
  })

  it('puts a DN on a long row, the absent revocation not shown', () => {
    render(<OverviewPanel cert={base} title="pc" />)
    const subject = section(en.common.subject)
    expect(rowOf(subject, en.details.subjectDN)).toHaveClass('long')
    expect(rowOf(subject, en.details.issuerDN)).toHaveClass('long')
    expect(rowOf(subject, en.details.subjectDN).querySelector('dd.v')).toHaveTextContent('CN=pc.example.com,O=Example,C=FR')
    expect(within(subject).queryByText(en.details.revokedAt)).toBeNull()
  })

  it('gives each CT log as a URL copied whole, and the absence of SCTs in grey', async () => {
    const { unmount } = render(<OverviewPanel cert={{ ...base, ct_scts: [{ log_url: LOG }] }} title="pc" />)
    const row = rowOf(section(en.common.fingerprints), en.certificates.ctScts)
    expect(row.querySelector('dd.v .code-value.url')).toBeTruthy()
    fireEvent.click(within(row).getByRole('button', { name: en.protocols.copyValue.replace('{{name}}', en.certificates.ctScts) }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(LOG))
    unmount()
    render(<OverviewPanel cert={base} title="pc" />)
    const none = rowOf(section(en.common.fingerprints), en.certificates.ctScts)
    expect(none.querySelector('dd.absent')).toHaveTextContent(en.certificates.ctNoScts)
    expect(none.querySelector('dd.v')).toBeNull()
  })

  it('says a criterion\'s score, its reason under it', () => {
    render(<OverviewPanel cert={{ ...base, compliance: { breakdown: { key_strength: { score: 20, max: 25, reason: 'weak' } } } }} title="pc" />)
    const row = rowOf(section(en.compliance.title), en.compliance.criteria.key_strength)
    const value = row.querySelector('dd.v')
    expect(value.firstChild.textContent).toBe('20/25')
    expect(value.querySelector('.sub')).toHaveTextContent(en.compliance.reasons.weak)
  })

  it('copies a reference whole', async () => {
    render(<OverviewPanel cert={base} title="pc" />)
    const row = rowOf(section(en.details.metadata), en.details.referenceId)
    expect(row.querySelector('dd.v .code-value')).toHaveTextContent(base.refid)
    fireEvent.click(within(row).getByRole('button', { name: en.protocols.copyValue.replace('{{name}}', en.details.referenceId) }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(base.refid))
  })
})

describe('the open ACME failure', () => {
  it('says the error on a long row, the order and the domain under it', async () => {
    acme.allowed = true
    acme.getClientOrders.mockResolvedValue({ data: [{ id: 31, certificate_id: 7, error_message: 'DNS problem: NXDOMAIN looking up TXT', primary_domain: 'pc.example.com', challenge_type: 'dns-01', status: 'invalid' }] })
    render(<OverviewPanel cert={{ ...base, source: 'acme_client' }} title="pc" />)
    const box = await screen.findByTestId('acme-last-failure')
    expect(box).toHaveClass('kv')
    const row = rowOf(box, en.inspector.cert.lastFailure)
    expect(row).toHaveClass('long')
    expect(row.querySelector('dd.v')).toHaveTextContent(/^DNS problem: NXDOMAIN looking up TXT/)
    expect(row.querySelector('dd.v .sub')).toHaveTextContent('pc.example.com · DNS-01')
  })
})
