/**
 * A session the server holds locked answers 401 urn:ucm:problem:session-locked: the tab goes to
 * the lock screen of the account the refusal names, without a session check, and never to the
 * plain sign-in page.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiClient, resetLoginRedirect } from '../apiClient'
import { setTabAccount, readLock, clearLock, clearSharedLock } from '../../lib/sessionLock'

const json = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: new Headers({ 'content-type': 'application/problem+json' }),
  json: () => Promise.resolve(body),
})
const LOCKED = { type: 'urn:ucm:problem:session-locked', status: 401, details: { username: 'alice', reason: 'inactivity' } }

describe('apiClient: a session locked on the server', () => {
  const originalFetch = global.fetch
  const originalLocation = window.location
  let assigned

  beforeEach(() => {
    sessionStorage.clear()
    clearSharedLock()
    assigned = []
    delete window.location
    window.location = { pathname: '/certificates', search: '', hash: '', set href(v) { assigned.push(v) }, get href() { return assigned.at(-1) ?? '' } }
    global.fetch = vi.fn().mockResolvedValue(json(401, LOCKED))
  })

  afterEach(() => {
    resetLoginRedirect()
    setTabAccount(null)
    clearLock()
    global.fetch = originalFetch
    window.location = originalLocation
  })

  it('opens the lock screen of the account it names, with what the tab knew of it', async () => {
    setTabAccount({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'certificate' })
    await expect(apiClient.get('/certificates')).rejects.toMatchObject({ status: 401 })
    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(assigned).toEqual(['/login?next=%2Fcertificates'])
    expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'certificate', reason: 'idle' })
  })

  it('names the locked account even in a tab that never knew it', async () => {
    await expect(apiClient.get('/certificates')).rejects.toMatchObject({ status: 401 })
    expect(readLock()).toMatchObject({ username: 'alice', reason: 'idle' })
  })

  it('stays on the lock screen: a refusal there leads nowhere', async () => {
    window.location.pathname = '/login'
    await expect(apiClient.get('/auth/methods')).rejects.toMatchObject({ status: 401 })
    expect(assigned).toEqual([])
  })
})
