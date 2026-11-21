/**
 * Effects whose cleanup cancelled the timer but not the in-flight request
 * (DUP-FE-005).
 *
 * React 18 makes a setState on an unmounted component a silent no-op, so a
 * leak is only observable where the continuation has an effect OUTSIDE the
 * component. Both cases below do: they raise a toast through the notification
 * provider, which outlives the component (it wraps the whole route tree in
 * App.jsx). The user therefore sees a toast about a screen they have left —
 * for AppShell, an expiry warning appearing on the login page after logout.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act } from '@testing-library/react'

const showError = vi.fn()
const showWarning = vi.fn()

vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showError, showSuccess: vi.fn(), showConfirm: vi.fn() }),
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showWarning, showError, showSuccess: vi.fn() }),
  useAuth: () => ({ user: { username: 'admin', role: 'admin' }, isAuthenticated: true, logout: vi.fn() }),
}))

const apiGet = vi.fn()
vi.mock('../../services/apiClient', () => ({
  apiClient: { get: (...a) => apiGet(...a), post: vi.fn() },
}))

import EmailTemplateDialog from '../../pages/settings/EmailTemplateDialog'

describe('EmailTemplateDialog — a request that outlives the dialog', () => {
  beforeEach(() => { showError.mockClear(); apiGet.mockReset() })
  afterEach(() => { vi.clearAllMocks() })

  it('does not raise an error toast once the dialog has been closed', async () => {
    let rejectLoad
    apiGet.mockReturnValue(new Promise((_, reject) => { rejectLoad = reject }))

    const { unmount } = render(<EmailTemplateDialog onClose={() => {}} />)

    // The user closes the dialog while the template is still loading.
    unmount()

    // The request then fails, as it would on a dropped connection.
    await act(async () => {
      rejectLoad(new Error('Network error. Please check your connection.'))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(showError).not.toHaveBeenCalled()
  })

  it('still reports the error while the dialog is open', async () => {
    let rejectLoad
    apiGet.mockReturnValue(new Promise((_, reject) => { rejectLoad = reject }))

    render(<EmailTemplateDialog onClose={() => {}} />)

    await act(async () => {
      rejectLoad(new Error('boom'))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(showError).toHaveBeenCalledWith('boom')
  })
})
