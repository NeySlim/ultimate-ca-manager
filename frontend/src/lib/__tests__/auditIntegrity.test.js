import { describe, it, expect } from 'vitest'
import { integrityMessage } from '../auditIntegrity'

describe('integrityMessage', () => {
  it('names the entry an unsealed write broke the chain at', () => {
    const m = integrityMessage({ valid: false, status: 'broken', first_error_id: 42,
      first_error_code: 'not_sealed_by_key', error_count: 3 })
    expect(m).toEqual({ level: 'error', key: 'audit.integrityUnsealedAfterKey', params: { id: 42, errors: 3 } })
  })

  it('names the entry any other break is at', () => {
    const m = integrityMessage({ valid: false, status: 'broken', first_error_id: 7,
      first_error_code: 'tampered', errors: [{}] })
    expect(m.key).toBe('audit.integrityBroken')
    expect(m.params).toEqual({ id: 7, errors: 1 })
  })

  it('warns, not succeeds, when the log is not protected', () => {
    const m = integrityMessage({ valid: true, status: 'unprotected', checked: 10,
      protection: { key_available: false, not_attested: 10 } })
    expect(m.level).toBe('warning')
    expect(m.key).toBe('audit.integrityUnprotected')
  })

  it('warns when the key changed without this server recording it', () => {
    const m = integrityMessage({ valid: true, status: 'unprotected', checked: 9,
      protection: { key_rotation_id: 6, rotation_attested: false, not_attested: 5 } })
    expect(m).toEqual({ level: 'warning', key: 'audit.integrityRotationUnattested',
      params: { rotation: 6, older: 5 } })
  })

  it('says where a key rotation re-anchored the chain', () => {
    const m = integrityMessage({ valid: true, status: 'intact', checked: 9,
      protection: { protected_from_id: 5, key_rotation_id: 6, not_attested: 4, protected: 5 } })
    expect(m).toEqual({ level: 'success', key: 'audit.integrityIntactRotated',
      params: { id: 5, rotation: 6, older: 4 } })
  })

  it('reports a fully attested log as verified', () => {
    const m = integrityMessage({ valid: true, status: 'intact', checked: 3,
      protection: { protected_from_id: 1, not_attested: 0, protected: 3 } })
    expect(m).toEqual({ level: 'success', key: 'audit.integrityVerified', params: { count: 3 } })
  })
})
