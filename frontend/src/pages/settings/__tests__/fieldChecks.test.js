/** Bounds checked before a save: ports from 1 to 65535, the syslog port only while syslog is on. */
import { describe, expect, it } from 'vitest'
import { fieldProblems, fieldSection } from '../fieldChecks'

const draft = (settings, syslog = { enabled: false }) => ({ settings, syslog })

describe('fieldProblems', () => {
  it('refuses a port out of 1 to 65535, empty included, and accepts one inside', () => {
    for (const v of [0, 65536, 99999, '', '12a', -1]) {
      expect(fieldProblems(draft({ smtp_port: v }), ['smtp_port'])).toEqual({ smtp_port: 'settings.portOutOfRange' })
    }
    for (const v of [1, 587, '465', 65535]) expect(fieldProblems(draft({ smtp_port: v }), ['smtp_port'])).toEqual({})
  })

  it('checks only the fields that changed', () => {
    expect(fieldProblems(draft({ smtp_port: 99999, acme_public_port: 0 }), ['acme_public_port']))
      .toEqual({ acme_public_port: 'settings.portOutOfRange' })
  })

  it('checks the syslog port while syslog is on, and names its section', () => {
    expect(fieldProblems(draft({}, { enabled: false, port: 0 }), ['syslog.port'])).toEqual({})
    expect(fieldProblems(draft({}, { enabled: true, port: 0 }), ['syslog.port'])).toEqual({ 'syslog.port': 'settings.portOutOfRange' })
    expect(fieldSection('syslog.port')).toBe('audit')
    expect(fieldSection('smtp_port')).toBe('email')
  })
})
