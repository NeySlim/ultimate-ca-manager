/**
 * The export dialog is the mockup's: its title names the object, the formats are radio
 * buttons of one group with no capitals heading, the options are one line each, and a
 * structure preview says what the file will hold as the options change.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts === 'object' && opts.format ? `${key}:${opts.format}` : key),
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

import { ExportModal } from '../ExportModal'

const renderModal = (props = {}) => render(
  <ExportModal open onClose={() => {}} entityType="certificate" entityName="web.example.com"
    hasPrivateKey canExportKey onExport={vi.fn().mockResolvedValue(undefined)} {...props} />
)
const preview = () => screen.getByTestId('export-preview').textContent

describe('ExportModal at the mockup', () => {
  it('names the certificate or the CA in its title', () => {
    const { unmount } = renderModal()
    expect(screen.getByRole('heading', { name: 'export.titleCertificate' })).toBeInTheDocument()
    unmount()
    renderModal({ entityType: 'ca' })
    expect(screen.getByRole('heading', { name: 'export.titleCa' })).toBeInTheDocument()
  })

  it('offers every format as a radio button of one group, PEM checked', () => {
    renderModal()
    const group = screen.getByRole('radiogroup', { name: 'export.format' })
    const radios = [...group.querySelectorAll('input[type="radio"]')]
    expect(radios.map((r) => r.value)).toEqual(['pem', 'der', 'pkcs7', 'pkcs12', 'jks', 'key'])
    expect(radios[0]).toBeChecked()
    // The words of the mockup; no capitals heading over the formats or the options
    expect(screen.getByText('PKCS#12')).toBeInTheDocument()
    expect(document.querySelector('.uppercase')).toBeNull()
    fireEvent.click(radios[1])
    expect(radios[1]).toBeChecked()
    expect(radios[0]).not.toBeChecked()
  })

  it('keeps the chain on one line and previews what the file holds', () => {
    renderModal()
    const chain = screen.getByLabelText('export.includeChain')
    expect(chain).toBeChecked()
    expect(chain.closest('label')).not.toHaveClass('has-desc')
    expect(preview()).toBe(['export.previewTitle:PEM', '', 'web.example.com', '  export.previewChain'].join('\n'))
    fireEvent.click(screen.getByLabelText('export.includeKey'))
    expect(preview()).toContain('  export.previewKey')
    fireEvent.click(chain)
    expect(preview()).not.toContain('export.previewChain')
  })

  it('says the PKCS#12 key is encrypted by the password, and holds the password field', () => {
    renderModal()
    fireEvent.click(screen.getByLabelText(/PKCS#12/))
    expect(screen.getByLabelText('export.password')).toHaveAttribute('type', 'password')
    expect(preview()).toContain('export.previewTitle:PKCS#12')
    expect(preview()).toContain('  export.previewKeyEncrypted')
    expect(screen.getByText('export.pkcs12Note').closest('.ui-notice')).not.toBeNull()
  })

  it('shows DER alone, with no option to carry', () => {
    renderModal()
    fireEvent.click(screen.getByLabelText(/DER/))
    expect(screen.queryByLabelText('export.includeChain')).toBeNull()
    expect(preview()).toBe(['export.previewTitle:DER', '', 'web.example.com'].join('\n'))
  })
})
