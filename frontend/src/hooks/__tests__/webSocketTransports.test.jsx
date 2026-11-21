/**
 * The socket opens on WebSocket only: engine.io-client falls back to another
 * transport only with tryAllTransports, so a second entry would never be used.
 */
import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'

const fakeSocket = { on: vi.fn(), emit: vi.fn(), disconnect: vi.fn(), connected: false }
const socketIo = vi.hoisted(() => ({ io: vi.fn() }))
vi.mock('socket.io-client', () => ({ io: (...a) => { socketIo.io(...a); return fakeSocket } }))

vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
  NotificationProvider: ({ children }) => children,
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true }),
  AuthProvider: ({ children }) => children,
}))

import { WebSocketProvider } from '../useWebSocket'

describe('socket transports', () => {
  it('asks for WebSocket and nothing else', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    expect(socketIo.io).toHaveBeenCalledTimes(1)
    const options = socketIo.io.mock.calls[0][1]
    expect(options.transports).toEqual(['websocket'])
    expect(options.tryAllTransports).toBeUndefined()
  })
})
