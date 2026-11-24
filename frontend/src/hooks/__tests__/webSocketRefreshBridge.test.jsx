/**
 * A change made elsewhere refreshes the table, not just the toast.
 *
 * The pages listen on the in-app `ucm:data-changed` bus, which only the
 * acting tab fired. A second operator saw the revocation toast beside a list
 * that still showed the certificate as valid until a manual reload.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, act } from '@testing-library/react'

const socketHandlers = new Map()
const fakeSocket = {
  on: (evt, cb) => { socketHandlers.set(evt, cb) },
  emit: vi.fn(),
  disconnect: vi.fn(),
  connected: false,
  io: { on: vi.fn() },
}
vi.mock('socket.io-client', () => ({ io: vi.fn(() => fakeSocket) }))

vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(),
    showWarning: vi.fn(), showInfo: vi.fn(),
  }),
  NotificationProvider: ({ children }) => children,
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true }),
  AuthProvider: ({ children }) => children,
}))

import { WebSocketProvider, EventType } from '../useWebSocket'

// The announcements are coalesced, so the burst has to be let through.
function watch(send) {
  const seen = []
  const listener = (e) => seen.push(e.detail?.type)
  window.addEventListener('ucm:data-changed', listener)
  act(() => { send(socketHandlers) })
  act(() => { vi.advanceTimersByTime(500) })
  window.removeEventListener('ucm:data-changed', listener)
  return seen
}

function collect(send) {
  render(<WebSocketProvider><div /></WebSocketProvider>)
  return watch(send)
}

function emit(payload) {
  return collect((handlers) => handlers.get('event')(payload))
}

describe('the socket announces the change on the refresh bus', () => {
  beforeEach(() => { socketHandlers.clear(); vi.useFakeTimers() })
  afterEach(() => vi.useRealTimers())

  it.each([
    [EventType.CERTIFICATE_REVOKED, 'certificate'],
    [EventType.CERTIFICATE_ISSUED, 'certificate'],
    [EventType.CERTIFICATE_DELETED, 'certificate'],
    [EventType.CA_CREATED, 'ca'],
    [EventType.CA_DELETED, 'ca'],
    [EventType.CRL_REGENERATED, 'ca'],
    [EventType.USER_CREATED, 'user'],
    [EventType.GROUP_DELETED, 'group'],
  ])('%s refreshes the %s pages', (type, resource) => {
    expect(emit({ type, data: {} })).toEqual([resource])
  })

  it('says nothing for an event that changes no table', () => {
    expect(emit({ type: 'nope.nope', data: {} })).toEqual([])
    expect(emit({ type: EventType.SYSTEM_ALERT, data: {} })).toEqual([])
  })

  it('says nothing for a sign-in', () => {
    // user.login and user.logout reach every holder of read:audit, and a
    // last-login column is not worth reloading the users page for.
    expect(emit({ type: EventType.USER_LOGIN, data: {} })).toEqual([])
    expect(emit({ type: EventType.USER_LOGOUT, data: {} })).toEqual([])
  })

  it('collapses a burst into one announcement per resource', () => {
    // A bulk revoke emits one event per certificate; 200 of them used to be
    // 200 reloads of the whole page, in every open tab.
    const seen = collect((handlers) => {
      const onEvent = handlers.get('event')
      for (let i = 0; i < 200; i += 1) {
        onEvent({ type: EventType.CERTIFICATE_REVOKED, data: { id: i } })
      }
      onEvent({ type: EventType.CA_UPDATED, data: {} })
    })
    expect(seen.sort()).toEqual(['ca', 'certificate'])
  })
})

describe('a reconnection refreshes what it may have missed', () => {
  beforeEach(() => { socketHandlers.clear(); vi.useFakeTimers() })
  afterEach(() => vi.useRealTimers())

  it('says nothing on the first connection', () => {
    expect(collect((handlers) => handlers.get('connect')())).toEqual([])
  })

  it('refreshes every table after the socket comes back', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    act(() => { socketHandlers.get('connect')() })
    act(() => { socketHandlers.get('disconnect')('transport close') })

    const seen = watch((handlers) => handlers.get('connect')())
    // Events sent while it was down are gone; the tables reload instead.
    expect(new Set(seen)).toEqual(new Set(['certificate', 'ca', 'user', 'group']))
    // Once each, not once per event type that maps to it.
    expect(seen.length).toBe(4)
  })
})
