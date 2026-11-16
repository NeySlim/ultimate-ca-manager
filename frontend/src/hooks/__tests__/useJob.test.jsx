/**
 * useJob polls a background job until it ends, picks the active one up after a reload,
 * cancels it, and stops polling once the page is left.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

vi.mock('../../services/jobs.service', async (importOriginal) => {
  const real = await importOriginal()
  return { ...real, default: { get: vi.fn(), list: vi.fn(), cancel: vi.fn() } }
})

import jobsService from '../../services/jobs.service'
import { acceptedJob } from '../../services/jobs.service'
import { useJob, JOB_POLL_MS } from '../useJob'

const tick = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const job = (state, extra = {}) => ({ id: 'j1', kind: 'audit_verify', state, progress: { done: 0, total: 10 }, ...extra })

describe('useJob', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })
  afterEach(() => vi.useRealTimers())

  it('follows a job until it is final and resolves with it', async () => {
    jobsService.get
      .mockResolvedValueOnce({ data: job('running', { progress: { done: 4, total: 10 } }) })
      .mockResolvedValueOnce({ data: job('succeeded', { result: { code: 200, data: { valid: true } } }) })
    const { result } = renderHook(() => useJob())
    let done
    act(() => { result.current.follow(job('pending')).then((j) => { done = j }) })
    expect(result.current.running).toBe(true)
    await tick(JOB_POLL_MS)
    expect(result.current.job.progress.done).toBe(4)
    await tick(JOB_POLL_MS)
    expect(done.state).toBe('succeeded')
    expect(result.current.running).toBe(false)
    await tick(JOB_POLL_MS * 3)
    expect(jobsService.get).toHaveBeenCalledTimes(2)
  })

  it('resumes the active job of a kind after a reload, or nothing', async () => {
    jobsService.list.mockResolvedValueOnce({ data: [] })
    const { result } = renderHook(() => useJob())
    let none = 'unset'
    await act(async () => { none = await result.current.resume('audit_verify') })
    expect(none).toBeNull()
    expect(jobsService.list).toHaveBeenCalledWith({ kind: 'audit_verify', state: 'active', limit: 1 })

    jobsService.list.mockResolvedValueOnce({ data: [job('running')] })
    jobsService.get.mockResolvedValueOnce({ data: job('failed', { reason: 'executor_lost' }) })
    let resumed
    act(() => { result.current.resume('audit_verify').then((j) => { resumed = j }) })
    await tick(JOB_POLL_MS)
    expect(resumed.reason).toBe('executor_lost')
  })

  it('asks the server to cancel the job it follows', async () => {
    jobsService.get.mockResolvedValue({ data: job('running', { cancel_requested: true }) })
    jobsService.cancel.mockResolvedValueOnce({ data: job('running', { cancel_requested: true }) })
    const { result } = renderHook(() => useJob())
    act(() => { result.current.follow(job('running')) })
    await act(async () => { await result.current.cancel() })
    expect(jobsService.cancel).toHaveBeenCalledWith('j1')
    expect(result.current.job.cancel_requested).toBe(true)
  })

  it('stops polling once unmounted', async () => {
    jobsService.get.mockResolvedValue({ data: job('running') })
    const { result, unmount } = renderHook(() => useJob())
    act(() => { result.current.follow(job('running')) })
    unmount()
    await tick(JOB_POLL_MS * 5)
    expect(jobsService.get).not.toHaveBeenCalled()
  })

  it('tells a 202 job from a finished answer', () => {
    expect(acceptedJob({ data: { job: job('running') } }).id).toBe('j1')
    expect(acceptedJob({ data: { valid: true } })).toBeNull()
  })
})
