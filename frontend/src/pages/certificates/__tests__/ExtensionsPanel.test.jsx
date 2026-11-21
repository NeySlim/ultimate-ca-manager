/**
 * The Extensions panel of the zone dock: decoded qcStatements and the extensions without a
 * section of their own (#437), which the shell's certificate panel showed before it was retired.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))

import { ExtensionsPanel } from '../inspector/ExtensionsPanel'

const LONG = 'ab'.repeat(40)
const other = [
  { oid: '1.3.6.1.4.1.99999.1', name: null, critical: true, value_hex: LONG },
  { oid: '1.3.6.1.5.5.7.1.24', name: 'TLSFeature', critical: false, value_hex: '3003020105' },
]
const qc = {
  compliance: true, type: 'esign', sscd: true, semantics: 'eidas-natural', retention_period: 10,
  pds: [{ url: 'https://pki.example/pds_en.pdf', language: 'en' }],
  limit_value: { currency: 'EUR', amount: 5000, exponent: 0 },
}
const row = (label) => screen.getAllByRole('term').find((dt) => dt.textContent.startsWith(label)).closest('.extension')

describe('ExtensionsPanel, qcStatements', () => {
  it('words every decoded statement, the transaction limit included', () => {
    render(<ExtensionsPanel cert={{ extensions: { qc_statements: qc } }} />)
    const dd = row('Qualified Certificate Statements').querySelector('dd')
    for (const part of ['QcCompliance', 'QcSSCD', 'QcType: esign', 'Semantics: eidas-natural', 'QcRetentionPeriod: 10', 'QcPDS en: https://pki.example/pds_en.pdf', 'QcLimitValue: 5000e0 EUR']) {
      expect(dd.textContent).toContain(part)
    }
  })

  it('lists every QcType of an imported certificate', () => {
    render(<ExtensionsPanel cert={{ extensions: { qc_statements: { type: ['esign', 'web'] } } }} />)
    expect(row('Qualified Certificate Statements')).toHaveTextContent('QcType: esign, web')
  })
})

describe('ExtensionsPanel, other extensions', () => {
  it('shows OID, name, criticality and the value truncated, the whole value in its title', () => {
    render(<ExtensionsPanel cert={{ extensions: { other_extensions: other } }} />)
    const unnamed = row('1.3.6.1.4.1.99999.1')
    expect(unnamed.querySelector('small')).toHaveTextContent('1.3.6.1.4.1.99999.1 · inspector.cert.critical')
    expect(unnamed.querySelector('dd')).toHaveAttribute('title', LONG)
    expect(unnamed.querySelector('dd').textContent).toContain(`${LONG.slice(0, 48)}…`)
    expect(row('TLSFeature').querySelector('small')).not.toHaveTextContent('inspector.cert.critical')
    expect(row('TLSFeature')).toHaveTextContent('3003020105')
  })

  it('copies the full value of a raw extension', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
    render(<ExtensionsPanel cert={{ extensions: { other_extensions: other } }} />)
    fireEvent.click(screen.getAllByRole('button', { name: 'details.ext.copyValue' })[0])
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(LONG))
  })

  it('offers no copy for a decoded extension', () => {
    render(<ExtensionsPanel cert={{ extensions: { key_usage: { usages: ['digitalSignature'] } } }} />)
    expect(screen.queryByRole('button', { name: 'details.ext.copyValue' })).toBeNull()
  })
})
