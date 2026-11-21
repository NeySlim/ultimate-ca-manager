/**
 * The entity actions judge an entry by its own resource (DUP-FE-020).
 *
 * They serve certificates, CAs, user certificates and trust store
 * entries, but derived the RBAC resource from only the first three:
 *
 *   const resource = isCA ? 'cas' : isUserCert ? 'user_certificates' : 'certificates'
 *
 * so a trust store entry fell through to 'certificates' and its Delete was
 * gated on delete:certificates. DELETE /api/v2/truststore/<id> requires
 * delete:truststore (backend/api/v2/truststore.py), and TrustStorePage gates
 * the very same call on canDelete('truststore'). The asymmetry cut both ways:
 * the actions offered a delete the route would refuse, and hid one they would
 * accept, for the same row.
 *
 * The guard now also sits at the head of the handler, so a call site that
 * wires the button up anyway still cannot reach the API.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authState = vi.hoisted(() => ({ permissions: [] }))
const truststoreMocks = vi.hoisted(() => ({
  getById: vi.fn(),
  delete: vi.fn(),
}))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
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
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

vi.mock('../../services', () => ({
  certificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  casService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  userCertificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  truststoreService: truststoreMocks,
}))

import { ActionsHarness } from '../../test/ActionsHarness'

const ENTRY = {
  id: 9,
  name: 'Corporate Root',
  subject: 'CN=Corporate Root',
  purpose: 'tls',
}

const renderWindow = async () => {
  render(<ActionsHarness type="truststore" entity={ENTRY} />)
}

describe('deleting a trust store entry from its actions', () => {
  beforeEach(() => {
    Object.values(notify).forEach(fn => fn.mockReset())
    truststoreMocks.getById.mockReset()
    truststoreMocks.delete.mockReset()
    truststoreMocks.getById.mockResolvedValue({ data: ENTRY })
    truststoreMocks.delete.mockResolvedValue({})
    notify.showConfirm.mockResolvedValue(true)
  })

  it('is not offered to a principal holding only delete:certificates', async () => {
    // The route asks for delete:truststore, so this could only ever 403.
    authState.permissions = ['read:truststore', 'delete:certificates']
    await renderWindow()
    expect(screen.queryByLabelText('common.delete')).toBeNull()
  })

  it('is offered to a principal holding delete:truststore', async () => {
    authState.permissions = ['read:truststore', 'delete:truststore']
    await renderWindow()
    expect(screen.getByLabelText('common.delete')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('common.delete'))
    await waitFor(() => expect(truststoreMocks.delete).toHaveBeenCalledWith(9))
  })

  it('revokes a user certificate through its own route, with its own id', async () => {
    // The entity id is the enrolment (AuthCertificate) id: the row comes
    // from auth_cert.to_dict() and exposes the Certificate id separately as
    // cert_id. Sending it to POST /certificates/<id>/revoke resolves it against
    // a different table, so an admin revoked an unrelated certificate.
    authState.permissions = ['read:user_certificates', 'write:user_certificates']
    const { userCertificatesService, certificatesService } = await import('../../services')
    userCertificatesService.getById.mockResolvedValue({
      data: { id: 11, name: 'alice@example.test', status: 'valid' },
    })
    userCertificatesService.revoke = vi.fn().mockResolvedValue({})
    certificatesService.revoke = vi.fn().mockResolvedValue({})

    render(<ActionsHarness type="user_certificate" entity={{ id: 11, name: 'alice@example.test', status: 'valid' }} />)
    fireEvent.click(screen.getByText('Revoke'))
    fireEvent.submit(await screen.findByText('revocation.confirm').then(el => el.closest('form')))

    await waitFor(() => expect(userCertificatesService.revoke).toHaveBeenCalledTimes(1))
    expect(userCertificatesService.revoke.mock.calls[0][0]).toBe(11)
    expect(certificatesService.revoke).not.toHaveBeenCalled()
  })

  it.each([
    [['read:certificates', 'delete:certificates'], true],
    [['read:certificates', 'delete:truststore'], false],
  ])('still judges a certificate by delete:certificates (%o)', (permissions, offered) => {
    authState.permissions = permissions
    render(<ActionsHarness entity={{ id: 4, common_name: 'web.example.com' }} />)
    expect(!!screen.queryByLabelText('common.delete') || !!screen.queryByText('common.delete')).toBe(offered)
  })
})
