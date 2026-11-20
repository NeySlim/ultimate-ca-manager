/**
 * Operation types and dates of the journal, in the mockup's words and forms.
 */
import { describe, it, expect, vi } from 'vitest'

vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))

import { typeOf, typeIcon, presentTypes, actionsOfType, effectiveActions, actionLabel } from '../activityTypes'
import { rowTime, fullTime, eventDate } from '../activityDates'

describe('operation types', () => {
  it.each([
    ['cert_created', 'issued'], ['certificate.issued', 'issued'], ['acme.order.finalize', 'issued'],
    ['certificate_renewed', 'renewed'], ['msca.renew', 'renewed'],
    ['cert_revoked', 'revoked'], ['ca_revoked', 'revoked'],
    ['apikey_revoke', 'users'], ['smtp_oauth_revoke', 'settings'], ['acme.eab_credential.revoke', 'acme'],
    ['login_failure', 'auth'], ['webauthn_register', 'auth'],
    ['key_recovery.approved', 'approval'], ['acme_auto_approve', 'approval'],
    ['crl_config', 'crl'], ['scep_config_update', 'scep'], ['est_config_update', 'settings'],
    ['backup_schedule_updated', 'backups'], ['cert_deleted', 'certificates'], ['template_create', 'setup'],
    ['database.migrate.success', 'system'], ['', 'system'], [null, 'system'],
  ])('%s is a %s', (action, type) => {
    expect(typeOf(action)).toBe(type)
  })

  it('draws each type with the mockup\'s pictogram', () => {
    expect(typeIcon('issued')).toBe('cert')
    expect(typeIcon('revoked')).toBe('block')
    expect(typeIcon('crl')).toBe('crl')
    expect(typeIcon('nope')).toBe('cert')
  })

  it('lists the types present in the server\'s list, in the select\'s order', () => {
    expect(presentTypes(['login_success', 'cert_revoked', 'cert_created'])).toEqual(['issued', 'revoked', 'auth'])
    expect(actionsOfType(['login_success', 'cert_revoked', 'logout'], 'auth')).toEqual(['login_success', 'logout'])
  })

  it('sends the type\'s actions narrowed by the chosen ones, or nothing that can match', () => {
    const all = ['login_success', 'login_failure', 'cert_revoked']
    expect(effectiveActions(all, '', [])).toBeNull()
    expect(effectiveActions(all, '', ['cert_revoked'])).toEqual(['cert_revoked'])
    expect(effectiveActions(all, 'auth', [])).toEqual(['login_success', 'login_failure'])
    expect(effectiveActions(all, 'auth', ['login_failure', 'cert_revoked'])).toEqual(['login_failure'])
    expect(effectiveActions(all, 'auth', ['cert_revoked'])).toEqual([])
  })

  it('reads an action code', () => {
    expect(actionLabel('cert_revoked')).toBe('Cert revoked')
    expect(actionLabel('key_recovery.approve_denied')).toBe('Key recovery approve denied')
    expect(actionLabel('')).toBe('')
  })
})

describe('dates of the journal', () => {
  const now = new Date('2026-11-08T12:00:00Z')
  it('shows the time alone today, the day and the time otherwise', () => {
    expect(rowTime('2026-11-08T10:42:18Z', 'fr', now)).toBe('10:42:18')
    expect(rowTime('2026-11-07T18:05:12Z', 'fr', now)).toBe('7 nov., 18:05:12')
    expect(rowTime('nope', 'fr', now)).toBe('')
  })

  it('writes the date as « 8 nov. 2026 » and the detail as « date, time »', () => {
    expect(eventDate('2026-11-08T10:42:18Z', 'fr')).toBe('8 nov. 2026')
    expect(fullTime('2026-11-05T02:00:41Z', 'fr')).toBe('5 nov. 2026, 02:00:41')
    expect(fullTime(null, 'fr')).toBe('')
  })
})
