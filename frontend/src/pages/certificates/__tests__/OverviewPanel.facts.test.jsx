/**
 * Facts the shell's certificate panel showed, now in the zone dock's Aperçu: the key named as the
 * registry names it (a post-quantum one with its level), the other member of a hybrid pair
 * (RFC 9763) as a link that opens it, and the Windows enrollment profile that issued it.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
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
vi.mock('../../../hooks', () => ({ usePermission: () => ({ hasPermission: () => false }) }))
vi.mock('../../../services/acme.service', () => ({ acmeService: { getClientOrders: vi.fn() } }))
vi.mock('../../../components/deploy/CertDeploySection', () => ({ CertDeploySection: () => <section data-testid="cert-deploy" /> }))

import { OverviewPanel } from '../inspector/OverviewPanel'
import { GROUP_PQ, KEY_ALGORITHMS } from '../../../lib/keyAlgorithms'

const H = en.certificates.hybrid
const base = {
  id: 7, common_name: 'pc.example.com', subject: 'CN=pc.example.com', serial_number: '42',
  valid_to: '2030-01-01T00:00:00Z', has_private_key: true, status: 'valid',
}
const ident = () => screen.getByText(en.inspector.cert.identity).closest('section')
const value = (label) => within(ident()).getByText(label).nextElementSibling

describe('the key of a certificate in Aperçu', () => {
  const pq = KEY_ALGORITHMS.find((a) => a.group === GROUP_PQ && a.label === 'ML-DSA-65')

  it('names a post-quantum key as the registry does', () => {
    render(<OverviewPanel cert={{ ...base, key_algorithm: pq.label, key_type: pq.label, post_quantum: true }} title="pc" />)
    expect(value(en.common.keyAlgorithm)).toHaveTextContent(pq.display)
  })

  it('keeps an RSA key with its size', () => {
    render(<OverviewPanel cert={{ ...base, key_algorithm: 'RSA', key_type: 'RSA 2048' }} title="pc" />)
    expect(value(en.common.keyAlgorithm)).toHaveTextContent(/^RSA 2048$/)
  })

  it('never calls a key the API did not name RSA', () => {
    render(<OverviewPanel cert={{ ...base, key_algorithm: null, key_type: null, signature_algorithm: null }} title="pc" />)
    expect(value(en.common.keyAlgorithm)).toHaveTextContent('—')
  })
})

describe('a hybrid pair member in Aperçu', () => {
  it('links to the other member by its role and opens it', () => {
    const onOpenRelated = vi.fn()
    render(<OverviewPanel cert={{ ...base, id: 11, related_certificate_id: 12, hybrid_role: 'classical' }} title="pair" onOpenRelated={onOpenRelated} />)
    const link = screen.getByRole('link', { name: H.openRelated.replace('{{id}}', '12') })
    expect(link).toHaveAttribute('href', '/certificates/12')
    expect(link).toHaveTextContent(`#12 (${H.rolePq})`)
    fireEvent.click(link)
    expect(onOpenRelated).toHaveBeenCalledWith(12)
  })

  it('shows no link on a single certificate', () => {
    render(<OverviewPanel cert={base} title="pc" />)
    expect(screen.queryByText(H.relatedCertificate)).toBeNull()
  })
})

describe('the Windows profile under Plus de détails', () => {
  it.each([
    [{ windows_profile_id: 3, windows_profile_name: 'Corp' }, 'Corp'],
    [{ windows_profile_id: 3, windows_profile_name: null }, '#3'],
  ])('names the profile that issued it (%o)', (fields, shown) => {
    render(<OverviewPanel cert={{ ...base, ...fields }} title="pc" />)
    expect(screen.getByText(en.certificates.windowsProfile).nextElementSibling).toHaveTextContent(shown)
  })

  it('says nothing of a profile for a certificate no profile issued', () => {
    render(<OverviewPanel cert={{ ...base, windows_profile_id: null }} title="pc" />)
    expect(screen.queryByText(en.certificates.windowsProfile)).toBeNull()
  })
})

describe('the deployment section under Plus de détails', () => {
  it('sits in the panel among the other sections', () => {
    render(<OverviewPanel cert={base} title="pc" />)
    const deploy = screen.getByTestId('cert-deploy')
    expect(deploy.parentElement).toHaveClass('advanced-panel')
  })
})
