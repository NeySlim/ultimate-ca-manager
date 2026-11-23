/**
 * A tab opened on a session the server holds locked: the session check keeps the account the
 * server names for the lock screen and opens nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext'
import { authService } from '../../services/auth.service'
import { readLock, saveLock, clearLock, shareLock, clearSharedLock, markLockUnconfirmed, readUnconfirmedLock, clearUnconfirmedLock } from '../../lib/sessionLock'

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
    clearUnconfirmedLock()
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

  describe('a lock this browser made that the server never took (its POST failed)', () => {
    const open = { data: { authenticated: true, user: { username: 'alice', role: 'operator' }, permissions: ['read:certificates'], auth_method: 'password' } }

    it('is sent again on the next load and the console stays closed', async () => {
      markLockUnconfirmed({ username: 'alice', reason: 'manual' })
      authService.getCurrentUser.mockResolvedValue(open)
      authService.lock.mockResolvedValue({})
      render(<AuthProvider><Probe /></AuthProvider>)
      await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|false'))
      expect(authService.lock).toHaveBeenCalledWith('manual')
      expect(readLock()).toMatchObject({ username: 'alice', reason: 'manual' })
    })

    it('never locks the session of another account', async () => {
      markLockUnconfirmed({ username: 'bob', reason: 'manual' })
      authService.getCurrentUser.mockResolvedValue(open)
      render(<AuthProvider><Probe /></AuthProvider>)
      await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|true'))
      expect(authService.lock).not.toHaveBeenCalled()
    })

    it('a lock the server took leaves no mark: a later sign-in of the account opens', async () => {
      // The lock screen's marks outlive a session that expired; an SSO return then opens a new one
      saveLock({ username: 'alice', reason: 'manual' })
      shareLock({ username: 'alice', reason: 'manual' })
      authService.getCurrentUser.mockResolvedValue(open)
      render(<AuthProvider><Probe /></AuthProvider>)
      await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|true'))
      expect(authService.lock).not.toHaveBeenCalled()
    })

    it('the lock made here stays marked until the server answers it', async () => {
      authService.getCurrentUser.mockResolvedValue(open)
      authService.lock.mockReturnValue(new Promise(() => {}))
      let auth
      function Lock() { auth = useAuth(); return null }
      render(<AuthProvider><Probe /><Lock /></AuthProvider>)
      await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|true'))
      act(() => { auth.lock('manual') })
      expect(readUnconfirmedLock()).toEqual({ username: 'alice', reason: 'manual' })
    })
  })
})
