/** The locked account is kept for this tab only, and a broken storage never throws. */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { saveLock, readLock, clearLock } from '../sessionLock'

describe('sessionLock', () => {
  beforeEach(() => { sessionStorage.clear(); localStorage.clear() })

  it('keeps the account in this tab, not across tabs', () => {
    saveLock({ username: 'alice', name: 'Alice Martin', role: 'admin', method: 'password', password: 'never' })
    expect(readLock()).toEqual({ username: 'alice', name: 'Alice Martin', role: 'admin', method: 'password' })
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
})
