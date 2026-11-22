/**
 * A tab opened on a session the server holds locked: the session check keeps the account the
 * server names for the lock screen and opens nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext'
import { authService } from '../../services/auth.service'
import { readLock, clearLock, clearSharedLock } from '../../lib/sessionLock'

vi.mock('../../services/auth.service', () => ({
  authService: { getCurrentUser: vi.fn(), login: vi.fn(), logout: vi.fn(), lock: vi.fn() },
}))
vi.mock('../../services/account.service', () => ({
  accountService: { getPreferences: vi.fn().mockResolvedValue({ data: {} }) },
}))

function Probe() {
  const auth = useAuth()
  return <span data-testid="state">{`${auth.sessionChecked}|${auth.isAuthenticated}`}</span>
}

describe('AuthContext on a session locked on the server', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    clearLock()
    clearSharedLock()
  })

  it('keeps the account the server names for the lock screen', async () => {
    authService.getCurrentUser.mockResolvedValue({ data: { authenticated: false, locked: {
      username: 'alice', name: 'Alice Martin', role: 'operator', method: 'mtls', reason: 'inactivity', methods: ['password'] } } })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|false'))
    expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'mtls', reason: 'idle' })
  })

  it('keeps no lock when the session is simply gone', async () => {
    authService.getCurrentUser.mockResolvedValue({ data: { authenticated: false } })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|false'))
    expect(readLock()).toBeNull()
  })
})
