/** The toasts and confirmations of useEntityActions resolve to keys every locale defines. */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import fr from '../../i18n/locales/fr.json'

// A missing key surfaces as the key itself, never as the English fallback
const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), fr)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => (typeof lookup(key) === 'string' ? lookup(key) : key) }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))
const svc = vi.hoisted(() => ({
  certs: { delete: vi.fn(), revoke: vi.fn(), renew: vi.fn(), export: vi.fn() },
  cas: { delete: vi.fn(), revoke: vi.fn(), export: vi.fn() },
  users: { delete: vi.fn(), revoke: vi.fn(), export: vi.fn() },
  trust: { delete: vi.fn(), export: vi.fn() },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: ['*'] }) }))
vi.mock('../../components/CertificateLintModal', () => ({ CertificateLintModal: () => null }))
vi.mock('../../components/RevokeCertificateModal', () => ({
  RevokeCertificateModal: ({ open, onConfirm }) => (open
    ? <button type="button" onClick={() => onConfirm('keyCompromise', {})}>confirm-revoke</button>
    : null),
}))
vi.mock('../../services', async (orig) => ({
  ...(await orig()),
  certificatesService: svc.certs,
  casService: svc.cas,
  userCertificatesService: svc.users,
  truststoreService: svc.trust,
}))

import { ActionsHarness } from '../../components/detail/__tests__/ActionsHarness'

const ALLOW = { canWrite: () => true, canDelete: () => true, hasPermission: () => true }
const CERT = {
  id: 4, common_name: 'web.example.com', subject: 'CN=web.example.com', serial_number: '42',
  status: 'valid', revoked: false, has_private_key: true,
  valid_from: '2025-01-01T00:00:00Z', valid_to: '2030-01-01T00:00:00Z',
}
const EXPIRED = { ...CERT, status: 'expired' }

const revoke = async (type = 'certificate') => {
  render(<ActionsHarness type={type} entity={CERT} permissions={ALLOW} />)
  fireEvent.click(screen.getByText(fr.common.revoke))
  fireEvent.click(await screen.findByText('confirm-revoke'))
}

beforeEach(() => {
  vi.clearAllMocks()
  notify.showConfirm.mockResolvedValue(true)
  notify.showPrompt.mockResolvedValue('')
})

describe('translated messages of the entity actions', () => {
  it('reports a revoked certificate in the locale', async () => {
    svc.certs.revoke.mockResolvedValue({ data: { id: 4, revoked: true } })
    await revoke()
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith(fr.messages.success.other.revoked))
  })

  it('reports a revoked user certificate in the locale', async () => {
    svc.users.revoke.mockResolvedValue({ data: { id: 4 } })
    await revoke('user_certificate')
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith(fr.messages.success.other.revoked))
  })

  it('reports a failed revocation in the locale', async () => {
    svc.certs.revoke.mockRejectedValue(new Error(''))
    await revoke()
    await waitFor(() => expect(notify.showError).toHaveBeenCalledWith(fr.messages.errors.revokeFailed.certificate))
  })

  it('reports a renewed certificate in the locale', async () => {
    svc.certs.renew.mockResolvedValue({ data: { id: 5 } })
    render(<ActionsHarness entity={CERT} permissions={ALLOW} />)
    fireEvent.click(screen.getByText(fr.common.renew))
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalled())
    expect(fr.certificates.renewed).toEqual(expect.any(String))
    expect(notify.showSuccess).toHaveBeenCalledWith(fr.certificates.renewed)
  })

  it('reports a failed renewal in the locale', async () => {
    svc.certs.renew.mockRejectedValue(new Error(''))
    render(<ActionsHarness entity={CERT} permissions={ALLOW} />)
    fireEvent.click(screen.getByText(fr.common.renew))
    await waitFor(() => expect(notify.showError).toHaveBeenCalledWith(fr.common.operationFailed))
  })

  it.each([
    ['certificate', EXPIRED, fr.messages.confirm.delete.certificate],
    ['ca', { id: 9, common_name: 'Sub CA', type: 'intermediate', has_private_key: true }, fr.messages.confirm.delete.ca],
    ['truststore', { id: 1, name: 'root' }, fr.messages.confirm.delete.truststore],
  ])('asks before deleting a %s in the locale', async (type, entity, question) => {
    notify.showConfirm.mockResolvedValue(false)
    render(<ActionsHarness type={type} entity={entity} permissions={ALLOW} />)
    fireEvent.click(screen.getByRole('button', { name: fr.common.delete }))
    await waitFor(() => expect(notify.showConfirm).toHaveBeenCalled())
    expect(notify.showConfirm.mock.calls[0][0]).toBe(question)
  })
})
