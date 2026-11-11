/**
 * DUP-FE-006 — real-time WebSocket toasts must go through i18n.
 *
 * `getEventNotification()` used to hardcode English sentences while the
 * `notifications.*` keys sat unreferenced in all nine locales. These tests pin
 * the mapping to the existing keys, and prove the provider actually hands `t`
 * down to it (a translated function that never reaches the socket handler is
 * worth nothing).
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'

// ── socket.io-client: capture the handlers the provider registers ──
const socketHandlers = new Map()
const fakeSocket = {
  on: (evt, cb) => { socketHandlers.set(evt, cb) },
  emit: vi.fn(),
  disconnect: vi.fn(),
  connected: false,
}
vi.mock('socket.io-client', () => ({ io: vi.fn(() => fakeSocket) }))

const notify = {
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showWarning: vi.fn(),
  showInfo: vi.fn(),
}
vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => notify,
  NotificationProvider: ({ children }) => children,
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true }),
  AuthProvider: ({ children }) => children,
}))

import i18n from '../../i18n'
import { WebSocketProvider, EventType, getEventNotification } from '../useWebSocket'

describe('DUP-FE-006 — getEventNotification() uses the existing notifications.* keys', () => {
  let t

  beforeAll(async () => {
    await i18n.changeLanguage('fr')
    t = i18n.getFixedT('fr')
  })

  const cases = [
    [EventType.CERTIFICATE_ISSUED, { cn: 'web.example.com' }, 'showSuccess', 'Certificat émis : web.example.com'],
    [EventType.CERTIFICATE_REVOKED, { cn: 'web.example.com' }, 'showWarning', 'Certificat révoqué : web.example.com'],
    [EventType.CA_CREATED, { name: 'Root CA' }, 'showSuccess', 'AC créée : Root CA'],
    [EventType.CA_REVOKED, { name: 'Root CA' }, 'showError', 'AC révoquée : Root CA'],
    [EventType.CRL_REGENERATED, { ca_name: 'Root CA' }, 'showInfo', 'CRL régénérée pour Root CA'],
    [EventType.USER_LOGIN, { username: 'alice' }, 'showInfo', 'Utilisateur connecté : alice'],
    [EventType.USER_LOGOUT, { username: 'alice' }, 'showInfo', 'Utilisateur déconnecté : alice'],
    [EventType.CERTIFICATE_BINDING_LEFT_BEHIND, { binding: { type: 'deploy', target_name: 'web01' } }, 'showWarning',
      'Un renouvellement a laissé web01 sur le certificat précédent'],
  ]

  it.each(cases)('%s is translated', (type, data, method, expected) => {
    expect(getEventNotification({ type, data }, t)).toEqual({ method, msg: expected })
  })

  it('certificate.expiring keeps the day count even though the key has no {{days}} placeholder', () => {
    // notifications.certificateExpiring only interpolates {{name}}; the day
    // count is appended through the existing common.daysLeft key.
    const notif = getEventNotification(
      { type: EventType.CERTIFICATE_EXPIRING, data: { cn: 'web.example.com', days_left: 7 } },
      t,
    )
    expect(notif.method).toBe('showWarning')
    expect(notif.msg).toBe('Certificat expire bientôt : web.example.com (7j restants)')
    // Never leak a raw i18n key or an unresolved placeholder into a toast.
    expect(notif.msg).not.toMatch(/\{\{|notifications\./)
  })

  it('certificate.expiring without days_left falls back to the bare sentence', () => {
    const notif = getEventNotification(
      { type: EventType.CERTIFICATE_EXPIRING, data: { cn: 'web.example.com' } },
      t,
    )
    expect(notif.msg).toBe('Certificat expire bientôt : web.example.com')
  })

  it('system.alert still relays the backend-supplied message verbatim', () => {
    expect(getEventNotification(
      { type: EventType.SYSTEM_ALERT, data: { severity: 'critical', message: 'Disk almost full' } },
      t,
    )).toEqual({ method: 'showError', msg: 'Disk almost full' })
    expect(getEventNotification(
      { type: EventType.SYSTEM_ALERT, data: { severity: 'warning', message: 'Slow queries' } },
      t,
    ).method).toBe('showWarning')
    expect(getEventNotification(
      { type: EventType.SYSTEM_ALERT, data: { severity: 'info', message: 'Rotated logs' } },
      t,
    ).method).toBe('showInfo')
  })

  it('unknown event types produce no toast', () => {
    expect(getEventNotification({ type: 'nope.nope', data: {} }, t)).toBeNull()
  })

  it('never returns an untranslated key for the events that have one', () => {
    for (const [type, data] of cases) {
      const { msg } = getEventNotification({ type, data }, t)
      expect(msg.startsWith('notifications.')).toBe(false)
    }
  })
})

describe('DUP-FE-006 — the provider wires t() into the socket event handler', () => {
  beforeEach(async () => {
    socketHandlers.clear()
    notify.showSuccess.mockClear()
    notify.showWarning.mockClear()
    notify.showError.mockClear()
    notify.showInfo.mockClear()
    await i18n.changeLanguage('fr')
  })

  it('dispatches a translated toast for a real socket event', () => {
    render(<WebSocketProvider><div /></WebSocketProvider>)
    const onEvent = socketHandlers.get('event')
    expect(onEvent, 'provider must register an "event" handler').toBeTypeOf('function')

    act(() => {
      onEvent({ type: EventType.CERTIFICATE_ISSUED, data: { cn: 'web.example.com' } })
    })

    expect(notify.showSuccess).toHaveBeenCalledWith('Certificat émis : web.example.com')
  })
})
