/**
 * A session renewal closes every socket of the old session: the tab opens it again once,
 * with the cookie the renewal set, and a handshake the server refuses is not retried.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render } from '@testing-library/react'

const auth = vi.hoisted(() => ({ value: { isAuthenticated: true } }))
const socketHandlers = new Map()
const fakeSocket = {
  on: (evt, cb) => { socketHandlers.set(evt, cb) },
  emit: vi.fn(),
  connect: vi.fn(),
  disconnect: vi.fn(),
  connected: false,
}
vi.mock('socket.io-client', () => ({ io: vi.fn(() => fakeSocket) }))

vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
  NotificationProvider: ({ children }) => children,
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => auth.value,
  AuthProvider: ({ children }) => children,
}))

import { SERVER_CUT_RECONNECT_MS, WebSocketProvider } from '../useWebSocket'

const fire = (evt, ...args) => act(() => { socketHandlers.get(evt)(...args) })
const elapse = (ms) => act(() => { vi.advanceTimersByTime(ms) })

describe('a socket closed by the server', () => {
  beforeEach(() => {
    socketHandlers.clear()
    fakeSocket.connect.mockClear()
    fakeSocket.connected = false
    auth.value = { isAuthenticated: true }
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('reconnects once, after the renewal answer had time to set its cookie', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    expect(fakeSocket.connect).not.toHaveBeenCalled()
    elapse(SERVER_CUT_RECONNECT_MS)
    expect(fakeSocket.connect).toHaveBeenCalledTimes(1)
  })

  it('does not retry a handshake the server refuses', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    elapse(SERVER_CUT_RECONNECT_MS)
    fire('connect_error', new Error('refused'))
    elapse(10 * SERVER_CUT_RECONNECT_MS)
    expect(fakeSocket.connect).toHaveBeenCalledTimes(1)
  })

  it('reconnects once per cut: a socket back and cut again reconnects again', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    elapse(SERVER_CUT_RECONNECT_MS)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    elapse(SERVER_CUT_RECONNECT_MS)
    expect(fakeSocket.connect).toHaveBeenCalledTimes(2)
  })

  it('leaves a transport loss to the client library', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'transport close')
    elapse(10 * SERVER_CUT_RECONNECT_MS)
    expect(fakeSocket.connect).not.toHaveBeenCalled()
  })

  it('does not reconnect a socket the app closed meanwhile (sign-out)', () => {
    const view = render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    auth.value = { isAuthenticated: false }
    view.rerender(<WebSocketProvider><div /></WebSocketProvider>)
    elapse(10 * SERVER_CUT_RECONNECT_MS)
    expect(fakeSocket.connect).not.toHaveBeenCalled()
  })
})
