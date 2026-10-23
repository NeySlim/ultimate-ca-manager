/**
 * The server refuses the socket while a forced password change or 2FA
 * enrolment is pending: the app connects once the gate lifts, not before.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'

const auth = vi.hoisted(() => ({ value: {} }))
const fakeSocket = { on: vi.fn(), emit: vi.fn(), disconnect: vi.fn(), connected: false }
const socketIo = vi.hoisted(() => ({ io: vi.fn() }))
vi.mock('socket.io-client', () => ({ io: (...a) => { socketIo.io(...a); return fakeSocket } }))

vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
  NotificationProvider: ({ children }) => children,
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => auth.value,
  AuthProvider: ({ children }) => children,
}))

import { WebSocketProvider } from '../useWebSocket'

describe('the socket waits for the forced gates', () => {
  beforeEach(() => { socketIo.io.mockClear() })

  it.each([
    [{ forcePasswordChange: true }],
    [{ mustEnroll2fa: true }],
  ])('does not connect while %o', (gate) => {
    auth.value = { isAuthenticated: true, ...gate }
    render(<WebSocketProvider><div /></WebSocketProvider>)
    expect(socketIo.io).not.toHaveBeenCalled()
  })

  it('connects once the gate lifts', () => {
    auth.value = { isAuthenticated: true, forcePasswordChange: true }
    const view = render(<WebSocketProvider><div /></WebSocketProvider>)
    auth.value = { isAuthenticated: true, forcePasswordChange: false }
    view.rerender(<WebSocketProvider><div /></WebSocketProvider>)
    expect(socketIo.io).toHaveBeenCalledTimes(1)
  })
})
