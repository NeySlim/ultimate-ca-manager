import { describe, it, expect } from 'vitest'
import { actionDetail } from '../actionDetails'

describe('the English detail of a SCEP challenge event in the user\'s language', () => {
  const t = (key, opts) => `${key}:${opts.name}`
  it('words the read and the regeneration of a CA\'s challenge', () => {
    expect(actionDetail('Read SCEP challenge password for CA: IoT CA', t)).toBe('audit.actionDetails.scepChallengeRead:IoT CA')
    expect(actionDetail('Regenerated SCEP challenge password for CA: R1', t)).toBe('audit.actionDetails.scepChallengeRegenerate:R1')
  })
  it('keeps any other detail as written', () => {
    expect(actionDetail('Revoked certificate 12', t)).toBe('Revoked certificate 12')
    expect(actionDetail(null, t)).toBe(null)
  })
})
