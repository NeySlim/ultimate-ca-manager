/**
 * The chain of trust in Aperçu: a vertical tree from the anchor down to the certificate, each node
 * with its role in small, the certificate as the current node with its state when it lapsed, the
 * product's authorities clickable; and the order of the sections, the chain under the validity.
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

const base = {
  id: 7, common_name: 'web.example.com', subject: 'CN=web.example.com', serial_number: '42', status: 'valid',
  valid_from: '2026-01-01T00:00:00Z', valid_to: '2030-01-01T00:00:00Z', issuer_name: 'Issuing CA',
  chain_status: { status: 'complete', chain: [{ name: 'Issuing CA', type: 'managed_ca' }, { name: 'Root CA', type: 'managed_ca' }] },
}
const nodes = () => [...document.querySelectorAll('.chain-mini > li')]
const nameOf = (li) => li.querySelector('.chain-name').textContent
const roleOf = (li) => li.querySelector('.chain-role').textContent

describe('the chain of trust in Aperçu', () => {
  it('names each node and gives its role in small, anchor first', () => {
    render(<OverviewPanel cert={base} title="web.example.com" />)
    expect(nodes().map(nameOf)).toEqual(['Root CA', 'Issuing CA', 'web.example.com'])
    expect(nodes().map(roleOf)).toEqual(['Root CA', 'Intermediate CA', 'This certificate'])
  })

  it('marks the certificate as the current node, not as a link', () => {
    render(<OverviewPanel cert={base} title="web.example.com" openCa={vi.fn()} />)
    const leaf = nodes().at(-1)
    expect(leaf).toHaveAttribute('aria-current', 'true')
    expect(leaf).toHaveClass('current')
    expect(leaf.querySelector('button, a, .text-link')).toBeNull()
    expect(nodes().filter((li) => li.getAttribute('aria-current'))).toHaveLength(1)
  })

  it('opens an authority of the product from the chain, the root of a managed chain staying text', () => {
    const openCa = vi.fn()
    render(<OverviewPanel cert={base} title="web.example.com" openCa={openCa} />)
    const chain = document.querySelector('.chain-mini')
    const go = within(chain).getByRole('button', { name: 'Issuing CA' })
    expect(go).toHaveAttribute('data-ca-go', 'Issuing CA')
    fireEvent.click(go)
    expect(openCa).toHaveBeenCalledWith('Issuing CA', { issuing: true })
    expect(within(chain).getAllByRole('button')).toHaveLength(1)
  })

  it('marks the anchor of a trust store, never clickable', () => {
    const cert = { ...base, chain_status: { status: 'complete', chain: [{ name: 'Issuing CA', type: 'managed_ca' }, { name: 'Corp Root', type: 'trust_store' }] } }
    render(<OverviewPanel cert={cert} title="web.example.com" openCa={vi.fn()} />)
    const anchor = nodes()[0]
    expect(nameOf(anchor)).toBe('Corp Root')
    expect(roleOf(anchor)).toBe('Root CA · trust store')
    expect(anchor.querySelector('button')).toBeNull()
  })

  it.each([
    [{ status: 'expired', valid_to: '2026-02-01T00:00:00Z' }, 'Expired', 'bad'],
    [{ status: 'revoked', revoked: true }, 'Revoked', 'muted'],
  ])('shows the state of a lapsed certificate in words beside its node (%o)', (fields, label, tone) => {
    render(<OverviewPanel cert={{ ...base, ...fields }} title="web.example.com" />)
    const state = nodes().at(-1).querySelector('.badge')
    expect(state).toHaveTextContent(label)
    expect(state).toHaveClass(tone)
    // Words beside the colour, an icon too
    expect(state.querySelector('svg')).not.toBeNull()
  })

  it('says nothing of the state of a certificate in force', () => {
    render(<OverviewPanel cert={base} title="web.example.com" />)
    expect(nodes().at(-1).querySelector('.badge')).toBeNull()
  })
})

describe('the sections of Aperçu', () => {
  it('reads validity, identity, chain, then « More details » right after them', () => {
    render(<OverviewPanel cert={base} title="web.example.com" />)
    const overview = screen.getByTestId('certificate-overview')
    const titles = [...overview.querySelectorAll(':scope > section > .section-title')].map((h) => h.textContent)
    expect(titles).toEqual([en.inspector.cert.validity, en.inspector.cert.identity, en.inspector.cert.chainOfTrust])
    expect(overview.nextElementSibling).toHaveClass('advanced')
  })
})
