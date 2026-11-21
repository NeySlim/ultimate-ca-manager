/** #437: extensions without a section of their own (backend key `other_extensions`). */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '../../../pages/__tests__/pageRenderingSetup.jsx'

import { CertificateExtensions } from '../CertificateExtensions'

const LONG = 'ab'.repeat(40)
const other = [
  { oid: '1.3.6.1.4.1.99999.1', name: null, critical: true, value_hex: LONG },
  { oid: '1.3.6.1.5.5.7.1.24', name: 'TLSFeature', critical: false, value_hex: '3003020105' },
]

describe('CertificateExtensions, other extensions', () => {
  it('shows OID, name, criticality and the value truncated', () => {
    render(<CertificateExtensions extensions={{ other_extensions: other }} />)
    expect(screen.getByText('details.ext.otherExtensions')).toBeTruthy()
    expect(screen.getByText('1.3.6.1.4.1.99999.1')).toBeTruthy()
    expect(screen.getByText('TLSFeature')).toBeTruthy()
    expect(screen.getAllByText('Critical')).toHaveLength(1)
    const shown = screen.getByTitle(LONG)
    expect(shown.textContent).toBe(`${LONG.slice(0, 48)}…`)
    expect(screen.getByText('3003020105')).toBeTruthy()
  })

  it('copies the full value', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
    render(<CertificateExtensions extensions={{ other_extensions: other }} />)
    fireEvent.click(screen.getAllByLabelText('details.ext.copyValue')[0])
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(LONG))
  })

  it('renders no such block without the key', () => {
    render(<CertificateExtensions extensions={{ key_usage: { usages: ['digitalSignature'] } }} />)
    expect(screen.queryByTestId('other-extensions')).toBeNull()
  })
})
