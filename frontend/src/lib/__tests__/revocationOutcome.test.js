import { describe, it, expect } from 'vitest'
import { localOnlyRevocationWarning } from '../revocationOutcome'

const t = (key) => key

describe('localOnlyRevocationWarning', () => {
  it('warns when only the related certificate was not told to its ACME CA', () => {
    const res = { message: 'Revoked. Related certificate #7: not told', meta: { acme_ca_revoked: true, related_acme_local_only: 7 } }
    expect(localOnlyRevocationWarning(res, t)).toBe(res.message)
  })

  it('stays silent when the CA was told', () => {
    expect(localOnlyRevocationWarning({ message: 'ok', meta: { acme_ca_revoked: true } }, t)).toBeNull()
  })
})
