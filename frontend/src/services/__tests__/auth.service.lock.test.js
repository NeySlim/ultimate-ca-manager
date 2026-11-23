/**
 * POST /auth/lock may fail (network, a node restarting, 5xx, a stale CSRF token): it is sent
 * again a few times, and a session the server never locked is then signed out, so no session
 * stays open behind the lock screen.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const api = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), clearCsrfToken: vi.fn(), setCsrfToken: vi.fn() }))
vi.mock('../apiClient', () => ({ apiClient: api }))

import { authService } from '../auth.service'
import { clearUnconfirmedLock, markLockUnconfirmed, readUnconfirmedLock } from '../../lib/sessionLock'

const failure = (status) => Object.assign(new Error('failed'), { status })
const posts = (path) => api.post.mock.calls.filter(([url]) => url === path).length

describe('authService.lock', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    Object.values(api).forEach(fn => fn.mockReset())
    api.post.mockImplementation(async (url) => (url === '/auth/logout' ? {} : Promise.reject(failure(0))))
    api.get.mockResolvedValue({ data: { authenticated: true, csrf_token: 'fresh' } })
    markLockUnconfirmed({ username: 'alice', reason: 'manual' })
  })
  afterEach(() => vi.useRealTimers())

  it('sends a failed lock again and stops once the server takes it', async () => {
    api.post.mockRejectedValueOnce(failure(0)).mockRejectedValueOnce(failure(503)).mockResolvedValueOnce({})
    const done = authService.lock('manual')
    await vi.runAllTimersAsync()
    await expect(done).resolves.toEqual({})
    expect(posts('/auth/lock')).toBe(3)
    expect(api.post).toHaveBeenCalledWith('/auth/lock', { reason: 'manual' })
    expect(posts('/auth/logout')).toBe(0)
    // The CSRF token goes once the lock is answered, not after the first failure
    expect(api.clearCsrfToken).toHaveBeenCalledTimes(1)
    expect(readUnconfirmedLock()).toBeNull()
  })

  it('signs the session out when the lock never gets through', async () => {
    const done = authService.lock('idle')
    done.catch(() => {})
    await vi.runAllTimersAsync()
    await expect(done).rejects.toMatchObject({ status: 0 })
    expect(posts('/auth/lock')).toBe(4)
    expect(posts('/auth/logout')).toBe(1)
    // The sign-out was sent with the token still set, then the token went
    expect(api.post.mock.invocationCallOrder.at(-1)).toBeLessThan(api.clearCsrfToken.mock.invocationCallOrder[0])
    await expect(authService.whenLocked()).resolves.toBeUndefined()
    // Signed out: nothing left for the next load to lock
    expect(readUnconfirmedLock()).toBeNull()
  })

  it('keeps the lock marked for the next load when the sign-out fails too', async () => {
    api.post.mockRejectedValue(failure(0))
    const done = authService.lock('manual')
    done.catch(() => {})
    await vi.runAllTimersAsync()
    await expect(done).rejects.toMatchObject({ status: 0 })
    expect(posts('/auth/logout')).toBe(1)
    expect(readUnconfirmedLock()).toEqual({ username: 'alice', reason: 'manual' })
  })

  it('takes a fresh CSRF token before sending a lock refused as forbidden again', async () => {
    api.post.mockRejectedValueOnce(failure(403)).mockResolvedValueOnce({})
    const done = authService.lock('manual')
    await vi.runAllTimersAsync()
    await expect(done).resolves.toEqual({})
    expect(api.get).toHaveBeenCalledWith('/auth/verify')
    expect(api.setCsrfToken).toHaveBeenCalledWith('fresh')
    expect(posts('/auth/lock')).toBe(2)
  })

  it('stops at a second 401: the session is gone, nothing is left open', async () => {
    api.post.mockRejectedValueOnce(failure(401)).mockRejectedValueOnce(failure(401))
    const done = authService.lock('manual')
    done.catch(() => {})
    await vi.runAllTimersAsync()
    expect(posts('/auth/lock')).toBe(2)
    expect(posts('/auth/logout')).toBe(0)
    expect(readUnconfirmedLock()).toBeNull()
  })

  it('sends a lock refused with 401 once more: a renewed identifier may have replaced the cookie', async () => {
    api.post.mockRejectedValueOnce(failure(401)).mockResolvedValueOnce({})
    const done = authService.lock('manual')
    await vi.runAllTimersAsync()
    await expect(done).resolves.toEqual({})
    expect(posts('/auth/lock')).toBe(2)
    expect(readUnconfirmedLock()).toBeNull()
  })

  it('sends again a lock the server answers it did not store (409)', async () => {
    api.post.mockRejectedValueOnce(failure(409)).mockResolvedValueOnce({})
    const done = authService.lock('manual')
    await vi.runAllTimersAsync()
    await expect(done).resolves.toEqual({})
    expect(posts('/auth/lock')).toBe(2)
    expect(posts('/auth/logout')).toBe(0)
  })

  it('sends nothing more once a sign-in happened meanwhile: the new session is left alone', async () => {
    api.post.mockImplementation(async (url) => {
      if (url === '/auth/lock') {
        // Another tab signs in while this lock waits for its next attempt (login clears the mark)
        clearUnconfirmedLock()
        return Promise.reject(failure(503))
      }
      return {}
    })
    const done = authService.lock('manual')
    done.catch(() => {})
    await vi.runAllTimersAsync()
    await expect(done).rejects.toMatchObject({ superseded: true })
    expect(posts('/auth/lock')).toBe(1)
    expect(posts('/auth/logout')).toBe(0)
    expect(api.get).not.toHaveBeenCalled()
    // The token may be the new session's: it stays
    expect(api.clearCsrfToken).not.toHaveBeenCalled()
  })

  it('sends nothing more once the mark names another account', async () => {
    api.post.mockImplementation(async (url) => {
      if (url === '/auth/lock') {
        markLockUnconfirmed({ username: 'bob', reason: 'idle' })
        return Promise.reject(failure(403))
      }
      return {}
    })
    const done = authService.lock('manual')
    done.catch(() => {})
    await vi.runAllTimersAsync()
    await expect(done).rejects.toMatchObject({ superseded: true })
    expect(posts('/auth/lock')).toBe(1)
    expect(posts('/auth/logout')).toBe(0)
    // No fresh CSRF token taken from the session opened meanwhile
    expect(api.get).not.toHaveBeenCalled()
    expect(readUnconfirmedLock()).toEqual({ username: 'bob', reason: 'idle' })
  })

  it('leaves the mark another account posted while the lock was answered', async () => {
    api.post.mockImplementation(async (url) => {
      if (url === '/auth/lock') markLockUnconfirmed({ username: 'bob', reason: 'idle' })
      return {}
    })
    const done = authService.lock('manual')
    await vi.runAllTimersAsync()
    await expect(done).resolves.toEqual({})
    expect(readUnconfirmedLock()).toEqual({ username: 'bob', reason: 'idle' })
  })

  it.each([
    ['answered', async () => ({})],
    ['refused with 401', async () => Promise.reject(failure(401))],
  ])('leaves the mark another account posted during the sign-out fallback (%s)', async (_name, signOut) => {
    api.post.mockImplementation(async (url) => {
      if (url === '/auth/logout') {
        markLockUnconfirmed({ username: 'bob', reason: 'idle' })
        return signOut()
      }
      return Promise.reject(failure(0))
    })
    const done = authService.lock('idle')
    done.catch(() => {})
    await vi.runAllTimersAsync()
    await expect(done).rejects.toMatchObject({ status: 0 })
    expect(posts('/auth/logout')).toBe(1)
    expect(readUnconfirmedLock()).toEqual({ username: 'bob', reason: 'idle' })
  })

  it('does not sign out a session opened during the last attempt', async () => {
    let sent = 0
    api.post.mockImplementation(async (url) => {
      if (url === '/auth/lock') {
        sent += 1
        if (sent === 4) clearUnconfirmedLock()
        return Promise.reject(failure(0))
      }
      return {}
    })
    const done = authService.lock('idle')
    done.catch(() => {})
    await vi.runAllTimersAsync()
    await expect(done).rejects.toBeTruthy()
    expect(posts('/auth/lock')).toBe(4)
    expect(posts('/auth/logout')).toBe(0)
    expect(api.clearCsrfToken).not.toHaveBeenCalled()
  })
})
