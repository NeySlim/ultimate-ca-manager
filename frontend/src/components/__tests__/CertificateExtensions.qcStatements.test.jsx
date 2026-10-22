/** Decoded qcStatements (backend key `qc_statements`) shown with the other extensions. */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import '../../pages/__tests__/pageRenderingSetup.jsx'

import { CertificateExtensions } from '../CertificateExtensions'

const qc = {
  compliance: true, type: 'esign', sscd: true, semantics: 'eidas-natural', retention_period: 10,
  pds: [{ url: 'https://pki.example/pds_en.pdf', language: 'en' }],
  limit_value: { currency: 'EUR', amount: 5000, exponent: 0 },
}

describe('CertificateExtensions, qcStatements', () => {
  it('renders the decoded statements', () => {
    render(<CertificateExtensions extensions={{ qc_statements: qc }} />)
    expect(screen.getByText('details.ext.qcStatements')).toBeTruthy()
    expect(screen.getByText('details.ext.qc.compliance')).toBeTruthy()
    expect(screen.getByText('details.ext.qc.sscd')).toBeTruthy()
    expect(screen.getByText('https://pki.example/pds_en.pdf')).toBeTruthy()
    expect(screen.getByText(/5000e0 EUR/)).toBeTruthy()
  })

  it('lists every QcType of an imported certificate', () => {
    render(<CertificateExtensions extensions={{ qc_statements: { type: ['esign', 'web'] } }} />)
    expect(screen.getByText(/esign, web/)).toBeTruthy()
  })

  it('renders nothing for it when the key is absent', () => {
    render(<CertificateExtensions extensions={{ key_usage: { usages: ['digitalSignature'] } }} />)
    expect(screen.queryByText('details.ext.qcStatements')).toBeNull()
  })
})
