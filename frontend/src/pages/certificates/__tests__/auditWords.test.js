/** The History panel's words for an audit action: the first rule that matches names it. */
import { describe, expect, it } from 'vitest'
import { auditWords } from '../inspector/auditWords'

describe('auditWords', () => {
  it('words the lift of a local revocation as such, not as a revocation (#450)', () => {
    expect(auditWords('certificate_local_revocation_lifted')).toBe('revocationLifted')
    expect(auditWords('user_certificate_revoked')).toBe('revokedPlain')
    expect(auditWords('certificate_unheld')).toBe('unheld')
  })
})
