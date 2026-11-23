/**
 * Lock, after inactivity or by hand: the console state goes at once, before the server answers
 * (it may not), the account is kept for the lock screen with the reason, the session is closed
 * through the lock route, and the other tabs of the session lock too.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext'
import { authService } from '../../services/auth.service'
import { readLock, takeJustLocked, takeSignedOut, announceLock, shareLock, readSharedLock, clearSharedLock } from '../../lib/sessionLock'

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
    clearSharedLock()
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

  const ALICE = { data: { authenticated: true, user: { username: 'alice', full_name: 'Alice Martin', role: 'operator' }, permissions: ['read:certificates'], auth_method: 'password' } }
  const delivered = () => new Promise((resolve) => setTimeout(resolve, 30))

  it('locks when the message arrives while the tab still checks its session', async () => {
    let answer
    authService.getCurrentUser.mockReturnValue(new Promise((resolve) => { answer = resolve }))
    render(<AuthProvider><Probe /></AuthProvider>)
    act(() => { announceLock('alice', 'manual') })
    await delivered()
    // The server answered the check before the lock reached it
    await act(async () => { answer(ALICE) })
    await waitFor(() => expect(auth.sessionChecked).toBe(true))
    expect(screen.getByTestId('state').textContent).toBe('false||0')
    expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password', reason: 'manual' })
    expect(takeJustLocked()).toBe(true)
    expect(authService.lock).not.toHaveBeenCalled()
  })

  describe('a lock asked while the tab still checks its session', () => {
    let answer
    beforeEach(() => {
      authService.lock.mockResolvedValue({})
      authService.getCurrentUser.mockReturnValue(new Promise((resolve) => { answer = resolve }))
    })

    it('is held, then applied to the account the check finds, with the request sent after it', async () => {
      const heard = []
      const other = new BroadcastChannel('ucm-session-lock')
      other.onmessage = (event) => heard.push(event.data)
      render(<AuthProvider><Probe /></AuthProvider>)
      act(() => { auth.lock('manual') })
      // Nothing to send yet: no account, no CSRF token before the check answers
      expect(authService.lock).not.toHaveBeenCalled()
      await act(async () => { answer(ALICE) })
      await waitFor(() => expect(auth.sessionChecked).toBe(true))
      // Never open in between: the lock screen of the account found
      expect(screen.getByTestId('state').textContent).toBe('false||0')
      expect(authService.lock).toHaveBeenCalledTimes(1)
      expect(authService.lock).toHaveBeenCalledWith('manual')
      expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password', reason: 'manual' })
      expect(readSharedLock()).toEqual({ username: 'alice', reason: 'manual' })
      expect(takeJustLocked()).toBe(true)
      await waitFor(() => expect(heard).toEqual([{ type: 'locked', username: 'alice', reason: 'manual' }]))
      other.close()
    })

    it('keeps the reason of an inactivity lock', async () => {
      render(<AuthProvider><Probe /></AuthProvider>)
      act(() => { auth.lock() })
      await act(async () => { answer(ALICE) })
      await waitFor(() => expect(auth.sessionChecked).toBe(true))
      expect(authService.lock).toHaveBeenCalledWith('idle')
      expect(readLock()).toMatchObject({ username: 'alice', reason: 'idle' })
    })

    it('is dropped when the check finds no session', async () => {
      render(<AuthProvider><Probe /></AuthProvider>)
      act(() => { auth.lock('manual') })
      await act(async () => { answer({ data: { authenticated: false } }) })
      await waitFor(() => expect(auth.sessionChecked).toBe(true))
      expect(authService.lock).not.toHaveBeenCalled()
      expect(readLock()).toBeNull()
      expect(readSharedLock()).toBeNull()
    })

    it('leaves the lock the server already holds as it is', async () => {
      render(<AuthProvider><Probe /></AuthProvider>)
      act(() => { auth.lock('manual') })
      await act(async () => {
        answer({ data: { authenticated: false, locked: { username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password', reason: 'idle' } } })
      })
      await waitFor(() => expect(auth.sessionChecked).toBe(true))
      expect(authService.lock).not.toHaveBeenCalled()
      expect(readLock()).toMatchObject({ username: 'alice', reason: 'idle' })
    })

    it('stays locked when a later check answers before the lock reached the server', async () => {
      authService.getCurrentUser.mockResolvedValueOnce(ALICE)
      render(<AuthProvider><Probe /></AuthProvider>)
      await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
      authService.getCurrentUser.mockReturnValue(new Promise((resolve) => { answer = resolve }))
      let check
      act(() => { check = auth.checkSession() })
      act(() => { auth.lock('manual') })
      expect(authService.lock).toHaveBeenCalledTimes(1)
      await act(async () => { answer(ALICE); await check })
      expect(screen.getByTestId('state').textContent).toBe('false||0')
      expect(authService.lock).toHaveBeenCalledTimes(1)
      expect(readLock()).toMatchObject({ username: 'alice', reason: 'manual' })
    })
  })

  it('opens when the message heard during the check was of another account', async () => {
    let answer
    authService.getCurrentUser.mockReturnValue(new Promise((resolve) => { answer = resolve }))
    render(<AuthProvider><Probe /></AuthProvider>)
    act(() => { announceLock('bob', 'manual') })
    await delivered()
    await act(async () => { answer(ALICE) })
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    expect(readLock()).toBeNull()
  })

  it('shares its lock with the tabs that miss the message; a sign-in or a sign-out removes it', async () => {
    authService.lock.mockResolvedValue({})
    authService.logout.mockResolvedValue({})
    authService.login.mockResolvedValue(ALICE)
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    act(() => { auth.lock('manual') })
    expect(readSharedLock()).toEqual({ username: 'alice', reason: 'manual' })
    // This tab hears its own message too, while signed out: let it pass first
    await delivered()
    await act(async () => { await auth.login('alice', 'secret') })
    expect(readSharedLock()).toBeNull()
    act(() => { auth.lock('idle') })
    expect(readSharedLock()).toEqual({ username: 'alice', reason: 'idle' })
    await act(async () => { await auth.logout() })
    expect(readSharedLock()).toBeNull()
  })

  it('shows the lock screen when a check finds the session gone and this account was locked elsewhere', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    shareLock({ username: 'alice', reason: 'manual' })
    authService.getCurrentUser.mockResolvedValue({ data: { authenticated: false } })
    await act(async () => { await auth.checkSession() })
    expect(screen.getByTestId('state').textContent).toBe('false||0')
    expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password', reason: 'manual' })
  })

  it('shows the sign-in page when the session is gone and the lock elsewhere was of another account', async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
    shareLock({ username: 'bob', reason: 'manual' })
    authService.getCurrentUser.mockResolvedValue({ data: { authenticated: false } })
    await act(async () => { await auth.checkSession() })
    expect(screen.getByTestId('state').textContent).toBe('false||0')
    expect(readLock()).toBeNull()
  })

  describe('back to the foreground', () => {
    const show = () => act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
      await delivered()
    })
    beforeEach(() => { vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible') })

    it('locks when this account was locked elsewhere and the server confirms the session is gone', async () => {
      render(<AuthProvider><Probe /></AuthProvider>)
      await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
      shareLock({ username: 'alice', reason: 'manual' })
      authService.getCurrentUser.mockResolvedValue({ data: { authenticated: false } })
      await show()
      expect(screen.getByTestId('state').textContent).toBe('false||0')
      expect(readLock()).toMatchObject({ username: 'alice', reason: 'manual' })
      expect(takeJustLocked()).toBe(true)
    })

    it('stays open when the server still holds the session', async () => {
      render(<AuthProvider><Probe /></AuthProvider>)
      await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
      shareLock({ username: 'alice', reason: 'manual' })
      await show()
      expect(authService.getCurrentUser).toHaveBeenCalledTimes(2)
      expect(screen.getByTestId('state').textContent).toBe('true|alice|1')
      expect(readLock()).toBeNull()
    })

    it('asks the server nothing when no lock was made elsewhere', async () => {
      render(<AuthProvider><Probe /></AuthProvider>)
      await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('true|alice|1'))
      await show()
      expect(authService.getCurrentUser).toHaveBeenCalledTimes(1)
      expect(screen.getByTestId('state').textContent).toBe('true|alice|1')
    })
  })
})
