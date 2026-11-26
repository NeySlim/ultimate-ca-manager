/**
 * useAccountProof: the password of an account that has one, else its authenticator
 * code; cancelling sends nothing; neither leaves the server to refuse with its reason.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ getProfile: vi.fn(), showPrompt: vi.fn() }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))
vi.mock('../../contexts', () => ({ useNotification: () => ({ showPrompt: mocks.showPrompt }) }))
vi.mock('../../services', () => ({ accountService: { getProfile: mocks.getProfile } }))

import { useAccountProof } from '../useAccountProof'

const ask = () => renderHook(() => useAccountProof()).result.current()

describe('useAccountProof', () => {
  beforeEach(() => { mocks.getProfile.mockReset(); mocks.showPrompt.mockReset() })

  it('asks the password of a local account', async () => {
    mocks.getProfile.mockResolvedValue({ data: { has_local_password: true, two_factor_enabled: true } })
    mocks.showPrompt.mockResolvedValue('s3cret')
    expect(await ask()).toEqual({ password: 's3cret' })
    expect(mocks.showPrompt).toHaveBeenCalledWith('account.confirmWithPassword', expect.objectContaining({ type: 'password' }))
  })

  it('asks the code of an account without a password', async () => {
    mocks.getProfile.mockResolvedValue({ data: { has_local_password: false, two_factor_enabled: true } })
    mocks.showPrompt.mockResolvedValue('123456')
    expect(await ask()).toEqual({ code: '123456' })
    expect(mocks.showPrompt).toHaveBeenCalledWith('account.confirmWithCode', expect.anything())
  })

  it('sends nothing once cancelled', async () => {
    mocks.getProfile.mockResolvedValue({ data: { has_local_password: true } })
    mocks.showPrompt.mockResolvedValue(null)
    expect(await ask()).toBeNull()
  })

  it('asks nothing of an account with neither, for the server to refuse', async () => {
    mocks.getProfile.mockResolvedValue({ data: { has_local_password: false, two_factor_enabled: false } })
    expect(await ask()).toEqual({})
    expect(mocks.showPrompt).not.toHaveBeenCalled()
  })

  it('asks the password when the profile cannot be read', async () => {
    mocks.getProfile.mockRejectedValue(new Error('offline'))
    mocks.showPrompt.mockResolvedValue('pw')
    expect(await ask()).toEqual({ password: 'pw' })
  })
})
