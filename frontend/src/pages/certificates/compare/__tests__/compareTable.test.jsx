/**
 * The comparison table: an identical line merged across the certificates and marked so, a line that
 * differs kept one cell per certificate with the elements one has alone marked, and the summary
 * counting the differences among the properties.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'en' } }),
}))
vi.mock('../../../../services', () => ({ certificatesService: { getById: vi.fn() } }))

import { CompareTable } from '../CompareView'

const cert = (id, cn, names, extra = {}) => ({
  id, common_name: cn, subject: `CN=${cn}`, issuer: 'CN=Root', valid_from: '2026-01-01T00:00:00Z', valid_to: '2027-01-01T00:00:00Z',
  key_type: 'RSA 2048', serial_number: String(id), thumbprint_sha1: `S1${id}`, thumbprint_sha256: `S2${id}`,
  extensions: { subject_alt_names: { entries: names.map((value) => ({ type: 'DNS', value })) }, key_usage: { usages: ['digitalSignature'] } },
  ...extra,
})

const line = (c, key) => c.querySelector(`tr[data-row="${key}"]`)

describe('CompareTable', () => {
  it('merges an identical line into one cell across the certificates, marked identical', () => {
    const certs = [cert(1, 'a.example', ['a.example', 'www.example']), cert(2, 'b.example', ['b.example', 'www.example']), cert(3, 'c.example', ['www.example'])]
    const { container } = render(<CompareTable certs={certs} />)
    const issuer = line(container, 'issuer')
    expect(issuer).not.toHaveClass('different')
    const cells = issuer.querySelectorAll('td')
    expect(cells).toHaveLength(1)
    expect(cells[0]).toHaveAttribute('colspan', '3')
    expect(cells[0]).toHaveTextContent('compare.identical')
    expect(cells[0]).toHaveTextContent('CN=Root')
    // A line that differs keeps a cell per certificate
    expect(line(container, 'subject')).toHaveClass('different')
    expect(line(container, 'subject').querySelectorAll('td')).toHaveLength(3)
  })

  it('marks in a list the element a certificate has alone, the shared one plain', () => {
    const certs = [cert(1, 'a.example', ['a.example', 'www.example']), cert(2, 'b.example', ['www.example'])]
    const { container } = render(<CompareTable certs={certs} />)
    const [first, second] = line(container, 'san').querySelectorAll('td')
    expect([...first.querySelectorAll('li')].map((li) => [li.className, li.firstChild.textContent])).toEqual([['only', 'DNS: a.example'], ['common', 'DNS: www.example']])
    expect([...second.querySelectorAll('li')].map((li) => li.className)).toEqual(['common'])
    // The mark is read out, not only drawn
    expect(first.querySelector('li.only .sr-only')).toHaveTextContent('compare.notInAll')
  })

  it('marks no element when each certificate holds a single one: the line differs as a whole', () => {
    const certs = [cert(1, 'a.example', ['a.example']), cert(2, 'b.example', ['b.example'])]
    const { container } = render(<CompareTable certs={certs} />)
    const san = line(container, 'san')
    expect(san).toHaveClass('different')
    expect([...san.querySelectorAll('li')].map((li) => [li.className, li.textContent])).toEqual([['', 'DNS: a.example'], ['', 'DNS: b.example']])
  })

  it('shows an absent list as the absence mark, its line a difference', () => {
    const certs = [cert(1, 'a.example', ['a.example']), cert(2, 'b.example', [], { extensions: {} })]
    const { container } = render(<CompareTable certs={certs} />)
    const [, second] = line(container, 'san').querySelectorAll('td')
    expect(second.querySelector('li')).toBeNull()
    expect(second).toHaveTextContent('—')
  })

  it('sums up the differences among the properties, and the filter keeps only the differences', () => {
    const certs = [cert(1, 'a.example', ['www.example']), cert(2, 'b.example', ['www.example'])]
    const { container } = render(<CompareTable certs={certs} />)
    const total = container.querySelectorAll('tbody tr').length
    const differing = container.querySelectorAll('tbody tr.different').length
    // subject, sha1, sha256, serial differ; the rest is identical
    expect(differing).toBe(4)
    expect(screen.getByText(`compare.differences ${JSON.stringify({ count: 4, total })}`)).toBeInTheDocument()
    // A count, neither a warning nor a deadline: a neutral pill
    expect(screen.getByText(`compare.differences ${JSON.stringify({ count: 4, total })}`).closest('.badge').className).toBe('badge')
    fireEvent.click(screen.getByRole('checkbox', { name: 'compare.onlyDifferences' }))
    expect(container.querySelectorAll('tbody tr')).toHaveLength(4)
    expect(container.querySelectorAll('tbody td[colspan]')).toHaveLength(0)
    expect(within(container.querySelector('tbody')).getAllByRole('rowheader').map((h) => h.firstChild.textContent)).toEqual(['common.subject', 'common.fingerprints SHA-1', 'common.fingerprints SHA-256', 'inspector.cert.serial'])
  })
})
