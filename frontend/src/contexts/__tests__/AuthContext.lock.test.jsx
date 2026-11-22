/**
 * Lock, after inactivity or by hand: the console state goes at once, before the server answers
 * (it may not), the account is kept for the lock screen with the reason, the session is closed
 * through the lock route, and the other tabs of the session lock too.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext'
import { authService } from '../../services/auth.service'
import { readLock, takeJustLocked, takeSignedOut, announceLock } from '../../lib/sessionLock'

vi.mock('../../services/auth.service', () => ({
  authService: { getCurrentUser: vi.fn(), login: vi.fn(), logout: vi.fn(), lock: vi.fn() },
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
    takeJustLocked()
    takeSignedOut()
    authService.getCurrentUser.mockResolvedValue({
      data: { authenticated: true, user: { username: 'alice', full_name: 'Alice Martin', role: 'operator' }, permissions: ['read:certificates'], auth_method: 'password' },
    })
  })

  it('clears the session at once and keeps the account for the lock screen', async () => {
    // The server never answers the lock: the console must still go
    authService.lock.mockReturnValue(new Promise(() => {}))
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))

    act(() => { auth.lock() })

    expect(screen.getByTestId('state').textContent).toBe('false||0')
    expect(authService.lock).toHaveBeenCalledWith('idle')
    expect(authService.logout).not.toHaveBeenCalled()
    expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password', reason: 'idle' })
    // The lock screen that follows knows it comes from this lock, once
    expect(takeJustLocked()).toBe(true)
    expect(takeJustLocked()).toBe(false)
  })

  it('keeps a custom role by its name for the lock screen', async () => {
    authService.getCurrentUser.mockResolvedValue({
      data: { authenticated: true, user: { username: 'c.durand', full_name: 'Claire Durand', role: 'viewer', custom_role_name: 'PKI desk' }, permissions: ['read:certificates'], auth_method: 'password' },
    })
    authService.lock.mockResolvedValue({})
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|c.durand|1'))
    act(() => { auth.lock() })
    expect(readLock().role).toBe('PKI desk')
  })

  it('keeps no lock on an ordinary sign-out', async () => {
    authService.logout.mockResolvedValue({})
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    await act(async () => { await auth.logout() })
    expect(readLock()).toBeNull()
    expect(takeJustLocked()).toBe(false)
  })

  it('tells the sign-in page of a sign-out, once, and of no lock', async () => {
    authService.logout.mockResolvedValue({})
    authService.lock.mockResolvedValue({})
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    act(() => { auth.lock() })
    expect(takeSignedOut()).toBe(false)
    await act(async () => { await auth.logout() })
    expect(takeSignedOut()).toBe(true)
    expect(takeSignedOut()).toBe(false)
  })

  it('locks by hand with its own reason, and keeps the method a reload learnt from the server', async () => {
    authService.getCurrentUser.mockResolvedValue({
      data: { authenticated: true, user: { username: 'alice', full_name: 'Alice Martin', role: 'operator' }, permissions: ['read:certificates'], auth_method: 'webauthn' },
    })
    authService.lock.mockResolvedValue({})
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    expect(auth.authMethod).toBe('webauthn')
    act(() => { auth.lock('manual') })
    expect(authService.lock).toHaveBeenCalledWith('manual')
    expect(readLock()).toMatchObject({ username: 'alice', method: 'webauthn', reason: 'manual' })
  })

  it('locks when another tab of the session locks, without asking the server again', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    act(() => { announceLock('alice', 'manual') })
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('false||0'))
    expect(authService.lock).not.toHaveBeenCalled()
    expect(authService.logout).not.toHaveBeenCalled()
    expect(readLock()).toMatchObject({ username: 'alice', reason: 'manual' })
    expect(takeJustLocked()).toBe(true)
  })

  it('tells the other tabs of its own lock', async () => {
    authService.lock.mockResolvedValue({})
    const heard = []
    const other = new BroadcastChannel('ucm-session-lock')
    other.onmessage = (event) => heard.push(event.data)
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    act(() => { auth.lock('manual') })
    await waitFor(() => expect(heard).toEqual([{ type: 'locked', username: 'alice', reason: 'manual' }]))
    other.close()
  })

  it('stays open when another account locks elsewhere', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    act(() => { announceLock('bob', 'manual') })
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(screen.getByTestId('state').textContent).toBe('true|alice|1')
    expect(readLock()).toBeNull()
  })
})
