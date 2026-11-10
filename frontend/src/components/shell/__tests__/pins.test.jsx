/** Pins: stored with the server preferences, capped at three, hidden (not erased) when the right goes. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { canFor } from './shellTestUtils'

const updatePreferences = vi.hoisted(() => vi.fn().mockResolvedValue({}))
vi.mock('../../../services/account.service', () => ({ accountService: { updatePreferences } }))

import { visiblePins, togglePinList, usePins, MAX_PINS } from '../pins'
import { applyServerPreferences, setAuthenticated } from '../../../stores/userPreferencesStore'

const admin = canFor(['*'])

describe('visiblePins', () => {
  it('keeps order and drops unknown, unpinnable, duplicate and non-string ids', () => {
    expect(visiblePins(['audit', 'nope', 'dashboard', 'certificates', 'audit', 7, 'users'], admin))
      .toEqual(['audit', 'users'])
  })

  it('hides a pin whose right was withdrawn, without an error', () => {
    const viewer = canFor([])
    expect(visiblePins(['audit', 'templates'], viewer)).toEqual(['templates'])
    expect(visiblePins(['audit', 'templates'], canFor(['read:audit']))).toEqual(['audit', 'templates'])
  })

  it('never shows more than three, and tolerates a missing or malformed value', () => {
    expect(visiblePins(['audit', 'users', 'hsm', 'rbac'], admin)).toHaveLength(MAX_PINS)
    expect(visiblePins(undefined, admin)).toEqual([])
    expect(visiblePins('audit', admin)).toEqual([])
  })
})

describe('togglePinList', () => {
  it('adds at the end, removes in place, and refuses a fourth', () => {
    expect(togglePinList(['a'], 'b')).toEqual(['a', 'b'])
    expect(togglePinList(['a', 'b', 'c'], 'b')).toEqual(['a', 'c'])
    expect(togglePinList(['a', 'b', 'c'], 'd')).toBeNull()
  })
})

describe('usePins against the server preferences', () => {
  beforeEach(() => {
    updatePreferences.mockClear()
    setAuthenticated(false)
    setAuthenticated(true)
  })

  it('reads the pins the server sent', () => {
    applyServerPreferences({ pins: ['audit', 'users'], language: 'fr' })
    const { result } = renderHook(() => usePins(admin))
    expect(result.current.pins).toEqual(['audit', 'users'])
  })

  it('follows a later server copy', () => {
    applyServerPreferences({ pins: [] })
    const { result } = renderHook(() => usePins(admin))
    act(() => applyServerPreferences({ pins: ['hsm'] }))
    expect(result.current.pins).toEqual(['hsm'])
  })

  it('persists a new pin with the other preferences in one PUT', async () => {
    applyServerPreferences({ pins: ['audit'], language: 'fr' })
    const { result } = renderHook(() => usePins(admin))
    let ok
    await act(async () => { ok = result.current.toggle('users') })
    expect(ok).toBe(true)
    expect(updatePreferences).toHaveBeenCalledWith({ pins: ['audit', 'users'], language: 'fr' })
    expect(result.current.pins).toEqual(['audit', 'users'])
  })

  it('refuses a fourth pin without writing', async () => {
    applyServerPreferences({ pins: ['audit', 'users', 'hsm'] })
    const { result } = renderHook(() => usePins(admin))
    let ok
    await act(async () => { ok = result.current.toggle('rbac') })
    expect(ok).toBe(false)
    expect(updatePreferences).not.toHaveBeenCalled()
    expect(result.current.pins).toEqual(['audit', 'users', 'hsm'])
  })

  it('writes only visible pins, so a withdrawn right never blocks a slot', async () => {
    applyServerPreferences({ pins: ['audit', 'users', 'hsm'] })
    const { result } = renderHook(() => usePins(canFor(['read:hsm'])))
    expect(result.current.pins).toEqual(['hsm'])
    await act(async () => { result.current.toggle('tsa') })
    expect(updatePreferences).toHaveBeenCalledWith({ pins: ['hsm', 'tsa'] })
  })
})
