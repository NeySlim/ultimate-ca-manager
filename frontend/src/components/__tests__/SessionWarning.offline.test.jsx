/**
 * #384: an unreachable server (a laptop waking before the network is back) signed
 * the tab out. The end of the idle time now locks the tab, which keeps the session
 * for its unlock, and Extend never signs out while the server cannot answer.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act, screen, fireEvent } from '@testing-library/react'

const auth = vi.hoisted(() => ({ checkSession: vi.fn(), lock: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { username: 'admin' }, ...auth }),
  useNotification: () => ({ showSuccess: vi.fn() }),
}))
const timeout = vi.hoisted(() => ({ seconds: 1 }))
vi.mock('../../services', () => ({
  authService: { getCurrentUser: vi.fn(async () => ({ data: { session_timeout: timeout.seconds } })) },
}))

import { SessionWarning } from '../SessionWarning'

const tick = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })

describe('SessionWarning with the server unreachable (#384)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    auth.checkSession.mockReset()
    auth.lock.mockReset()
    timeout.seconds = 1
  })
  afterEach(() => vi.useRealTimers())

  it('locks at the end of the idle time without waiting for the server to answer', async () => {
    auth.checkSession.mockResolvedValue(null)
    render(<SessionWarning />)
    await tick(5000)
    expect(auth.lock).toHaveBeenCalledTimes(1)
    expect(auth.checkSession).not.toHaveBeenCalled()
  })

  it('Extend leaves the warning up when the server cannot answer', async () => {
    timeout.seconds = 400 // the warning shows in the last 5 minutes
    auth.checkSession.mockResolvedValue(null)
    render(<SessionWarning />)
    await tick(120 * 1000)
    fireEvent.click(screen.getByText('session.extend'))
    await tick(0)
    expect(auth.checkSession).toHaveBeenCalled()
    expect(auth.lock).not.toHaveBeenCalled()
    expect(screen.getByText('session.extend')).toBeInTheDocument()
  })
})
