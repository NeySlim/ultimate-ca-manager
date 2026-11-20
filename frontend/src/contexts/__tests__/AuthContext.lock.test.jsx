/**
 * Inactivity lock: the console state goes at once, before the server answers
 * (it may not), the account is kept for the lock screen, and the session is closed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext'
import { authService } from '../../services/auth.service'
import { readLock } from '../../lib/sessionLock'

vi.mock('../../services/auth.service', () => ({
  authService: { getCurrentUser: vi.fn(), login: vi.fn(), logout: vi.fn() },
}))
vi.mock('../../services/account.service', () => ({
  accountService: { getPreferences: vi.fn().mockResolvedValue({ data: {} }) },
}))

let auth
function Probe() {
  auth = useAuth()
  return <span data-testid="state">{`${auth.isAuthenticated}|${auth.user?.username || ''}|${auth.permissions.length}`}</span>
}

describe('AuthContext lock', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    authService.getCurrentUser.mockResolvedValue({
      data: { authenticated: true, user: { username: 'alice', full_name: 'Alice Martin', role: 'operator' }, permissions: ['read:certificates'], auth_method: 'password' },
    })
  })

  it('clears the session at once and keeps the account for the lock screen', async () => {
    // The server never answers the logout: the console must still go
    authService.logout.mockReturnValue(new Promise(() => {}))
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))

    act(() => { auth.lock() })

    expect(screen.getByTestId('state').textContent).toBe('false||0')
    expect(authService.logout).toHaveBeenCalledTimes(1)
    expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password' })
  })

  it('keeps no lock on an ordinary sign-out', async () => {
    authService.logout.mockResolvedValue({})
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    await act(async () => { await auth.logout() })
    expect(readLock()).toBeNull()
  })
})
