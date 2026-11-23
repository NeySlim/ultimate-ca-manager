/**
 * POST /auth/lock may fail (network, a node restarting, 5xx, a stale CSRF token): it is sent
 * again a few times, and a session the server never locked is then signed out, so no session
 * stays open behind the lock screen.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const api = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), clearCsrfToken: vi.fn(), setCsrfToken: vi.fn() }))
vi.mock('../apiClient', () => ({ apiClient: api }))

import { authService } from '../auth.service'
import { markLockUnconfirmed, readUnconfirmedLock } from '../../lib/sessionLock'

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

  it('stops at a 401: the session is gone or locked already, nothing is left open', async () => {
    api.post.mockRejectedValueOnce(failure(401))
    const done = authService.lock('manual')
    done.catch(() => {})
    await vi.runAllTimersAsync()
    expect(posts('/auth/lock')).toBe(1)
    expect(posts('/auth/logout')).toBe(0)
    expect(readUnconfirmedLock()).toBeNull()
  })
})
