/**
 * #384: once the inactivity timeout passed, an unreachable server (a laptop
 * waking before the network is back) logged the tab out, without even
 * reaching the server. Only a check that says the session is gone may.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act, screen, fireEvent } from '@testing-library/react'

const auth = vi.hoisted(() => ({ checkSession: vi.fn(), logout: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../index.js', () => ({
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
}))
vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { username: 'admin' }, ...auth }),
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
    auth.logout.mockReset()
    timeout.seconds = 1
  })
  afterEach(() => vi.useRealTimers())

  it('does not log out while the session check cannot answer, and asks again later', async () => {
    auth.checkSession.mockResolvedValue(null)
    render(<SessionWarning />)
    await tick(5000)
    expect(auth.checkSession).toHaveBeenCalledTimes(1)
    expect(auth.logout).not.toHaveBeenCalled()

    await tick(30000)
    expect(auth.checkSession).toHaveBeenCalledTimes(2)
    expect(auth.logout).not.toHaveBeenCalled()
  })

  it('logs out once the server says the session is gone', async () => {
    auth.checkSession.mockResolvedValueOnce(null).mockResolvedValue(false)
    render(<SessionWarning />)
    await tick(5000)
    expect(auth.logout).not.toHaveBeenCalled()
    await tick(30000)
    expect(auth.logout).toHaveBeenCalledTimes(1)
  })

  it('still locks the tab once the server stayed unreachable for five minutes', async () => {
    auth.checkSession.mockResolvedValue(null)
    render(<SessionWarning />)
    await tick(4 * 60 * 1000)
    expect(auth.logout).not.toHaveBeenCalled()
    await tick(2 * 60 * 1000)
    expect(auth.logout).toHaveBeenCalledTimes(1)
  })

  it('"Stay logged in" leaves the warning up when the server cannot answer', async () => {
    timeout.seconds = 400 // the warning shows in the last 5 minutes
    auth.checkSession.mockResolvedValue(null)
    render(<SessionWarning />)
    await tick(120 * 1000)
    fireEvent.click(screen.getByText('session.stayLoggedIn'))
    await tick(0)
    expect(auth.checkSession).toHaveBeenCalled()
    expect(auth.logout).not.toHaveBeenCalled()
    expect(screen.getByText('session.stayLoggedIn')).toBeInTheDocument()
  })
})
