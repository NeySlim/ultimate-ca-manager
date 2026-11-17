/**
 * useRestoreJob - follow a restore that runs as a background job, across its own sign-out.
 *
 * A restore that commits revokes every session, the page's own: polling then gets a 401,
 * which means "probably committed, sign in again", never a failure. The job id is kept in
 * this browser until its report has been shown, so the report appears after the sign-in.
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { useJob } from '../../hooks'
import jobsService, { acceptedJob, isFinalJob } from '../../services/jobs.service'

export const PENDING_RESTORE_KEY = 'ucm.restore.pendingJob'

const unwrap = (response) => response?.data || response

function remember(id) {
  try { window.localStorage.setItem(PENDING_RESTORE_KEY, id) } catch { /* private window */ }
}

function forget() {
  try { window.localStorage.removeItem(PENDING_RESTORE_KEY) } catch { /* private window */ }
}

export function pendingRestore() {
  try { return window.localStorage.getItem(PENDING_RESTORE_KEY) } catch { return null }
}

/**
 * onReport(data): the restore succeeded, its report; onFailure(job): it ended otherwise.
 */
export function useRestoreJob({ enabled = true, onReport, onFailure } = {}) {
  const { job, running, follow, cancel } = useJob()
  const [signInNeeded, setSignInNeeded] = useState(false)
  const handlers = useRef({ onReport, onFailure })
  handlers.current = { onReport, onFailure }

  const conclude = useCallback((final) => {
    forget()
    if (final.state === 'succeeded') handlers.current.onReport?.(final.result?.data || {})
    else handlers.current.onFailure?.(final)
  }, [])

  const track = useCallback(async (started) => {
    remember(started.id)
    try {
      conclude(await follow(started))
    } catch (error) {
      // The restore revoked this session: the report waits for the next sign-in
      if (error?.status === 401) setSignInNeeded(true)
      else throw error
    }
  }, [follow, conclude])

  // The route's answer: a 202 is followed here; a finished restore answered itself (false)
  const start = useCallback(async (response) => {
    const started = acceptedJob(response)
    if (!started) return false
    await track(started)
    return true
  }, [track])

  // After a reload or a sign-in: the restore this browser followed, else one still running
  useEffect(() => {
    if (!enabled) return undefined
    let gone = false
    const id = pendingRestore()
    const pick = id
      ? jobsService.get(id).then(unwrap).catch((error) => {
        if (error?.status === 404) forget()
        return null
      })
      : jobsService.list({ kind: 'restore', state: 'active', limit: 1 }).then((listed) => {
        const active = unwrap(listed)
        return Array.isArray(active) ? active[0] || null : null
      }).catch(() => null)
    pick.then((seen) => {
      if (gone || !seen) return
      if (isFinalJob(seen)) conclude(seen)
      else track(seen).catch(() => {})
    })
    return () => { gone = true }
  }, [enabled]) // eslint-disable-line react-hooks/exhaustive-deps

  return { job, running, signInNeeded, start, cancel }
}

export default useRestoreJob
