/**
 * useRestoreJob - follow a restore that runs as a background job, across its own sign-out.
 *
 * A restore that commits revokes every session, the page's own: polling then gets a 401,
 * which means "probably committed, sign in again", never a failure. The job id is kept in
 * this browser, under the account that followed it, until its report has been shown, so the
 * report appears after that account's sign-in.
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { useJob, isTransientError } from '../../hooks'
import jobsService, { acceptedJob, isFinalJob } from '../../services/jobs.service'

export const PENDING_RESTORE_KEY = 'ucm.restore.pendingJob'

const unwrap = (response) => response?.data || response

// Kept under the account that followed it: another account of this browser never sees it
function remember(id, account) {
  try {
    window.localStorage.setItem(PENDING_RESTORE_KEY, JSON.stringify({ id, account }))
  } catch { /* private window */ }
}

function forget() {
  try { window.localStorage.removeItem(PENDING_RESTORE_KEY) } catch { /* private window */ }
}

/** The restore job ``account`` followed in this browser; another account's is dropped. */
export function pendingRestore(account) {
  let kept = null
  try {
    const stored = window.localStorage.getItem(PENDING_RESTORE_KEY)
    if (stored === null) return null
    kept = JSON.parse(stored)
  } catch { /* unreadable: dropped below */ }
  if (kept && typeof kept.id === 'string' && account && kept.account === account) return kept.id
  forget()
  return null
}

// Phases from the commit on: the restore is validated, what follows signs every session out
// and asks a restart (no answer, 502, 503 for a while)
export const VALIDATED_PHASES = ['committed', 'sessions_revoked', 'session_files_removed',
  'caches_purged', 'crls_regenerated']
const validated = (job) => VALIDATED_PHASES.includes(job?.phase)
// From the start of the commit the server answers a cancellation 409
export const UNCANCELLABLE_PHASES = ['committing', ...VALIDATED_PHASES]

/**
 * onReport(data): the restore succeeded, its report; onFailure(job): it ended otherwise;
 * onLost(error): the job can no longer be followed and no commit was seen (no answer after
 * the retries, or any other error of the server): the end is unknown here.
 */
export function useRestoreJob({ enabled = true, account, onReport, onFailure, onLost } = {}) {
  const { job, running, follow, cancel, clear } = useJob()
  const [signInNeeded, setSignInNeeded] = useState(false)
  const handlers = useRef({ onReport, onFailure, onLost })
  handlers.current = { onReport, onFailure, onLost }

  const conclude = useCallback((final) => {
    forget()
    if (final.state === 'succeeded') handlers.current.onReport?.(final.result?.data || {})
    else handlers.current.onFailure?.(final)
  }, [])

  const track = useCallback(async (started) => {
    remember(started.id, account)
    // Past the commit, no answer is the restart the restore asked: not retried
    const restarting = (error, seen) => isTransientError(error) && validated(seen)
    try {
      conclude(await follow(started, { giveUp: restarting }))
    } catch (error) {
      // The restore revoked this session or restarts the service: the report waits for the
      // next sign-in. Before its commit, the end is unknown: said, the id kept for later
      if (error?.status === 401 || restarting(error, error?.job)) setSignInNeeded(true)
      else {
        clear()
        handlers.current.onLost?.(error)
      }
    }
  }, [follow, conclude, clear, account])

  // The route's answer: a 202 is followed here; a finished restore answered itself (false)
  const start = useCallback(async (response) => {
    const started = acceptedJob(response)
    if (!started) return false
    await track(started)
    return true
  }, [track])

  // After a reload or a sign-in: the restore this browser followed, else one still running
  useEffect(() => {
    if (!enabled || !account) return undefined
    let gone = false
    const id = pendingRestore(account)
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
      else track(seen)
    })
    return () => { gone = true }
  }, [enabled, account]) // eslint-disable-line react-hooks/exhaustive-deps

  return { job, running, signInNeeded, start, cancel }
}

export default useRestoreJob
