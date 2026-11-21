/**
 * Rename (#286) from the detail views: the floating window on desktop and
 * the action bar of the page slide-over, both on write:certificates.
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

vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({
    closeEntity: () => {}, setEntityData: () => {}, openEntity: () => {},
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

import { InspectorObject } from '../inspector/InspectorObject'
import { ActionsHarness } from '../detail/__tests__/ActionsHarness'

const CERT = { id: 4, common_name: 'web.example.com', descr: 'Front door', status: 'valid' }
const WINDOW = { key: 'certificate:4', type: 'certificate', entityId: 4, data: null }

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
    render(<InspectorObject entry={WINDOW} onTitle={() => {}} />)
    fireEvent.click(await screen.findByText('certificates.rename'))
    await waitFor(() => expect(certs.rename).toHaveBeenCalledWith(4, 'Back door'))
    await waitFor(() => expect(changed).toHaveBeenCalled())
    expect(changed.mock.calls[0][0].detail).toEqual({ type: 'certificate' })
    window.removeEventListener('ucm:data-changed', changed)
  })

  it('does not call the route when the name is unchanged', async () => {
    authState.permissions = ['read:certificates', 'write:certificates']
    notify.showPrompt.mockResolvedValueOnce('Front door ')
    render(<InspectorObject entry={WINDOW} onTitle={() => {}} />)
    fireEvent.click(await screen.findByText('certificates.rename'))
    await waitFor(() => expect(notify.showPrompt).toHaveBeenCalled())
    expect(certs.rename).not.toHaveBeenCalled()
  })

  it('is absent for a read-only operator', async () => {
    authState.permissions = ['read:certificates']
    render(<InspectorObject entry={WINDOW} onTitle={() => {}} />)
    await screen.findByText('export.title')
    expect(screen.queryByText('certificates.rename')).not.toBeInTheDocument()
  })
})

describe('rename from the action bar of a page slide-over', () => {
  const rights = (write) => ({ canWrite: () => write, canDelete: () => false, hasPermission: () => false })

  it('shows the action to a writer and renames in place', async () => {
    notify.showPrompt.mockResolvedValueOnce('Back door')
    certs.rename.mockResolvedValue({ data: { ...CERT, descr: 'Back door' } })
    const onChanged = vi.fn()
    render(<ActionsHarness entity={CERT} permissions={rights(true)} onChanged={onChanged} />)
    fireEvent.click(screen.getByText('certificates.rename'))
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ id: 4, descr: 'Back door' })))
  })

  it('hides it without write access', () => {
    render(<ActionsHarness entity={CERT} permissions={rights(false)} />)
    expect(screen.queryByText('certificates.rename')).not.toBeInTheDocument()
  })
})
