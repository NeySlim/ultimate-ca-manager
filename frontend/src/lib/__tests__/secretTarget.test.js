import { describe, expect, it } from 'vitest'
import {
  changedTargets, secretInputProps, secretRequiredForTarget, smtpSecretTargets, typedSecret,
} from '../secretTarget'

const t = (key) => key
const base = {
  saved: { host: 'ldap.example.com', port: 636, tls: true, ca: '' },
  fields: ['host', 'port', 'tls', 'ca'],
  secretSaved: true,
}

describe('secretTarget', () => {
  it('compares targets the way the form sends them back', () => {
    expect(changedTargets(base.saved, { host: ' ldap.example.com ', port: '636', tls: true, ca: null },
      base.fields)).toEqual([])
    expect(changedTargets(base.saved, { ...base.saved, port: 389, tls: false }, base.fields))
      .toEqual(['port', 'tls'])
  })

  it('treats blank and masked values as "keep the saved secret"', () => {
    for (const kept of ['', '  ', '***', '********', undefined, null]) expect(typedSecret(kept)).toBe(false)
    expect(typedSecret('typed')).toBe(true)
  })

  it('asks for the secret only when a saved one would follow a moved target', () => {
    const moved = { ...base.saved, host: 'ldap.attacker.example' }
    expect(secretRequiredForTarget({ ...base, current: moved, secret: '' })).toBe(true)
    expect(secretRequiredForTarget({ ...base, current: moved, secret: '***' })).toBe(true)
    expect(secretRequiredForTarget({ ...base, current: moved, secret: 'typed' })).toBe(false)
    expect(secretRequiredForTarget({ ...base, current: base.saved, secret: '' })).toBe(false)
    expect(secretRequiredForTarget({ ...base, secretSaved: false, current: moved, secret: '' })).toBe(false)
  })

  it('makes the secret field required with the reason', () => {
    const moved = { ...base.saved, port: 389 }
    expect(secretInputProps(t, { ...base, current: moved, secret: '' })).toEqual({
      required: true, hasExistingValue: false, error: 'common.secretRequiredForTarget',
    })
    expect(secretInputProps(t, { ...base, current: base.saved, secret: '' })).toEqual({})
  })

  it('SMTP: asks only for the secret the chosen method uses', () => {
    const saved = { smtp_host: 'smtp.example.com', smtp_port: 587, smtp_username: 'mailer',
      smtp_security: 'starttls', smtp_password: '********', has_oauth_client_secret: true,
      smtp_oauth_token_url: 'https://login.example.com/token' }
    const moved = { ...saved, smtp_host: 'smtp.attacker.example', smtp_auth_method: 'password' }
    let targets = smtpSecretTargets(saved, moved)
    expect(secretRequiredForTarget(targets.password)).toBe(true)
    expect(secretRequiredForTarget(targets.oauth)).toBe(false)

    targets = smtpSecretTargets(saved, { ...saved, smtp_auth_method: 'oauth2',
      smtp_oauth_token_url: 'https://login.attacker.example/token' })
    expect(secretRequiredForTarget(targets.oauth)).toBe(true)
    expect(secretRequiredForTarget(targets.password)).toBe(false)

    // The password is unused under OAuth: the server drops it rather than move it
    targets = smtpSecretTargets(saved, { ...moved, smtp_auth_method: 'oauth2' })
    expect(secretRequiredForTarget(targets.password)).toBe(false)

    // A cleared username sends the password nowhere new; the server ignores it too
    targets = smtpSecretTargets(saved, { ...saved, smtp_auth_method: 'password', smtp_username: '' })
    expect(secretRequiredForTarget(targets.password)).toBe(false)
  })
})
