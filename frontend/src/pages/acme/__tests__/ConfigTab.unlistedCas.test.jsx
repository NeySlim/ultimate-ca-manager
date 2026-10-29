/**
 * The default issuing CA picker of the ACME settings lists the CAs able to
 * sign, keeps the saved one visible and counts the others (#426).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key) }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../ProfilesEditor', () => ({ default: () => null }))
// A native select exposes the options and the helper text that the real one hides in a portal.
vi.mock('../../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, helperText }) => (
    <div data-testid={`field-${label}`}>
      <select aria-label={label} value={value ?? ''} onChange={() => {}}>
        <option value="">-</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
}))

import ConfigTab from '../ConfigTab'

const CAS = [
  { id: 1, name: 'Signing CA', has_private_key: true },
  { id: 2, name: 'Keyless root', certificate_only: true, has_private_key: false },
  { id: 3, name: 'Offline CA', has_private_key: true, offline: true },
]

function renderTab(issuing_ca_id) {
  render(<ConfigTab acmeSettings={{ enabled: true, profiles: {}, issuing_ca_id }} cas={CAS}
    updateSetting={vi.fn()} canWrite />)
  const field = screen.getByTestId('field-acme.defaultIssuingCA')
  return {
    field,
    labels: within(field).getAllByRole('option').filter((o) => o.value !== '').map((o) => o.textContent),
  }
}

describe('ACME ConfigTab default issuing CA picker (#426)', () => {
  it('offers only the CA that can sign and counts the others', () => {
    const { field, labels } = renderTab(null)
    expect(labels).toEqual(['Signing CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
  })

  it('keeps the saved CA without a key listed and counts one less', () => {
    const { field, labels } = renderTab(2)
    expect(labels).toEqual(['Signing CA', 'Keyless root'])
    expect(field).toHaveTextContent('cas.notListedForSigning:1')
  })
})
