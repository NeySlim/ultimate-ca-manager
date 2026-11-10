/** Renewing an AD CS certificate that awaits CA approval says so, not "renewed". */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import en from '../../../i18n/locales/en.json'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => lookup(key) ?? (typeof opts === 'string' ? opts : key) }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(async () => true), showPrompt: vi.fn(),
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))
vi.mock('../../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: ['*'] }) }))
vi.mock('../../CertificateLintModal', () => ({ CertificateLintModal: () => null }))
const renew = vi.hoisted(() => vi.fn())
vi.mock('../../../services', async (orig) => ({
  ...(await orig()),
  certificatesService: { ...((await orig()).certificatesService), renew },
}))

import { ActionsHarness } from './ActionsHarness'

const ALLOW = { canWrite: () => true, canDelete: () => true, hasPermission: () => true }
const cert = {
  id: 4, common_name: 'ad.example.com', subject: 'CN=ad.example.com', serial_number: '42',
  valid_to: '2030-01-01T00:00:00Z', source: 'msca', revoked: false,
}

describe('renew of an AD CS certificate', () => {
  it('reports a pending approval', async () => {
    renew.mockResolvedValue({ data: { id: 4 }, meta: { msca_status: 'pending' } })
    render(<ActionsHarness entity={cert} permissions={ALLOW} />)
    fireEvent.click(screen.getByText(en.common.renew))
    await waitFor(() => expect(renew).toHaveBeenCalled())
    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith(en.certificates.renewPendingMsca))
    expect(notify.showSuccess).not.toHaveBeenCalledWith(en.certificates.renewed)
  })
})
