/**
 * The issuing CA picker of the ACME proxy domain form lists the CAs able to
 * sign, keeps the domain's own CA visible and counts the others (#426).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key) }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
// A native select exposes the options and the helper text that the real one hides in a portal.
vi.mock('../../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, helperText }) => (
    <div data-testid={`field-${label}`}>
      <select aria-label={label} value={value ?? ''} onChange={() => {}}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
}))

import DomainForm from '../DomainForm'

const CAS = [
  { id: 1, common_name: 'Signing CA', has_private_key: true },
  { id: 2, common_name: 'Keyless root', certificate_only: true, has_private_key: false },
  { id: 3, common_name: 'Offline CA', has_private_key: true, offline: true },
]

function renderForm(domain) {
  render(<DomainForm domain={domain} dnsProviders={[{ id: 9, name: 'dns', provider_type: 'x' }]} cas={CAS}
    onSubmit={vi.fn()} onCancel={vi.fn()} />)
  const field = screen.getByTestId('field-acme.issuingCA')
  return { field, labels: within(field).getAllByRole('option').filter((o) => o.value !== '').map((o) => o.textContent) }
}

describe('DomainForm issuing CA picker (#426)', () => {
  it('offers only the CA that can sign and counts the others', () => {
    const { field, labels } = renderForm(undefined)
    expect(labels).toEqual(['Signing CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
  })

  it('keeps the domain CA without a key listed and counts one less', () => {
    const { field, labels } = renderForm({ domain: 'x.example', issuing_ca_id: 2 })
    expect(labels).toEqual(['Signing CA', 'Keyless root'])
    expect(field).toHaveTextContent('cas.notListedForSigning:1')
  })
})
