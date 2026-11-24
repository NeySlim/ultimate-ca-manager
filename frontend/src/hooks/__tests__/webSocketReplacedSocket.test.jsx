/**
 * A socket still trying when the app connects again is closed, and its events no longer touch
 * the timers of the socket that replaced it: the new handshake keeps its watchdog.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render } from '@testing-library/react'

const made = []
function fakeSocket() {
  const handlers = new Map()
  const manager = new Map()
  const socket = {
    handlers, manager,
    on: (evt, cb) => { handlers.set(evt, cb) },
    emit: vi.fn(), connect: vi.fn(), disconnect: vi.fn(),
    connected: false, active: true,
    io: { on: (evt, cb) => { manager.set(evt, cb) } },
  }
  made.push(socket)
  return socket
}
vi.mock('socket.io-client', () => ({ io: vi.fn(() => fakeSocket()) }))
vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
  NotificationProvider: ({ children }) => children,
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true }),
  AuthProvider: ({ children }) => children,
}))

import { HANDSHAKE_WATCHDOG_MS, SERVER_CUT_RETRY_MS, WebSocketProvider, useWebSocket } from '../useWebSocket'

let api
function Probe() { api = useWebSocket(); return null }

describe('a socket replaced while it was still trying', () => {
  beforeEach(() => { made.length = 0; vi.useFakeTimers() })
  afterEach(() => vi.useRealTimers())

  it('is closed, and its manager no longer stops the watchdog of the new handshake', () => {
    render(<WebSocketProvider><Probe /></WebSocketProvider>)
    const first = made[0]
    act(() => { api.connect() })
    const second = made[made.length - 1]
    expect(second).not.toBe(first)
    expect(first.disconnect).toHaveBeenCalled()
    act(() => { second.manager.get('open')() })
    act(() => { first.manager.get('close')() })
    act(() => { first.manager.get('open')?.() })
    act(() => { vi.advanceTimersByTime(HANDSHAKE_WATCHDOG_MS) })
    expect(second.disconnect).toHaveBeenCalledTimes(1)
    act(() => { vi.advanceTimersByTime(SERVER_CUT_RETRY_MS[0]) })
    expect(second.connect).toHaveBeenCalledTimes(1)
    expect(first.connect).not.toHaveBeenCalled()
  })
})
