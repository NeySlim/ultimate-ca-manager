/**
 * FIPS mode (#399) as the SSH and deploy forms read it: the flag comes from
 * the effective policy, and Ed25519 leaves the SSH key choices.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const getEffective = vi.fn()
vi.mock('../../services', () => ({ policiesService: { getEffective: (...a) => getEffective(...a) } }))

import { sshKeyOptions, useFipsMode } from '../policyAlgorithms'

const OPTIONS = [
  { value: 'ed25519', label: 'Ed25519' },
  { value: 'rsa', label: 'RSA' },
  { value: 'ecdsa-p256', label: 'ECDSA P-256' },
]

describe('sshKeyOptions', () => {
  it('drops Ed25519 in FIPS mode only', () => {
    expect(sshKeyOptions(OPTIONS, true).map(o => o.value)).toEqual(['rsa', 'ecdsa-p256'])
    expect(sshKeyOptions(OPTIONS, false)).toEqual(OPTIONS)
  })
})

describe('useFipsMode', () => {
  beforeEach(() => { getEffective.mockReset() })

  it('is true when the effective policy says so', async () => {
    getEffective.mockResolvedValue({ data: { fips: true } })
    const { result } = renderHook(() => useFipsMode())
    await waitFor(() => expect(result.current).toBe(true))
  })

  it('is false without the flag', async () => {
    getEffective.mockResolvedValue({ data: { allowed_key_types: null } })
    const { result } = renderHook(() => useFipsMode())
    await waitFor(() => expect(getEffective).toHaveBeenCalled())
    expect(result.current).toBe(false)
  })

  it('is false when the lookup fails', async () => {
    getEffective.mockImplementation(() => { throw Object.assign(new Error('Forbidden'), { status: 403 }) })
    const { result } = renderHook(() => useFipsMode())
    await waitFor(() => expect(getEffective).toHaveBeenCalled())
    expect(result.current).toBe(false)
  })
})
