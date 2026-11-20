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
const pending = { id: 1, status: 'pending', requested_by: 'alice' }
const approved = { id: 2, status: 'approved', requested_by: 'alice' }

describe('recoveryRights', () => {
  it('lets an administrator approve and reject the request of another user', () => {
    expect(recoveryRights(pending, { hasPermission: ADMIN, username: 'bob', dualControl: true })).toEqual({ approve: true, reject: true, recover: false })
  })

  it('with dual control, refuses the approval of one\'s own request but keeps its rejection', () => {
    expect(recoveryRights(pending, { hasPermission: ADMIN, username: 'alice', dualControl: true })).toEqual({ approve: false, reject: true, recover: false })
  })

  it('without dual control, lets an administrator approve their own request', () => {
    expect(recoveryRights(pending, { hasPermission: ADMIN, username: 'alice', dualControl: false }).approve).toBe(true)
  })

  it('gives no decision to a user without admin:key_recovery', () => {
    expect(recoveryRights(pending, { hasPermission: OPERATOR, username: 'bob', dualControl: true })).toEqual({ approve: false, reject: false, recover: false })
  })

  it('lets the requester recover an approved key with write:key_recovery', () => {
    expect(recoveryRights(approved, { hasPermission: OPERATOR, username: 'alice', dualControl: true }).recover).toBe(true)
  })

  it('lets an administrator recover a key another user asked for', () => {
    expect(recoveryRights(approved, { hasPermission: ADMIN, username: 'bob', dualControl: true }).recover).toBe(true)
  })

  it('refuses the recovery to another non-administrator, and to a reader', () => {
    expect(recoveryRights(approved, { hasPermission: OPERATOR, username: 'carol', dualControl: true }).recover).toBe(false)
    expect(recoveryRights(approved, { hasPermission: READER, username: 'alice', dualControl: true }).recover).toBe(false)
  })

  it('offers nothing on a closed request', () => {
    for (const status of ['rejected', 'recovered', 'cancelled']) {
      expect(recoveryRights({ status, requested_by: 'alice' }, { hasPermission: ADMIN, username: 'alice', dualControl: false }))
        .toEqual({ approve: false, reject: false, recover: false })
    }
  })
})
