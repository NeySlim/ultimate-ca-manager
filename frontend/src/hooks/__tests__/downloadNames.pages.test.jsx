/** Pages hand downloadBlob a raw label; the file lands under a safe name (#448). */
import { renderHook, render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const svc = vi.hoisted(() => ({
  cas: { downloadCsr: vi.fn(), takeOffline: vi.fn() },
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() }),
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: ['*'] }) }))
vi.mock('../../services', () => ({
  certificatesService: {}, casService: svc.cas,
  userCertificatesService: {}, truststoreService: {},
}))

import { useEntityActions } from '../useEntityActions'
import { TakeOfflineModal } from '../../components/cas/TakeOfflineModal'

const LABEL = 'テスト/用:CA'
let saved
beforeEach(() => {
  saved = []
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { saved.push(this.download) })
})
afterEach(() => vi.restoreAllMocks())

describe('raw labels saved through downloadBlob', () => {
  it('CA CSR download keeps the Japanese label, drops the separators', async () => {
    svc.cas.downloadCsr.mockResolvedValue(new Blob(['csr']))
    const rights = { canWrite: () => true, canDelete: () => true, hasPermission: () => true }
    const { result } = renderHook(() => useEntityActions({
      type: 'ca', entity: { id: 9, common_name: LABEL, has_csr: true, type: 'root' }, permissions: rights, onClose: vi.fn(),
    }))
    await act(async () => { await result.current.actions.find(a => a.id === 'downloadCsr').onClick() })
    expect(saved).toEqual(['テスト_用_CA.csr'])
  })

  it('offline CA key file keeps the Japanese label too', async () => {
    svc.cas.takeOffline.mockResolvedValue(new Blob(['key']))
    render(<TakeOfflineModal open onClose={() => {}} ca={{ id: 3, descr: LABEL, has_private_key: true }} />)
    fireEvent.click(screen.getByText('common.continue'))
    fireEvent.click(screen.getByText('cas.offlineFileExported'))
    const inputs = document.querySelectorAll('input[type="password"]')
    inputs.forEach(i => fireEvent.change(i, { target: { value: 'Sup3r-secret-pass' } }))
    const confirm = document.querySelector('input[type="text"]')
    if (confirm) fireEvent.change(confirm, { target: { value: 'OFFLINE' } })
    fireEvent.submit(document.querySelector('form'))
    await waitFor(() => expect(saved).toEqual(['テスト_用_CA-offline.key']))
  })
})
