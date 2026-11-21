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
import { useJob, JOB_POLL_MS, JOB_POLL_RETRIES } from '../useJob'

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

  it.each([0, 502, 503])('polls again after a %s, then gives up with the job last seen', async (status) => {
    const lost = Object.assign(new Error('lost'), { status })
    jobsService.get.mockResolvedValueOnce({ data: job('running', { phase: 'applying' }) })
      .mockRejectedValueOnce(lost)
      .mockResolvedValueOnce({ data: job('running', { phase: 'applying' }) })
      .mockRejectedValue(lost)
    const { result } = renderHook(() => useJob())
    let failure
    act(() => { result.current.follow(job('pending')).catch((e) => { failure = e }) })
    await tick(JOB_POLL_MS * 3)
    expect(failure).toBeUndefined()  // one error between two answers: still followed
    await tick(JOB_POLL_MS * (JOB_POLL_RETRIES + 1))
    expect(failure.status).toBe(status)
    expect(failure.job.phase).toBe('applying')
    expect(jobsService.get).toHaveBeenCalledTimes(3 + JOB_POLL_RETRIES + 1)
  })

  it('gives up at once when the caller says so', async () => {
    jobsService.get.mockRejectedValue(Object.assign(new Error('gone'), { status: 503 }))
    const { result } = renderHook(() => useJob())
    let failure
    act(() => {
      result.current.follow(job('running'), { giveUp: (e) => e.status === 503 })
        .catch((e) => { failure = e })
    })
    await tick(JOB_POLL_MS)
    expect(failure.status).toBe(503)
    expect(jobsService.get).toHaveBeenCalledTimes(1)
  })

  it('never retries a refusal', async () => {
    jobsService.get.mockRejectedValue(Object.assign(new Error('nope'), { status: 401 }))
    const { result } = renderHook(() => useJob())
    let failure
    act(() => { result.current.follow(job('running')).catch((e) => { failure = e }) })
    await tick(JOB_POLL_MS)
    expect(failure.status).toBe(401)
    expect(jobsService.get).toHaveBeenCalledTimes(1)
  })

  it('tells a 202 job from a finished answer', () => {
    expect(acceptedJob({ data: { job: job('running') } }).id).toBe('j1')
    expect(acceptedJob({ data: { valid: true } })).toBeNull()
  })
})

describe('jobPercent', () => {
  it('is null while the total is unknown, then a whole percentage, never above 100', async () => {
    const { jobPercent } = await import('../useJob')
    expect(jobPercent(undefined)).toBeNull()
    expect(jobPercent({ done: null, total: null })).toBeNull()
    expect(jobPercent({ done: 0, total: 255010 })).toBe(0)
    expect(jobPercent({ done: 127505, total: 255010 })).toBe(50)
    expect(jobPercent({ done: 255009, total: 255010 })).toBe(99)
    expect(jobPercent({ done: 255010, total: 255010 })).toBe(100)
    expect(jobPercent({ done: 300000, total: 255010 })).toBe(100)
  })
})
