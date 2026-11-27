/**
 * The separation of roles of key recovery, as the server enforces it
 * (api/v2/key_recovery.py): the queue offers exactly what would be accepted.
 */
import { describe, it, expect } from 'vitest'
import { recoveryRights } from '../recoveryRules'

const perms = (...granted) => (p) => granted.includes(p)
const ADMIN = perms('admin:key_recovery', 'write:key_recovery', 'read:key_recovery')
const OPERATOR = perms('write:key_recovery', 'read:key_recovery')
const READER = perms('read:key_recovery')
const pending = { id: 1, status: 'pending', requested_by: 'alice', requested_by_id: 11 }
const approved = { id: 2, status: 'approved', requested_by: 'alice', requested_by_id: 11 }
const ID = { alice: 11, bob: 12, carol: 13 }

describe('recoveryRights', () => {
  it('lets an administrator approve and reject the request of another user', () => {
    expect(recoveryRights(pending, { hasPermission: ADMIN, username: 'bob', userId: ID.bob, dualControl: true })).toEqual({ approve: true, reject: true, recover: false })
  })

  it('with dual control, refuses the approval of one\'s own request but keeps its rejection', () => {
    expect(recoveryRights(pending, { hasPermission: ADMIN, username: 'alice', userId: ID.alice, dualControl: true })).toEqual({ approve: false, reject: true, recover: false })
  })

  it('without dual control, lets an administrator approve their own request', () => {
    expect(recoveryRights(pending, { hasPermission: ADMIN, username: 'alice', userId: ID.alice, dualControl: false }).approve).toBe(true)
  })

  it('gives no decision to a user without admin:key_recovery', () => {
    expect(recoveryRights(pending, { hasPermission: OPERATOR, username: 'bob', userId: ID.bob, dualControl: true })).toEqual({ approve: false, reject: false, recover: false })
  })

  it('lets the requester recover an approved key with write:key_recovery', () => {
    expect(recoveryRights(approved, { hasPermission: OPERATOR, username: 'alice', userId: ID.alice, dualControl: true }).recover).toBe(true)
  })

  it('lets an administrator recover a key another user asked for', () => {
    expect(recoveryRights(approved, { hasPermission: ADMIN, username: 'bob', userId: ID.bob, dualControl: true }).recover).toBe(true)
  })

  it('refuses the recovery to another non-administrator, and to a reader', () => {
    expect(recoveryRights(approved, { hasPermission: OPERATOR, username: 'carol', userId: ID.carol, dualControl: true }).recover).toBe(false)
    expect(recoveryRights(approved, { hasPermission: READER, username: 'alice', userId: ID.alice, dualControl: true }).recover).toBe(false)
  })

  it('offers nothing on a closed request', () => {
    for (const status of ['rejected', 'recovered', 'cancelled']) {
      expect(recoveryRights({ status, requested_by: 'alice' }, { hasPermission: ADMIN, username: 'alice', userId: ID.alice, dualControl: false }))
        .toEqual({ approve: false, reject: false, recover: false })
    }
  })

  it('recognises the requester by account id: a later account with the same name is somebody else', () => {
    const later = { hasPermission: OPERATOR, username: 'alice', userId: 99, dualControl: true }
    expect(recoveryRights(approved, later).recover).toBe(false)
    expect(recoveryRights(approved, { ...later, userId: 11, username: 'alice-renamed' }).recover).toBe(true)
  })

  it('holds an approval back on the requester id or name, and gives a request without an id to administrators only', () => {
    expect(recoveryRights(pending, { hasPermission: ADMIN, username: 'renamed', userId: 11, dualControl: true }).approve).toBe(false)
    const legacy = { status: 'approved', requested_by: 'alice', requested_by_id: null }
    expect(recoveryRights(legacy, { hasPermission: OPERATOR, username: 'alice', userId: 11, dualControl: true }).recover).toBe(false)
    expect(recoveryRights(legacy, { hasPermission: ADMIN, username: 'bob', userId: 12, dualControl: true }).recover).toBe(true)
  })
})
