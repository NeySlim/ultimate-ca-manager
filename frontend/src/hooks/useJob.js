/**
 * useJob - follow a background job (backup, restore, audit verification) until it ends.
 *
 * follow(job) polls the job and resolves with it once final; resume(kind) picks up the
 * active job of that kind after a reload; cancel() asks the server to stop it.
 */
import { useState, useCallback, useRef, useEffect } from 'react'
import jobsService, { isFinalJob } from '../services/jobs.service'

export const JOB_POLL_MS = 1000

const unwrap = (response) => response?.data || response

export function useJob({ interval = JOB_POLL_MS } = {}) {
  const [job, setJob] = useState(null)
  const timer = useRef(null)
  const alive = useRef(true)
  const current = useRef(null)

  // Leaving the page stops the polling; the job itself goes on on the server
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      clearTimeout(timer.current)
    }
  }, [])

  const show = useCallback((next) => {
    current.current = next
    setJob(next)
  }, [])

  const follow = useCallback((initial) => new Promise((resolve, reject) => {
    clearTimeout(timer.current)
    show(initial)
    const step = (seen) => {
      if (!alive.current) return
      if (isFinalJob(seen)) {
        resolve(seen)
        return
      }
      timer.current = setTimeout(async () => {
        try {
          const next = unwrap(await jobsService.get(seen.id))
          if (!alive.current) return
          show(next)
          step(next)
        } catch (error) {
          reject(error)
        }
      }, interval)
    }
    step(initial)
  }), [interval, show])

  const resume = useCallback(async (kind) => {
    const listed = unwrap(await jobsService.list({ kind, state: 'active', limit: 1 }))
    const active = Array.isArray(listed) ? listed[0] : null
    return active ? follow(active) : null
  }, [follow])

  const cancel = useCallback(async () => {
    const target = current.current
    if (!target || isFinalJob(target)) return
    const next = unwrap(await jobsService.cancel(target.id))
    if (alive.current && next && !isFinalJob(current.current)) show(next)
  }, [show])

  const clear = useCallback(() => {
    clearTimeout(timer.current)
    show(null)
  }, [show])

  return { job, running: !!job && !isFinalJob(job), follow, resume, cancel, clear }
}
