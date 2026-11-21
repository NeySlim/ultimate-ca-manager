/**
 * A revocation a policy queues for approval revokes nothing, so the
 * "revoke then delete" of the Certificates zone dock must not delete either.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
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

vi.mock('../../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
  useInspector: () => ({ closeEntity: vi.fn(), setEntityData: vi.fn(), openEntity: vi.fn() }),
}))

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

vi.mock('../../../services', () => ({
  certificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  casService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  userCertificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  truststoreService: truststoreMocks,
}))

import { renderCertificateBody } from '../../../test/certificateBody'
import { chooseMoreAction } from '../../../test/moreActions'

async function revokeThenDelete(revokeResult) {
  authState.permissions = ['read:certificates', 'write:certificates', 'delete:certificates']
  const { certificatesService } = await import('../../../services')
  certificatesService.getById.mockResolvedValue({ data: { id: 4, common_name: 'web.example.com', status: 'valid' } })
  certificatesService.revoke = vi.fn().mockResolvedValue(revokeResult)
  certificatesService.delete.mockResolvedValue({})
  notify.showConfirm.mockResolvedValue(true)
  renderCertificateBody(4)
  await screen.findAllByText('web.example.com')
  await chooseMoreAction('common.delete')
  fireEvent.click(within(await screen.findByTestId('revoke-dialog')).getByRole('button', { name: 'revocation.confirm' }))
  await waitFor(() => expect(certificatesService.revoke).toHaveBeenCalledTimes(1))
  return certificatesService
}

describe('revoke then delete, under a revocation policy', () => {
  beforeEach(() => vi.clearAllMocks())

  it('deletes nothing while the revocation waits for approval', async () => {
    const service = await revokeThenDelete({ data: { approval_required: true, policy_name: 'Two keys' } })
    await waitFor(() => expect(notify.showWarning).toHaveBeenCalledWith('certificates.revocationApprovalRequired'))
    expect(service.delete).not.toHaveBeenCalled()
  })

  it('deletes once the revocation is done', async () => {
    const service = await revokeThenDelete({ data: { id: 4, revoked: true } })
    await waitFor(() => expect(service.delete).toHaveBeenCalledWith(4))
  })
})
