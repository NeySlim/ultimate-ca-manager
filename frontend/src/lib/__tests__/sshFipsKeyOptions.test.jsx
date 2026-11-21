/**
 * FIPS mode (#399) as the SSH and deploy forms read it: the flag comes from
 * the effective policy, and Ed25519 leaves the SSH key choices.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const getEffective = vi.fn()
vi.mock('../../services', () => ({ policiesService: { getEffective: (...a) => getEffective(...a) } }))

import { sshKeyOptions, useEffectiveAlgorithms, useFipsMode, useKeyPlatform } from '../policyAlgorithms'

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

  it('keeps Ed25519 in FIPS mode when the server module approves it', () => {
    expect(sshKeyOptions(OPTIONS, true, ['EC-P256', 'ED25519'])).toEqual(OPTIONS)
    expect(sshKeyOptions(OPTIONS, true, ['EC-P256', 'ML-DSA-65']).map(o => o.value)).toEqual(['rsa', 'ecdsa-p256'])
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

describe('ML-DSA on this build', () => {
  beforeEach(() => { getEffective.mockReset() })

  it.each([
    ['useKeyPlatform', () => useKeyPlatform()],
    ['useEffectiveAlgorithms', () => useEffectiveAlgorithms({ caId: 1 })],
  ])('%s reads ml_dsa: false as no ML-DSA', async (_name, hook) => {
    getEffective.mockResolvedValue({ data: { ml_dsa: false } })
    const { result } = renderHook(hook)
    await waitFor(() => expect(result.current.mldsa).toBe(false))
  })

  it.each([
    ['useKeyPlatform', () => useKeyPlatform()],
    ['useEffectiveAlgorithms', () => useEffectiveAlgorithms({ caId: 1 })],
  ])('%s offers ML-DSA when a server does not say', async (_name, hook) => {
    getEffective.mockResolvedValue({ data: { allowed_key_types: null } })
    const { result } = renderHook(hook)
    await waitFor(() => expect(getEffective).toHaveBeenCalled())
    await waitFor(() => expect(result.current.allowedKeyTypes ?? null).toBe(null))
    expect(result.current.mldsa).toBe(true)
  })
})

describe('What the FIPS module approves', () => {
  beforeEach(() => { getEffective.mockReset() })

  it.each([
    ['useKeyPlatform', () => useKeyPlatform()],
    ['useEffectiveAlgorithms', () => useEffectiveAlgorithms({ caId: 1 })],
  ])('%s reads fips_key_types', async (_name, hook) => {
    getEffective.mockResolvedValue({ data: { fips: true, fips_key_types: ['EC-P256', 'ML-DSA-65'] } })
    const { result } = renderHook(hook)
    await waitFor(() => expect(result.current.fipsKeys).toEqual(['EC-P256', 'ML-DSA-65']))
    expect(result.current.fips).toBe(true)
  })

  it.each([
    ['useKeyPlatform', () => useKeyPlatform()],
    ['useEffectiveAlgorithms', () => useEffectiveAlgorithms({ caId: 1 })],
  ])('%s has no list when the server gives none', async (_name, hook) => {
    getEffective.mockResolvedValue({ data: { fips: true } })
    const { result } = renderHook(hook)
    await waitFor(() => expect(result.current.fips).toBe(true))
    expect(result.current.fipsKeys).toBeNull()
  })
})
