/**
 * The mTLS trusted CA also signs the enrolled certificates: its picker lists the
 * CAs able to sign, keeps the saved one visible and counts the others (#426).
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

import SecuritySection from '../SecuritySection'

const CAS = [
  { id: 1, refid: 'sign', descr: 'Signing CA', has_private_key: true },
  { id: 2, refid: 'keyless', descr: 'Keyless root', certificate_only: true, has_private_key: false },
  { id: 3, refid: 'revoked', descr: 'Revoked CA', has_private_key: true, revoked: true },
]

function renderPicker(trustedCaId) {
  render(<SecuritySection settings={{}} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
    hasPermission={() => true} encryptionStatus={null} setShowEnableEncryptionModal={vi.fn()}
    setShowDisableEncryptionModal={vi.fn()} anomalies={[]} anomaliesLoading={false} loadAnomalies={vi.fn()}
    mtlsSettings={{ enabled: true, trusted_ca_id: trustedCaId }} setMtlsSettings={vi.fn()}
    mtlsLoading={false} mtlsSaving={false} handleMtlsSave={vi.fn()} cas={CAS} />)
  const field = screen.getByTestId('field-settings.mtls.trustedCA')
  return { field, labels: within(field).getAllByRole('option').map((o) => o.textContent) }
}

describe('SecuritySection mTLS trusted CA picker (#426)', () => {
  it('offers only the CA that can sign and counts the others', () => {
    const { field, labels } = renderPicker(undefined)
    expect(labels).toEqual(['Signing CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
  })

  it('keeps the saved CA listed even when it can no longer sign', () => {
    const { field, labels } = renderPicker('revoked')
    expect(labels).toEqual(['Signing CA', 'Revoked CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:1')
  })
})
