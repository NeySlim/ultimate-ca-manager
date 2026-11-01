/**
 * Rename (#286) from the detail views: the floating window on desktop and
 * CertificateDetails in the mobile slide-over, both on write:certificates.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authState = vi.hoisted(() => ({ permissions: [] }))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))
const certs = vi.hoisted(() => ({ getById: vi.fn(), rename: vi.fn(), delete: vi.fn(), export: vi.fn() }))
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))

vi.mock('../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({
    closeWindow: () => {}, focusWindow: () => {}, sameWindow: true, openWindow: () => {}, windows: [],
  }),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

vi.mock('../../services', () => ({
  certificatesService: certs,
  casService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  userCertificatesService: { getById: vi.fn(), delete: vi.fn(), export: vi.fn() },
  truststoreService: { getById: vi.fn(), delete: vi.fn() },
}))

import { FloatingDetailWindow } from '../FloatingDetailWindow'
import { CertificateDetails } from '../CertificateDetails'

const CERT = { id: 4, common_name: 'web.example.com', descr: 'Front door', status: 'valid' }
const WINDOW = { id: 'w1', type: 'certificate', entityId: 4, defaultPos: { x: 0, y: 0 } }

describe('rename in the floating detail window', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    certs.getById.mockResolvedValue({ data: CERT })
  })

  it('renames with write:certificates and tells the list', async () => {
    authState.permissions = ['read:certificates', 'write:certificates']
    notify.showPrompt.mockResolvedValueOnce('Back door')
    certs.rename.mockResolvedValue({ data: { ...CERT, descr: 'Back door' } })
    const changed = vi.fn()
    window.addEventListener('ucm:data-changed', changed)
    render(<FloatingDetailWindow windowInfo={WINDOW} />)
    fireEvent.click(await screen.findByText('certificates.rename'))
    await waitFor(() => expect(certs.rename).toHaveBeenCalledWith(4, 'Back door'))
    await waitFor(() => expect(changed).toHaveBeenCalled())
    expect(changed.mock.calls[0][0].detail).toEqual({ type: 'certificate' })
    window.removeEventListener('ucm:data-changed', changed)
  })

  it('does not call the route when the name is unchanged', async () => {
    authState.permissions = ['read:certificates', 'write:certificates']
    notify.showPrompt.mockResolvedValueOnce('Front door ')
    render(<FloatingDetailWindow windowInfo={WINDOW} />)
    fireEvent.click(await screen.findByText('certificates.rename'))
    await waitFor(() => expect(notify.showPrompt).toHaveBeenCalled())
    expect(certs.rename).not.toHaveBeenCalled()
  })

  it('is absent for a read-only operator', async () => {
    authState.permissions = ['read:certificates']
    render(<FloatingDetailWindow windowInfo={WINDOW} />)
    await screen.findByText('export.title')
    expect(screen.queryByText('certificates.rename')).not.toBeInTheDocument()
  })
})

describe('rename in CertificateDetails (mobile slide-over)', () => {
  it('shows the action to a writer and calls it', () => {
    const onRename = vi.fn()
    render(<CertificateDetails certificate={CERT} onRename={onRename} canWrite />)
    fireEvent.click(screen.getByLabelText('certificates.renameCertificate'))
    expect(onRename).toHaveBeenCalledTimes(1)
  })

  it('hides it without write access', () => {
    render(<CertificateDetails certificate={CERT} onRename={vi.fn()} canWrite={false} />)
    expect(screen.queryByLabelText('certificates.renameCertificate')).not.toBeInTheDocument()
  })
})
