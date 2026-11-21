/**
 * A revocation from the Certificates zone dock that the issuing CA did not confirm
 * (ACME upstream, Microsoft CA): the server's warning is shown, not a plain success.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() },
  certificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn(), revoke: vi.fn(), renew: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => mocks.notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
  useInspector: () => ({ closeEntity: vi.fn(), setEntityData: vi.fn(), openEntity: vi.fn() }),
}))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: ['read:certificates', 'write:certificates', 'delete:certificates'] }),
}))
vi.mock('../../../services', () => ({
  certificatesService: mocks.certificatesService,
  casService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  userCertificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  truststoreService: { getById: vi.fn(), delete: vi.fn() },
}))
vi.mock('../../../components/deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))

import { renderCertificateBody } from '../../../test/certificateBody'
import { chooseMoreAction } from '../../../test/moreActions'

const CERT = { id: 11, common_name: 'web.example.com', status: 'valid', source: 'acme_client', key_algorithm: 'EC-P256' }

const revokeFromInspector = async () => {
  renderCertificateBody(11)
  await screen.findAllByText('web.example.com')
  await chooseMoreAction('inspector.cert.revokeAction')
  fireEvent.click(within(await screen.findByTestId('revoke-dialog')).getByRole('button', { name: 'revocation.confirm' }))
  await waitFor(() => expect(mocks.certificatesService.revoke).toHaveBeenCalled())
}

describe('the certificate inspector and a revocation the issuing CA did not confirm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.certificatesService.getById.mockResolvedValue({ data: CERT })
  })

  it.each([
    ['acme_local_only', { acme_local_only: true, acme_upstream_pending: true }],
    ['msca_local_only', { msca_local_only: true }],
  ])('shows the server warning for %s', async (_flag, meta) => {
    const message = 'Certificate revoked in UCM, but the CA did not confirm the revocation'
    mocks.certificatesService.revoke.mockResolvedValue({ data: { id: 11, revoked: true }, message, meta })
    await revokeFromInspector()
    await waitFor(() => expect(mocks.notify.showWarning).toHaveBeenCalledWith(message))
    expect(mocks.notify.showSuccess).not.toHaveBeenCalledWith('messages.success.other.revoked')
  })

  it('falls back to its own warning when the server gives no message', async () => {
    mocks.certificatesService.revoke.mockResolvedValue({ data: { id: 11, revoked: true }, meta: { acme_local_only: true } })
    await revokeFromInspector()
    await waitFor(() => expect(mocks.notify.showWarning).toHaveBeenCalledWith('revocation.revokedLocallyOnly'))
  })

  it('says plain success when the CA confirmed', async () => {
    mocks.certificatesService.revoke.mockResolvedValue({ data: { id: 11, revoked: true }, meta: { acme_ca_revoked: true } })
    await revokeFromInspector()
    await waitFor(() => expect(mocks.notify.showSuccess).toHaveBeenCalledWith('messages.success.other.revoked'))
    expect(mocks.notify.showWarning).not.toHaveBeenCalled()
  })
})
