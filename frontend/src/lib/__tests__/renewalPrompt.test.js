import { describe, it, expect, vi } from 'vitest'
import { askRenewal, originalDurationDays } from '../renewalPrompt'

const t = (key, vars) => (vars ? `${key}:${vars.min}-${vars.max}` : key)
const cert27 = { id: 1, valid_from: '2026-10-01T00:00:00Z', valid_to: '2026-10-28T00:00:00Z' }

function deps(answer) {
  return {
    showPrompt: vi.fn().mockResolvedValue(answer),
    showConfirm: vi.fn().mockResolvedValue(true),
    showError: vi.fn(),
    t,
  }
}

describe('askRenewal', () => {
  it('offers the original duration as the default', async () => {
    const d = deps('27')
    await askRenewal(cert27, d)
    expect(d.showPrompt.mock.calls[0][1]).toMatchObject({ type: 'number', defaultValue: '27' })
  })

  it('an unchanged default is not sent, so the server keeps the exact duration', async () => {
    expect(await askRenewal(cert27, deps('27'))).toEqual({})
    expect(await askRenewal(cert27, deps(' '))).toEqual({})
  })

  it('a new duration is sent as validity_days', async () => {
    expect(await askRenewal(cert27, deps('90'))).toEqual({ validity_days: 90 })
  })

  it('cancelling renews nothing', async () => {
    expect(await askRenewal(cert27, deps(null))).toBeNull()
  })

  it.each(['0', '3651', '1.5', '-3', 'abc'])('refuses %s with the bounds', async (bad) => {
    const d = deps(bad)
    expect(await askRenewal(cert27, d)).toBeNull()
    expect(d.showError).toHaveBeenCalledWith('certificates.renewDaysInvalid:1-3650')
  })

  it('a Microsoft CA certificate is only confirmed, never given a duration', async () => {
    const d = deps('90')
    expect(await askRenewal({ ...cert27, source: 'msca' }, d)).toEqual({})
    expect(d.showPrompt).not.toHaveBeenCalled()
    d.showConfirm.mockResolvedValue(false)
    expect(await askRenewal({ ...cert27, source: 'msca' }, d)).toBeNull()
  })

  it('without dates there is no default to offer', () => {
    expect(originalDurationDays({})).toBeNull()
  })
})
