/**
 * The expiry warning is a banner over the console: it shows in the last five
 * minutes, takes no focus, stays up under activity until Extend, and locks at the end.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act, screen, fireEvent } from '@testing-library/react'

const auth = vi.hoisted(() => ({ checkSession: vi.fn(), lock: vi.fn(), showSuccess: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, o) => (o?.time ? `${key}|${o.time}` : o?.minutes != null ? `${key}|${o.minutes}` : key) }) }))
vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { username: 'admin' }, checkSession: auth.checkSession, lock: auth.lock }),
  useNotification: () => ({ showSuccess: auth.showSuccess }),
}))
vi.mock('../../services', () => ({
  authService: { getCurrentUser: vi.fn(async () => ({ data: { session_timeout: 400 } })) },
}))

import { SessionWarning } from '../SessionWarning'

const tick = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })

describe('SessionWarning banner', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    auth.checkSession.mockReset()
    auth.lock.mockReset()
    auth.showSuccess.mockReset()
  })
  afterEach(() => vi.useRealTimers())

  function renderWithFocus() {
    render(<><button type="button">work</button><SessionWarning /></>)
    screen.getByText('work').focus()
  }

  it('shows in the last five minutes only, with the time left, and takes no focus', async () => {
    renderWithFocus()
    await tick(90 * 1000)
    expect(screen.queryByRole('region')).toBeNull()
    await tick(15 * 1000)
    const banner = screen.getByRole('region', { name: /session\.expiresIn/ })
    expect(banner).toHaveTextContent('session.expiresIn|4:5')
    expect(banner).toHaveTextContent('session.lockNotice')
    expect(document.activeElement).toBe(screen.getByText('work'))
  })

  it('stays up under activity: only Extend keeps the session', async () => {
    auth.checkSession.mockResolvedValue(true)
    renderWithFocus()
    await tick(110 * 1000)
    fireEvent.keyDown(window, { key: 'a' })
    fireEvent.mouseDown(window)
    await tick(2000)
    // The countdown goes on from where it was: activity no longer pushes the end back
    expect(screen.getByRole('region')).toHaveTextContent('session.expiresIn|4:48')
    fireEvent.click(screen.getByRole('button', { name: 'session.extend' }))
    await tick(0)
    expect(auth.checkSession).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('region')).toBeNull()
  })

  it('announces the time left once, when it appears', async () => {
    renderWithFocus()
    await tick(105 * 1000)
    expect(screen.getByText('session.announceLeft|4:55')).toBeInTheDocument()
    await tick(3000)
    expect(screen.getByText('session.announceLeft|4:55')).toBeInTheDocument()
  })

  it('Extend says how long the session was extended, aloud and in a toast', async () => {
    auth.checkSession.mockResolvedValue(true)
    renderWithFocus()
    await tick(110 * 1000)
    fireEvent.click(screen.getByRole('button', { name: 'session.extend' }))
    await tick(0)
    // 400 s of inactivity timeout, in whole minutes
    expect(auth.showSuccess).toHaveBeenCalledWith('session.extended|7')
    expect(screen.getByText('session.extended|7')).toBeInTheDocument()
  })

  it('locks when Extend finds the session already gone', async () => {
    auth.checkSession.mockResolvedValue(false)
    renderWithFocus()
    await tick(110 * 1000)
    fireEvent.click(screen.getByRole('button', { name: 'session.extend' }))
    await tick(0)
    expect(auth.lock).toHaveBeenCalledTimes(1)
  })

  it('locks at the end once the server confirms', async () => {
    auth.checkSession.mockResolvedValue(false)
    renderWithFocus()
    await tick(401 * 1000)
    expect(auth.lock).toHaveBeenCalledTimes(1)
  })
})
