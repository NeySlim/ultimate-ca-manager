/**
 * The CA panel shows an RSA CA's signature scheme and switches it after a
 * confirmation; an EC CA has no scheme to show.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ update: vi.fn(), showConfirm: vi.fn(), onChanged: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: ['*'], user: { id: 1, username: 'probe' } }),
}))

vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: mocks.showConfirm,
  }),
}))

vi.mock('../../services', () => ({
  casService: { getCrlInfo: vi.fn().mockResolvedValue({ data: {} }), update: mocks.update },
  templatesService: { getForCA: vi.fn().mockResolvedValue({ data: [] }) },
}))

vi.mock('../../components/cas/CACrlSection', () => ({ CACrlSection: () => null }))
vi.mock('../../components/cas/ChainUsageSection', () => ({ ChainUsageSection: () => null }))

import { CADetailsPanel } from '../cas/CADetailsPanel'

const RSA_CA = {
  id: 7, refid: 'ca-rsa', descr: 'RSA CA', type: 'root', is_root: true, key_type: 'RSA 3072',
  has_private_key: true, pending: false, revoked: false, signature_scheme: 'pkcs1v15',
}

function renderPanel(ca, canWrite = () => true) {
  render(
    <CADetailsPanel ca={ca} canWrite={canWrite} canDelete={() => false} hasPermission={() => false}
      onExport={vi.fn()} onDelete={vi.fn()} onChanged={mocks.onChanged} t={(key) => key} />
  )
}

describe('CADetailsPanel signature scheme', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the key family and size from key_type', () => {
    renderPanel({ ...RSA_CA, key_type: 'EC secp384r1' })
    expect(screen.getByText('EC')).toBeInTheDocument()
    expect(screen.getByText('secp384r1')).toBeInTheDocument()
    expect(screen.queryByText('cas.signatureScheme')).not.toBeInTheDocument()
    expect(screen.queryByText('cas.signatureSchemeUsePss')).not.toBeInTheDocument()
  })

  it('switches an RSA CA to PSS after confirmation', async () => {
    mocks.showConfirm.mockResolvedValue(true)
    mocks.update.mockResolvedValue({ data: { ...RSA_CA, signature_scheme: 'pss' } })
    renderPanel(RSA_CA)
    expect(screen.getByText('cas.signatureSchemePkcs1v15')).toBeInTheDocument()
    fireEvent.click(screen.getByText('cas.signatureSchemeUsePss'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(7, { signatureScheme: 'pss' }))
    expect(mocks.showConfirm.mock.calls[0][0]).toBe('cas.signatureSchemeToPssConfirm')
    expect(mocks.onChanged).toHaveBeenCalledWith(expect.objectContaining({ signature_scheme: 'pss' }))
  })

  it('changes nothing when the confirmation is declined', async () => {
    mocks.showConfirm.mockResolvedValue(false)
    renderPanel({ ...RSA_CA, signature_scheme: 'pss' })
    fireEvent.click(screen.getByText('cas.signatureSchemeUseV15'))
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalled())
    expect(mocks.update).not.toHaveBeenCalled()
  })

  it('offers no PSS on an Azure HSM key or without a key', () => {
    renderPanel({ ...RSA_CA, uses_hsm: true, hsm_provider_type: 'azure-keyvault' })
    expect(screen.queryByText('cas.signatureSchemeUsePss')).not.toBeInTheDocument()
    cleanup()
    renderPanel({ ...RSA_CA, has_private_key: false })
    expect(screen.queryByText('cas.signatureSchemeUsePss')).not.toBeInTheDocument()
    cleanup()
    renderPanel({ ...RSA_CA, uses_hsm: true, hsm_provider_type: 'openbao' })
    expect(screen.getByText('cas.signatureSchemeUsePss')).toBeInTheDocument()
  })

  it('offers no switch without write:cas', () => {
    renderPanel(RSA_CA, () => false)
    expect(screen.queryByText('cas.signatureSchemeUsePss')).not.toBeInTheDocument()
  })
})
