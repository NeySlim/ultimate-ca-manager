/**
 * The detail window of a hybrid pair member (RFC 9763): the linked certificate
 * opens in a window, the export offers the bundle, and the revocation answer
 * about the linked certificate reaches the service.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  openWindow: vi.fn(),
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
vi.mock('../../contexts', () => ({
  useNotification: () => mocks.notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))
vi.mock('../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({
    closeWindow: vi.fn(), focusWindow: vi.fn(), sameWindow: true, openWindow: mocks.openWindow, windows: [],
  }),
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: ['read:certificates', 'write:certificates', 'delete:certificates'] }),
}))
vi.mock('../../services', () => ({
  certificatesService: mocks.certificatesService,
  casService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  userCertificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  truststoreService: { getById: vi.fn(), delete: vi.fn() },
}))
vi.mock('../deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))

import { FloatingDetailWindow } from '../FloatingDetailWindow'

const WINDOW = { id: 'w1', type: 'certificate', entityId: 4, defaultPos: { x: 0, y: 0 } }
const MEMBER = {
  id: 4, common_name: 'pair.example.com', status: 'valid', key_algorithm: 'EC-P256',
  related_certificate_id: 5, hybrid_role: 'classical',
}

const PARTNER = { id: 5, common_name: 'pair.example.com', related_certificate_id: 4, revoked: false, hybrid_role: 'pq' }

const open = async () => {
  render(<FloatingDetailWindow windowInfo={WINDOW} />)
  await screen.findAllByText('pair.example.com')
}

describe('FloatingDetailWindow of a hybrid pair member', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.certificatesService.getById.mockImplementation((id) => Promise.resolve({ data: id === 5 ? PARTNER : MEMBER }))
    mocks.certificatesService.revoke.mockResolvedValue({ data: { id: 4, revoked: true } })
  })

  it('opens the linked certificate in a window', async () => {
    await open()
    fireEvent.click(screen.getByRole('link', { name: 'certificates.hybrid.openRelated' }))
    expect(mocks.openWindow).toHaveBeenCalledWith('certificate', 5)
  })

  it('offers the hybrid bundle', async () => {
    await open()
    fireEvent.click(screen.getByText('Export'))
    expect(screen.getByText('export.formats.hybridBundle')).toBeInTheDocument()
  })

  it('keeps the linked certificate valid when unchecked', async () => {
    await open()
    fireEvent.click(screen.getByText('Revoke'))
    fireEvent.click(await screen.findByLabelText('revocation.revokeRelated'))
    fireEvent.submit(screen.getByTestId('revoke-form'))
    await waitFor(() => expect(mocks.certificatesService.revoke)
      .toHaveBeenCalledWith(4, 'unspecified', { revokeRelated: false }))
  })

  it('names the linked certificate the server revoked too', async () => {
    mocks.certificatesService.revoke.mockResolvedValue({ data: { id: 4, revoked: true, related_revoked: 5 } })
    await open()
    fireEvent.click(screen.getByText('Revoke'))
    expect(await screen.findByLabelText('revocation.revokeRelated')).toBeChecked()
    fireEvent.submit(screen.getByTestId('revoke-form'))
    await waitFor(() => expect(mocks.notify.showSuccess).toHaveBeenCalledWith('revocation.revokedWithRelated'))
    expect(mocks.notify.showWarning).not.toHaveBeenCalled()
  })

  it.each([
    [{ id: 4, related_renewed: [5] }, 'certificates.hybrid.renewedWithRelated'],
    [{ id: 4 }, 'Certificate renewed'],
  ])('names the linked certificate renewed with it (%o)', async (answer, toast) => {
    mocks.certificatesService.getById.mockImplementation((id) =>
      Promise.resolve({ data: id === 5 ? PARTNER : { ...MEMBER, has_private_key: true } }))
    mocks.certificatesService.renew.mockResolvedValue({ data: answer })
    mocks.notify.showPrompt.mockResolvedValue('')
    await open()
    fireEvent.click(screen.getByText('Renew'))
    await waitFor(() => expect(mocks.notify.showSuccess).toHaveBeenCalledWith(toast))
  })

  it('warns when the linked certificate was not revoked', async () => {
    await open()
    fireEvent.click(screen.getByText('Revoke'))
    await screen.findByLabelText('revocation.revokeRelated')
    fireEvent.submit(screen.getByTestId('revoke-form'))
    await waitFor(() => expect(mocks.notify.showWarning).toHaveBeenCalledWith('revocation.relatedNotRevoked'))
  })

  it('shows why the server refused the bundle', async () => {
    const reason = 'Certificate 5 has no private key; export the bundle without keys'
    mocks.certificatesService.export.mockRejectedValue(Object.assign(new Error(reason), { status: 400 }))
    await open()
    fireEvent.click(screen.getByText('Export'))
    fireEvent.click(screen.getByText('export.formats.hybridBundle').closest('button'))
    fireEvent.submit(screen.getByText('PEM').closest('form'))
    await waitFor(() => expect(mocks.notify.showError).toHaveBeenCalledWith(reason))
  })
})
