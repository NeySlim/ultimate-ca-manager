/**
 * What the status bar sums up, each part read only for a role that may read it: the pending
 * approvals (read:approvals), the interventions of the overview's queue (read:dashboard, its
 * « À traiter » figure) and the background jobs running (backup and restore for admin:system,
 * the audit chain check for read:audit). Read again on a data change and once a minute; with
 * nothing readable, nothing is asked. A part not read yet, or that failed, stays null.
 */
import { useEffect, useState } from 'react'
import { approvalsService } from '../../services/approvals.service'
import { overviewService } from '../../services/overview.service'
import jobsService from '../../services/jobs.service'
import { queueSplit } from '../../lib/overviewQueue'

export const ACTIVITY_POLL_MS = 60000
const unwrap = (res) => res?.data ?? res

export function useActivity(can) {
  const has = (p) => !!can?.hasPermission?.(p)
  const approvals = has('read:approvals')
  const queue = has('read:dashboard')
  const jobs = has('admin:system') || has('read:audit')
  const [state, setState] = useState({ approvals: null, queue: null, jobs: null })

  useEffect(() => {
    if (!approvals && !queue && !jobs) return undefined
    let alive = true
    const set = (patch) => { if (alive) setState((s) => ({ ...s, ...patch })) }
    // The first read joins one the page opening alongside has started; the later ones read afresh
    const load = (opening) => {
      if (approvals) {
        approvalsService.getStats()
          .then((res) => { const n = Number(unwrap(res)?.pending); if (Number.isFinite(n)) set({ approvals: n }) })
          .catch(() => {})
      }
      if (queue) {
        overviewService.getQueue(undefined, { reuse: opening === true })
          .then((res) => { const { act } = queueSplit(unwrap(res)); if (act !== null) set({ queue: act }) })
          .catch(() => {})
      }
      if (jobs) {
        jobsService.list({ state: 'active', limit: 10 })
          .then((res) => { const list = unwrap(res); if (Array.isArray(list)) set({ jobs: list }) })
          .catch(() => {})
      }
    }
    load(true)
    const refresh = () => load(false)
    const timer = setInterval(refresh, ACTIVITY_POLL_MS)
    window.addEventListener('ucm:data-changed', refresh)
    return () => { alive = false; clearInterval(timer); window.removeEventListener('ucm:data-changed', refresh) }
  }, [approvals, queue, jobs])

  const readable = approvals || queue || jobs
  const known = (!approvals || state.approvals !== null) && (!queue || state.queue !== null) && (!jobs || state.jobs !== null)
  return {
    readable,
    approvals: approvals ? state.approvals : null,
    queue: queue ? state.queue : null,
    jobs: jobs ? state.jobs || [] : [],
    // Everything readable was read, and there is nothing in it
    calm: readable && known && !state.approvals && !state.queue && !(state.jobs || []).length,
  }
}
