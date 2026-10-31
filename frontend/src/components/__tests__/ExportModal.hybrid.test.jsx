/**
 * A member of a hybrid pair (RFC 9763) exports as 'hybrid-bundle': a ZIP with
 * both certificates and, when allowed, both keys. Other certificates never see it.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import en from '../../i18n/locales/en.json'
import { exportFileName } from '../../lib/exportDownload'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => {
      const vars = typeof opts === 'object' && opts ? opts : {}
      const template = lookup(key) ?? (typeof opts === 'string' ? opts : vars.defaultValue ?? key)
      return String(template).replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
    },
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

import { ExportModal } from '../ExportModal'

const bundleLabel = en.export.formats.hybridBundle
const renderModal = (props = {}) => {
  const onExport = vi.fn().mockResolvedValue(undefined)
  render(<ExportModal open onClose={() => {}} entityName="pair.example.com" onExport={onExport} {...props} />)
  return onExport
}
const submit = () => fireEvent.submit(screen.getByText('PEM').closest('form'))

describe('ExportModal hybrid bundle', () => {
  it('offers the bundle for a pair member and sends hybrid-bundle', async () => {
    const onExport = renderModal({ relatedCertificateId: 12, keyAlgorithm: 'EC-P256' })
    fireEvent.click(screen.getByText(bundleLabel).closest('button'))
    submit()
    await waitFor(() => expect(onExport).toHaveBeenCalledTimes(1))
    expect(onExport.mock.calls[0][0]).toBe('hybrid-bundle')
    expect(onExport.mock.calls[0][1]).toMatchObject({ includeKey: false })
  })

  it('stays available on the ML-DSA member', () => {
    renderModal({ relatedCertificateId: 11, keyAlgorithm: 'ML-DSA-65' })
    expect(screen.getByText(bundleLabel).closest('button')).toBeEnabled()
  })

  it('carries both keys only when the operator may export keys', async () => {
    const onExport = renderModal({ relatedCertificateId: 12, hasPrivateKey: true, canExportKey: true })
    fireEvent.click(screen.getByText(bundleLabel).closest('button'))
    fireEvent.click(screen.getByText(en.export.includeKey).closest('label').querySelector('input'))
    submit()
    await waitFor(() => expect(onExport).toHaveBeenCalledTimes(1))
    expect(onExport.mock.calls[0]).toEqual(['hybrid-bundle', expect.objectContaining({ includeKey: true })])
  })

  it('promises no CA chain the bundle does not carry', async () => {
    const onExport = renderModal({ relatedCertificateId: 12 })
    expect(screen.getByText(en.export.includeChain)).toBeInTheDocument()
    fireEvent.click(screen.getByText(bundleLabel).closest('button'))
    expect(screen.queryByText(en.export.includeChain)).toBeNull()
    submit()
    await waitFor(() => expect(onExport).toHaveBeenCalledTimes(1))
    expect(onExport.mock.calls[0][1]).toMatchObject({ includeChain: false, includeRoot: false })
  })

  it('is absent from a certificate with no linked certificate', () => {
    renderModal({ relatedCertificateId: null })
    expect(screen.queryByText(bundleLabel)).toBeNull()
  })

  it('lands as a .zip file', () => {
    expect(exportFileName('pair.example.com', 'hybrid-bundle')).toBe('pair.example.com.zip')
  })
})
