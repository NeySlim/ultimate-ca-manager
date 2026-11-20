/**
 * Bounds checked before a save, one family at a time: ports, whole numbers in a range (in the
 * unit the field shows), a lower bound, a required server, an address, a URL. A field is only
 * checked once changed; syslog fields only while syslog is on.
 */
import { describe, expect, it } from 'vitest'
import { fieldBounds, fieldProblems, fieldSection } from '../fieldChecks'

const draft = (settings, syslog = { enabled: false }, ar = {}) => ({ settings, syslog, ar })
const keyOf = (out, field) => out[field]?.key

describe('fieldProblems', () => {
  it('refuses a port out of 1 to 65535, empty included, and accepts one inside', () => {
    for (const v of [0, 65536, 99999, '', '12a', -1]) {
      expect(keyOf(fieldProblems(draft({ smtp_port: v }), ['smtp_port']), 'smtp_port')).toBe('settings.portOutOfRange')
    }
    for (const v of [1, 587, '465', 65535]) expect(fieldProblems(draft({ smtp_port: v }), ['smtp_port'])).toEqual({})
  })

  it('checks only the fields that changed', () => {
    expect(Object.keys(fieldProblems(draft({ smtp_port: 99999, acme_public_port: 0 }), ['acme_public_port'])))
      .toEqual(['acme_public_port'])
  })

  it('checks a whole number in its range, in the unit the field shows', () => {
    // Stored in seconds, shown and bounded in minutes: 5 to 1440
    const out = fieldProblems(draft({ session_timeout: 99999 * 60 }), ['session_timeout'])
    expect(out.session_timeout).toEqual({ key: 'settings.check.range_minutes', values: { min: 5, max: 1440 } })
    expect(fieldProblems(draft({ session_timeout: 480 * 60 }), ['session_timeout'])).toEqual({})
    expect(keyOf(fieldProblems(draft({ max_login_attempts: 500 }), ['max_login_attempts']), 'max_login_attempts')).toBe('settings.check.range_count')
    expect(keyOf(fieldProblems(draft({ session_max_lifetime: 800 * 3600 }), ['session_max_lifetime']), 'session_max_lifetime')).toBe('settings.check.range_hours')
    expect(keyOf(fieldProblems(draft({ backup_retention_days: 0 }), ['backup_retention_days']), 'backup_retention_days')).toBe('settings.check.range_days')
    expect(keyOf(fieldProblems(draft({}, undefined, { days_before_expiry: '' }), ['ar.days_before_expiry']), 'ar.days_before_expiry')).toBe('settings.check.range_days')
  })

  it('checks a lower bound alone', () => {
    expect(fieldProblems(draft({ hsts_max_age: -1 }), ['hsts_max_age']).hsts_max_age).toEqual({ key: 'settings.check.atLeast', values: { min: 0, max: undefined } })
    expect(fieldProblems(draft({ hsts_max_age: 31536000 }), ['hsts_max_age'])).toEqual({})
  })

  it('takes 0 or 7 to 1825 days for the audit log retention', () => {
    for (const v of [0, 7, 1825]) expect(fieldProblems(draft({ audit_retention_days: v }), ['audit_retention_days'])).toEqual({})
    for (const v of [3, 1826]) expect(keyOf(fieldProblems(draft({ audit_retention_days: v }), ['audit_retention_days']), 'audit_retention_days')).toBe('settings.check.retention')
  })

  it('requires a valid syslog server while syslog is on', () => {
    expect(fieldProblems(draft({}, { enabled: false, host: '', port: 0 }), ['syslog.host', 'syslog.port'])).toEqual({})
    const out = fieldProblems(draft({}, { enabled: true, host: '', port: 0 }), ['syslog.host', 'syslog.port'])
    expect(keyOf(out, 'syslog.host')).toBe('settings.check.required')
    expect(keyOf(out, 'syslog.port')).toBe('settings.portOutOfRange')
    expect(keyOf(fieldProblems(draft({}, { enabled: true, host: 'bad host!', port: 514 }), ['syslog.host']), 'syslog.host')).toBe('settings.check.host')
    for (const host of ['syslog.example.com', '192.0.2.25', '2001:db8::1']) {
      expect(fieldProblems(draft({}, { enabled: true, host, port: 514 }), ['syslog.host'])).toEqual({})
    }
  })

  it('checks the format of an address and of a URL, an empty one allowed', () => {
    expect(keyOf(fieldProblems(draft({ smtp_from_email: 'pki@' }), ['smtp_from_email']), 'smtp_from_email')).toBe('settings.check.email')
    expect(fieldProblems(draft({ smtp_from_email: 'pki@example.com' }), ['smtp_from_email'])).toEqual({})
    expect(keyOf(fieldProblems(draft({ base_url: 'pki.example.com' }), ['base_url']), 'base_url')).toBe('settings.check.url')
    expect(keyOf(fieldProblems(draft({ base_url: 'ftp://pki.example.com' }), ['base_url']), 'base_url')).toBe('settings.check.url')
    for (const v of ['', 'https://pki.example.com']) expect(fieldProblems(draft({ base_url: v }), ['base_url'])).toEqual({})
  })

  it('names the section of each field and gives the input its bounds', () => {
    expect(fieldSection('syslog.port')).toBe('audit')
    expect(fieldSection('smtp_port')).toBe('email')
    expect(fieldSection('session_max_lifetime')).toBe('security')
    expect(fieldSection('ar.days_before_expiry')).toBe('autoRenewal')
    expect(fieldBounds('session_timeout')).toEqual({ min: 5, max: 1440 })
    expect(fieldBounds('hsts_max_age')).toEqual({ min: 0 })
    expect(fieldBounds('base_url')).toEqual({})
  })
})
