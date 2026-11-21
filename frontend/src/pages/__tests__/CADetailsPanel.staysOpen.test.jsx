/**
 * The CA slide-over stays mounted after a revocation and receives the revoked
 * CA through onChanged; only the floating detail window closes.
 */
import { describe, it, expect, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'

const svc = vi.hoisted(() => ({
  cas: {
    revoke: vi.fn(), getById: vi.fn(), export: vi.fn(), renewCsr: vi.fn(), downloadCsr: vi.fn(),
    getCrlInfo: vi.fn().mockResolvedValue({ data: {} }),
  },
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: ['*'], user: { id: 1, username: 'probe' } }),
}))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn(),
}))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))
vi.mock('../../contexts/NotificationContext', () => ({ useNotification: () => notify }))
vi.mock('../../services', () => ({
  casService: svc.cas,
  certificatesService: {},
  userCertificatesService: {},
  truststoreService: {},
  templatesService: { getForCA: vi.fn().mockResolvedValue({ data: [] }) },
}))
vi.mock('../../components/cas/ChainUsageSection', () => ({ ChainUsageSection: () => null }))
// The modal is reduced to its confirm button: what it asks is tested elsewhere
vi.mock('../../components/RevokeCertificateModal', () => ({
  RevokeCertificateModal: ({ open, onConfirm }) => open
    ? <button onClick={() => onConfirm('keyCompromise', {})}>confirm-revoke</button>
    : null,
}))
import { CADetailsPanel } from '../cas/CADetailsPanel'

const CA = {
  id: 9, refid: 'ca-sub', descr: 'Sub CA', common_name: 'Sub CA', type: 'intermediate', is_root: false,
  parent_id: 1, has_private_key: true, pending: false, revoked: false, offline: false,
}

describe('CADetailsPanel after a revocation', () => {
  it('stays open and hands the revoked CA to onChanged', async () => {
    const revoked = { ...CA, revoked: true }
    svc.cas.revoke.mockResolvedValue({ data: revoked })
    svc.cas.getById.mockResolvedValue({ data: revoked })
    const onChanged = vi.fn(); const onClose = vi.fn()
    render(
      <CADetailsPanel
        ca={CA}
        canWrite={() => true}
        canDelete={() => true}
        hasPermission={() => true}
        onChanged={onChanged}
        onClose={onClose}
        t={(key) => key}
      />
    )
    fireEvent.click(screen.getByText('cas.revoke'))
    await act(async () => { fireEvent.click(screen.getByText('confirm-revoke')) })
    expect(svc.cas.revoke).toHaveBeenCalledWith(9, { reason: 'keyCompromise' })
    expect(onClose).not.toHaveBeenCalled()
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ id: 9, revoked: true }))
  })
})
