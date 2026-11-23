/**
 * The inactivity lock counts the user's gestures only. The console's own polls (status bar,
 * badges, health) keep the server session fresh, so the server is not asked whether the
 * session still lives: at the end of the idle time the tab locks. A gesture in another tab
 * of the same session counts too.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act, fireEvent } from '@testing-library/react'

const auth = vi.hoisted(() => ({ checkSession: vi.fn(), lock: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { username: 'admin' }, ...auth }),
  useNotification: () => ({ showSuccess: vi.fn() }),
}))
vi.mock('../../services', () => ({
  authService: { getCurrentUser: vi.fn(async () => ({ data: { session_timeout: 600 } })) },
}))

import { SessionWarning } from '../SessionWarning'
import { noteGesture } from '../../lib/userActivity'

const tick = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const MINUTE = 60 * 1000

describe('SessionWarning: the idle time is the time without a gesture', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    auth.checkSession.mockReset()
    auth.lock.mockReset()
    // The polls keep the server session open: it always says so
    auth.checkSession.mockResolvedValue(true)
  })
  afterEach(() => vi.useRealTimers())

  it('locks at the end of the idle time though the server still says the session is open', async () => {
    render(<SessionWarning />)
    await tick(9 * MINUTE)
    expect(auth.lock).not.toHaveBeenCalled()
    await tick(MINUTE + 2000)
    expect(auth.lock).toHaveBeenCalledTimes(1)
    await tick(MINUTE)
    expect(auth.lock).toHaveBeenCalledTimes(1)
  })

  it('a gesture in this tab pushes the lock back', async () => {
    render(<SessionWarning />)
    await tick(4 * MINUTE)
    fireEvent.keyDown(window, { key: 'a' })
    await tick(8 * MINUTE)
    expect(auth.lock).not.toHaveBeenCalled()
    await tick(3 * MINUTE)
    expect(auth.lock).toHaveBeenCalledTimes(1)
  })

  it('a gesture in another tab of the session pushes the lock back too', async () => {
    render(<SessionWarning />)
    await tick(4 * MINUTE)
    act(() => { noteGesture() }) // as the other tab records it
    await tick(8 * MINUTE)
    expect(auth.lock).not.toHaveBeenCalled()
    await tick(3 * MINUTE)
    expect(auth.lock).toHaveBeenCalledTimes(1)
  })
})
