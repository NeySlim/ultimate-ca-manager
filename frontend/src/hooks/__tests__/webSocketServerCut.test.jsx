/**
 * A socket the server closes (a session renewal) or a handshake it refuses (its session check
 * could not run, a cookie not there yet) is tried again on a bounded schedule, then once more at
 * the next answer of the API or when the tab is shown again: never in an unbounded loop.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render } from '@testing-library/react'

const auth = vi.hoisted(() => ({ value: { isAuthenticated: true } }))
const socketHandlers = new Map()
const managerHandlers = new Map()
const fakeSocket = {
  on: (evt, cb) => { socketHandlers.set(evt, cb) },
  emit: vi.fn(),
  connect: vi.fn(),
  disconnect: vi.fn(),
  connected: false,
  active: false,
  io: { on: (evt, cb) => { managerHandlers.set(evt, cb) } },
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

import {
  HANDSHAKE_WATCHDOG_MS, REARM_MIN_INTERVAL_MS, SERVER_CUT_RECONNECT_MS, SERVER_CUT_RETRY_MS, WebSocketProvider,
} from '../useWebSocket'
import { API_ANSWERED_EVENT } from '../../services/apiClient'

const fire = (evt, ...args) => act(() => { socketHandlers.get(evt)(...args) })
// The transport is open: the handshake (CONNECT of the namespace) is on its way
const transportOpen = () => act(() => { managerHandlers.get('open')() })
const elapse = (ms) => act(() => { vi.advanceTimersByTime(ms) })
const refused = () => fire('connect_error', new Error('session check unavailable'))
const apiAnswered = () => act(() => { window.dispatchEvent(new CustomEvent(API_ANSWERED_EVENT)) })
const setVisibility = (state) => {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state })
  act(() => { document.dispatchEvent(new Event('visibilitychange')) })
}
const total = SERVER_CUT_RETRY_MS.reduce((a, b) => a + b, 0)

// Every scheduled attempt refused, as a session check that cannot run would answer
function refuseEveryAttempt() {
  for (const delay of SERVER_CUT_RETRY_MS) {
    elapse(delay)
    refused()
  }
}

describe('a socket closed by the server', () => {
  beforeEach(() => {
    socketHandlers.clear()
    managerHandlers.clear()
    fakeSocket.connect.mockClear()
    fakeSocket.disconnect.mockClear()
    fakeSocket.connected = false
    fakeSocket.active = false
    auth.value = { isAuthenticated: true }
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('reconnects after the renewal answer had time to set its cookie', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    expect(fakeSocket.connect).not.toHaveBeenCalled()
    elapse(SERVER_CUT_RECONNECT_MS)
    expect(fakeSocket.connect).toHaveBeenCalledTimes(1)
  })

  it('tries a refused handshake again on the bounded schedule, then stops', () => {
    expect(SERVER_CUT_RETRY_MS.length).toBeGreaterThan(1)
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    refuseEveryAttempt()
    expect(fakeSocket.connect).toHaveBeenCalledTimes(SERVER_CUT_RETRY_MS.length)
    elapse(100 * total)
    expect(fakeSocket.connect).toHaveBeenCalledTimes(SERVER_CUT_RETRY_MS.length)
  })

  it('tries a first handshake the server refuses again too', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    refused()
    elapse(SERVER_CUT_RETRY_MS[0])
    expect(fakeSocket.connect).toHaveBeenCalledTimes(1)
  })

  it('starts the schedule again once a socket is back and cut again', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    refuseEveryAttempt()
    fire('connect')
    fire('disconnect', 'io server disconnect')
    elapse(SERVER_CUT_RETRY_MS[0])
    expect(fakeSocket.connect).toHaveBeenCalledTimes(SERVER_CUT_RETRY_MS.length + 1)
  })

  it('starts from the first delay for a refusal once the socket was back', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    refuseEveryAttempt()
    fire('connect')
    // The library reconnects after a transport loss, and the server refuses that handshake
    fakeSocket.active = true
    fire('disconnect', 'transport close')
    fakeSocket.active = false
    refused()
    elapse(SERVER_CUT_RETRY_MS[0])
    expect(fakeSocket.connect).toHaveBeenCalledTimes(SERVER_CUT_RETRY_MS.length + 1)
  })

  it('tries once more at the next answer of the API, at most once per interval', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    refuseEveryAttempt()
    const scheduled = SERVER_CUT_RETRY_MS.length
    apiAnswered()
    expect(fakeSocket.connect).toHaveBeenCalledTimes(scheduled + 1)
    refused()
    apiAnswered()
    elapse(REARM_MIN_INTERVAL_MS - 1)
    apiAnswered()
    expect(fakeSocket.connect).toHaveBeenCalledTimes(scheduled + 1)
    elapse(1)
    apiAnswered()
    expect(fakeSocket.connect).toHaveBeenCalledTimes(scheduled + 2)
    // A rearmed try refused schedules nothing more
    refused()
    elapse(100 * total)
    expect(fakeSocket.connect).toHaveBeenCalledTimes(scheduled + 2)
  })

  it('tries once more when the tab is shown again', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    refuseEveryAttempt()
    const scheduled = SERVER_CUT_RETRY_MS.length
    setVisibility('hidden')
    expect(fakeSocket.connect).toHaveBeenCalledTimes(scheduled)
    setVisibility('visible')
    expect(fakeSocket.connect).toHaveBeenCalledTimes(scheduled + 1)
  })

  it('does not rearm a socket that is connected, connecting or waiting for its next try', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fakeSocket.connected = true
    apiAnswered()
    fakeSocket.connected = false
    fire('disconnect', 'io server disconnect')
    apiAnswered()
    expect(fakeSocket.connect).not.toHaveBeenCalled()
    elapse(SERVER_CUT_RETRY_MS[0])
    fakeSocket.active = true
    apiAnswered()
    expect(fakeSocket.connect).toHaveBeenCalledTimes(1)
  })

  it('leaves a transport loss to the client library', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fakeSocket.active = true
    fire('disconnect', 'transport close')
    fire('connect_error', new Error('xhr poll error'))
    elapse(100 * total)
    expect(fakeSocket.connect).not.toHaveBeenCalled()
  })

  it('does not reconnect a socket the app closed meanwhile (sign-out)', () => {
    const view = render(<WebSocketProvider><div /></WebSocketProvider>)
    fire('connect')
    fire('disconnect', 'io server disconnect')
    auth.value = { isAuthenticated: false }
    view.rerender(<WebSocketProvider><div /></WebSocketProvider>)
    elapse(100 * total)
    apiAnswered()
    setVisibility('visible')
    expect(fakeSocket.connect).not.toHaveBeenCalled()
  })

  it('gives up a handshake the server never answers, then tries on the bounded schedule', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    transportOpen()
    elapse(HANDSHAKE_WATCHDOG_MS - 1)
    expect(fakeSocket.disconnect).not.toHaveBeenCalled()
    elapse(1)
    expect(fakeSocket.disconnect).toHaveBeenCalledTimes(1)
    elapse(SERVER_CUT_RETRY_MS[0])
    expect(fakeSocket.connect).toHaveBeenCalledTimes(1)
  })

  it('stops once the schedule is spent, every handshake left unanswered', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    transportOpen()
    for (const delay of SERVER_CUT_RETRY_MS) {
      elapse(HANDSHAKE_WATCHDOG_MS)
      elapse(delay)
      transportOpen()
    }
    elapse(HANDSHAKE_WATCHDOG_MS)
    expect(fakeSocket.disconnect).toHaveBeenCalledTimes(SERVER_CUT_RETRY_MS.length + 1)
    elapse(100 * total)
    expect(fakeSocket.connect).toHaveBeenCalledTimes(SERVER_CUT_RETRY_MS.length)
  })

  it('leaves an answered handshake alone', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    transportOpen()
    fire('connect')
    elapse(10 * HANDSHAKE_WATCHDOG_MS)
    expect(fakeSocket.disconnect).not.toHaveBeenCalled()
    transportOpen()
    refused()
    elapse(HANDSHAKE_WATCHDOG_MS)
    expect(fakeSocket.disconnect).not.toHaveBeenCalled()
  })

  it('leaves a transport that closed before the answer to the client library', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    transportOpen()
    act(() => { managerHandlers.get('close')('transport close') })
    elapse(10 * HANDSHAKE_WATCHDOG_MS)
    expect(fakeSocket.disconnect).not.toHaveBeenCalled()
  })
})
