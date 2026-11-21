/**
 * The zone's export and revocation dialogs (the mockup's exportDialog() and revokeDialog()), and
 * a mockup dialog drawn outside a zone carrying its own scope.
 */
import { fireEvent, render, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ getById: vi.fn(), variants: vi.fn() }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.algorithm ? `${key}:${opts.algorithm}` : key), i18n: { language: 'en' } }),
}))
vi.mock('../../../services', () => ({ certificatesService: { getById: (...a) => mocks.getById(...a) } }))
vi.mock('../../../lib/crossCertificates', () => ({ fetchChainVariants: (...a) => mocks.variants(...a) }))
vi.mock('../../../lib/exportPassword', () => ({
  exportPasswordPolicy: () => ({ min_length: 8, max_length: 64 }),
  loadExportPasswordPolicy: () => Promise.resolve({ min_length: 8, max_length: 64 }),
  isExportPasswordValid: (p) => p.length >= 8,
}))

import { ExportDialog } from '../dialogs/ExportDialog'
import { RevokeDialog } from '../dialogs/RevokeDialog'
import { AtelierDialog, Zone } from '../../../components/atelier'

const dialog = () => document.querySelector('dialog[open]')
beforeEach(() => {
  mocks.getById.mockReset()
  mocks.variants.mockReset()
  mocks.variants.mockResolvedValue([])
})

describe('ExportDialog (exportDialog)', () => {
  const base = { open: true, onClose: vi.fn(), entityName: 'web.example.com', chainVariantsFor: { type: 'certificate', id: 7 } }

  it('draws the formats as cards, the key formats greyed without a key, the chain ticked', async () => {
    render(<Zone><ExportDialog {...base} hasPrivateKey={false} onExport={vi.fn()} /></Zone>)
    const grid = dialog().querySelector('.format-grid')
    const radios = within(grid).getAllByRole('radio')
    expect(radios.map((r) => r.value)).toEqual(['pem', 'der', 'pkcs12', 'pkcs7', 'jks', 'key'])
    expect(radios[0]).toBeChecked()
    expect(within(grid).getByRole('radio', { name: /PKCS#12/ })).toBeDisabled()
    expect(grid.querySelectorAll('.format-option')[2]).toHaveTextContent('export.noPrivateKey')
    expect(within(dialog()).getByRole('checkbox', { name: 'export.includeChain' })).toBeChecked()
    expect(dialog().querySelector('#p12-options')).toHaveAttribute('hidden')
    expect(dialog().querySelector('form')).toBeNull()
  })

  it('asks a password for PKCS#12 and sends the options', async () => {
    const onExport = vi.fn().mockResolvedValue()
    render(<Zone><ExportDialog {...base} hasPrivateKey canExportKey onExport={onExport} /></Zone>)
    fireEvent.click(within(dialog()).getByRole('radio', { name: /PKCS#12/ }))
    expect(dialog().querySelector('#p12-options')).not.toHaveAttribute('hidden')
    const download = within(dialog()).getByRole('button', { name: 'export.download' })
    expect(download).toBeDisabled()
    fireEvent.change(dialog().querySelector('input[type=password]'), { target: { value: 'longenough' } })
    fireEvent.click(download)
    await waitFor(() => expect(onExport).toHaveBeenCalledWith('pkcs12', expect.objectContaining({ includeChain: true, includeKey: true, password: 'longenough', legacy: false })))
  })

  it('says why a post-quantum key cannot go in PKCS#12', async () => {
    render(<Zone><ExportDialog {...base} hasPrivateKey canExportKey keyAlgorithm="ML-DSA-65" onExport={vi.fn()} /></Zone>)
    expect(within(dialog()).getByRole('radio', { name: /PKCS#12/ })).toBeDisabled()
    expect(dialog().querySelectorAll('.format-option')[2]).toHaveTextContent('export.unavailableForKeyAlgorithm:ML-DSA-65')
  })

  it('offers the hybrid bundle only for a pair member', () => {
    mocks.getById.mockResolvedValue({ data: { has_private_key: true } })
    render(<Zone><ExportDialog {...base} relatedCertificateId={12} onExport={vi.fn()} /></Zone>)
    expect(within(dialog()).getByRole('radio', { name: /export\.formats\.hybridBundle/ })).toBeInTheDocument()
  })
})

describe('RevokeDialog (revokeDialog)', () => {
  it('warns, names the certificate, and sends the reason', () => {
    const onConfirm = vi.fn()
    render(<Zone><RevokeDialog open onClose={vi.fn()} onConfirm={onConfirm} certificate={{ id: 7, common_name: 'web.example.com' }} /></Zone>)
    expect(dialog()).toHaveClass('narrow')
    expect(dialog().querySelector('.notice.warn')).toHaveTextContent('revocation.notice')
    expect(dialog()).toHaveTextContent('web.example.com')
    fireEvent.change(within(dialog()).getByRole('combobox'), { target: { value: 'superseded' } })
    expect(dialog()).toHaveTextContent('revocation.hints.superseded')
    fireEvent.click(within(dialog()).getByRole('button', { name: 'revocation.confirm' }))
    expect(onConfirm).toHaveBeenCalledWith('superseded')
  })

  it('leaves the hold out when the certificate is already held', () => {
    render(<Zone><RevokeDialog open allowHold={false} onClose={vi.fn()} onConfirm={vi.fn()} certificate={{ id: 7 }} /></Zone>)
    expect([...dialog().querySelectorAll('option')].map((o) => o.value)).not.toContain('certificateHold')
  })

  it('asks about the other member of a hybrid pair, ticked by default', async () => {
    mocks.getById.mockResolvedValue({ data: { id: 12, related_certificate_id: 7, revoked: false } })
    const onConfirm = vi.fn()
    render(<Zone><RevokeDialog open onClose={vi.fn()} onConfirm={onConfirm} certificate={{ id: 7, related_certificate_id: 12 }} /></Zone>)
    const box = await within(dialog()).findByRole('checkbox', { name: /revocation\.revokeRelated/ })
    expect(box).toBeChecked()
    fireEvent.click(box)
    fireEvent.click(within(dialog()).getByRole('button', { name: 'revocation.confirm' }))
    expect(onConfirm).toHaveBeenCalledWith('unspecified', { revokeRelated: false })
  })
})

describe('AtelierDialog outside a zone', () => {
  it('carries the scope with it when no zone is around, and none inside one', () => {
    const { unmount } = render(<AtelierDialog title="T" onClose={vi.fn()}>body</AtelierDialog>)
    expect(dialog().parentElement).toHaveClass('atl', 'atl-island')
    unmount()
    render(<Zone><AtelierDialog title="T" onClose={vi.fn()}>body</AtelierDialog></Zone>)
    expect(dialog().parentElement).not.toHaveClass('atl-island')
    expect(dialog().closest('.atl')).not.toBeNull()
  })
})
