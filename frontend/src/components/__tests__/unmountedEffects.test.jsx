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
 *
 * Sidebar has the same unguarded shape but its continuation only calls
 * setExpiringCount, so there is nothing to assert on; it is fixed alongside
 * these two without a test of its own.
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

// Loaded at module level: its @phosphor-icons/react import takes seconds cold,
// which inside a test body counts against the 5 s timeout.
import EmailTemplateWindow from '../EmailTemplateWindow'

describe('EmailTemplateWindow — a request that outlives the window', () => {
  beforeEach(() => { showError.mockClear(); apiGet.mockReset() })
  afterEach(() => { vi.clearAllMocks() })

  it('does not raise an error toast once the window has been closed', async () => {
    let rejectLoad
    apiGet.mockReturnValue(new Promise((_, reject) => { rejectLoad = reject }))

    const { unmount } = render(<EmailTemplateWindow onClose={() => {}} />)

    // The user closes the window while the template is still loading.
    unmount()

    // The request then fails, as it would on a dropped connection.
    await act(async () => {
      rejectLoad(new Error('Network error. Please check your connection.'))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(showError).not.toHaveBeenCalled()
  })

  it('still reports the error while the window is open', async () => {
    let rejectLoad
    apiGet.mockReturnValue(new Promise((_, reject) => { rejectLoad = reject }))

    render(<EmailTemplateWindow onClose={() => {}} />)

    await act(async () => {
      rejectLoad(new Error('boom'))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(showError).toHaveBeenCalledWith('boom')
  })
})
