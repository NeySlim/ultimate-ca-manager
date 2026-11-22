/**
 * A tab that missed the message of a lock made in another tab learns it at its next request: the
 * refused call, with the session gone, leads to the lock screen of its account, not the sign-in page.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiClient, resetLoginRedirect } from '../apiClient'
import { shareLock, clearSharedLock, setTabAccount, readLock, clearLock } from '../../lib/sessionLock'

const json = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: new Headers({ 'content-type': 'application/json' }),
  json: () => Promise.resolve(body),
})

describe('apiClient: a lock made in another tab', () => {
  const originalFetch = global.fetch
  const originalLocation = window.location
  let assigned

  beforeEach(() => {
    sessionStorage.clear()
    clearSharedLock()
    assigned = []
    delete window.location
    window.location = { pathname: '/certificates', search: '', hash: '', set href(v) { assigned.push(v) }, get href() { return assigned.at(-1) ?? '' } }
    global.fetch = vi.fn()
      .mockResolvedValueOnce(json(401, { error: 'Unauthorized' }))
      .mockResolvedValueOnce(json(200, { data: { authenticated: false } }))
  })

  afterEach(() => {
    resetLoginRedirect()
    setTabAccount(null)
    clearLock()
    clearSharedLock()
    global.fetch = originalFetch
    window.location = originalLocation
  })

  it('leads to the lock screen of this tab\'s account', async () => {
    setTabAccount({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password' })
    shareLock({ username: 'alice', reason: 'manual' })
    await expect(apiClient.get('/certificates')).rejects.toMatchObject({ status: 401 })
    expect(assigned).toEqual(['/login?next=%2Fcertificates'])
    expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'password', reason: 'manual' })
  })

  it('leads to the sign-in page when the lock was of another account', async () => {
    setTabAccount({ username: 'bob' })
    shareLock({ username: 'alice', reason: 'manual' })
    await expect(apiClient.get('/certificates')).rejects.toMatchObject({ status: 401 })
    expect(assigned).toEqual(['/login?next=%2Fcertificates'])
    expect(readLock()).toBeNull()
  })
})
