/** The locked account is kept for this tab only, and a broken storage never throws; the lock reaches the other tabs. */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { saveLock, readLock, clearLock, announceLock, listenForLocks, shareLock, readSharedLock, clearSharedLock, setTabAccount, adoptSharedLock } from '../sessionLock'

describe('sessionLock', () => {
  beforeEach(() => { sessionStorage.clear(); localStorage.clear() })

  it('keeps the account in this tab, not across tabs', () => {
    saveLock({ username: 'alice', name: 'Alice Martin', role: 'admin', method: 'password', password: 'never' })
    expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'admin', method: 'password', reason: 'idle' })
    expect(sessionStorage.getItem('ucm_locked_session')).not.toContain('never')
    expect(localStorage.length).toBe(0)
  })

  it('keeps nothing without a username, and forgets once cleared', () => {
    saveLock({ name: 'nobody' })
    expect(readLock()).toBeNull()
    saveLock({ username: 'alice' })
    clearLock()
    expect(readLock()).toBeNull()
  })

  it('reads a damaged value as no lock', () => {
    sessionStorage.setItem('ucm_locked_session', '{not json')
    expect(readLock()).toBeNull()
    sessionStorage.setItem('ucm_locked_session', JSON.stringify({ username: 42 }))
    expect(readLock()).toBeNull()
  })

  it('never throws when the storage refuses', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    expect(() => saveLock({ username: 'alice' })).not.toThrow()
    spy.mockRestore()
  })

  it('keeps why the session was locked: by hand, else after inactivity', () => {
    saveLock({ username: 'alice', reason: 'manual' })
    expect(readLock().reason).toBe('manual')
    saveLock({ username: 'alice', reason: 'whatever' })
    expect(readLock().reason).toBe('idle')
  })

  it('tells the other tabs of a lock, and stops listening when asked', async () => {
    const heard = []
    const stop = listenForLocks((message) => heard.push(message))
    announceLock('alice', 'manual')
    await vi.waitFor(() => expect(heard).toEqual([{ username: 'alice', reason: 'manual' }]))
    stop()
    announceLock('alice', 'idle')
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(heard).toHaveLength(1)
  })

  it('ignores a message that is not a lock', async () => {
    const heard = []
    const stop = listenForLocks((message) => heard.push(message))
    const other = new BroadcastChannel('ucm-session-lock')
    other.postMessage({ type: 'something' })
    other.postMessage({ type: 'locked' })
    other.postMessage({ type: 'locked', username: 'bob', reason: 'manual' })
    await vi.waitFor(() => expect(heard).toEqual([{ username: 'bob', reason: 'manual' }]))
    other.close()
    stop()
  })

  describe('the lock shared with the tabs that missed its message', () => {
    beforeEach(() => setTabAccount(null))

    it('keeps the account name and the reason only, across tabs', () => {
      shareLock({ username: 'alice', name: 'Alice Martin', role: 'admin', method: 'password', reason: 'manual' })
      expect(readSharedLock()).toEqual({ username: 'alice', reason: 'manual' })
      expect(sessionStorage.length).toBe(0)
      clearSharedLock()
      expect(readSharedLock()).toBeNull()
    })

    it('is taken by a tab signed in as the same account, with its own account for the lock screen', () => {
      shareLock({ username: 'alice', reason: 'manual' })
      setTabAccount({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'webauthn' })
      expect(adoptSharedLock()).toBe(true)
      expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'operator', method: 'webauthn', reason: 'manual' })
    })

    it('is left by a tab of another account, or of no account', () => {
      shareLock({ username: 'alice', reason: 'manual' })
      expect(adoptSharedLock()).toBe(false)
      setTabAccount({ username: 'bob' })
      expect(adoptSharedLock()).toBe(false)
      expect(readLock()).toBeNull()
    })

    it('reads a damaged value as no lock', () => {
      localStorage.setItem('ucm_session_lock_shared', '{not json')
      expect(readSharedLock()).toBeNull()
    })
  })
})
