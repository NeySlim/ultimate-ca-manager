/**
 * One poll of /api/v2/health shared by the status bar, the HA banner and the write guard:
 * started by the first subscriber, stopped with the last. What the API omits stays unknown.
 */
import { useEffect, useState } from 'react'

export const HEALTH_URL = '/api/v2/health'
export const POLL_MS = 30000

// null until the first answer; false when the service did not answer
let current = null
let timer = null
let ctrl = null
const listeners = new Set()

function publish(value) {
  current = value
  for (const cb of listeners) cb(value)
}

async function load() {
  // A late answer must not write after the last subscriber left or after the next poll started
  ctrl?.abort()
  const mine = new AbortController()
  ctrl = mine
  try {
    const res = await fetch(HEALTH_URL, { signal: mine.signal, cache: 'no-store' })
    if (!res.ok) throw new Error(String(res.status))
    const body = await res.json()
    if (!mine.signal.aborted) publish(body && typeof body === 'object' ? body : false)
  } catch {
    if (!mine.signal.aborted) publish(false)
  }
}

function subscribe(cb) {
  listeners.add(cb)
  if (listeners.size === 1) {
    load()
    timer = setInterval(load, POLL_MS)
  }
  return () => {
    listeners.delete(cb)
    if (listeners.size === 0) {
      clearInterval(timer)
      timer = null
      ctrl?.abort()
      ctrl = null
      current = null
    }
  }
}

export function useHealth() {
  const [health, setHealth] = useState(current)
  useEffect(() => {
    setHealth(current)
    return subscribe(setHealth)
  }, [])
  return health
}

/**
 * What the HA part of /health says, outside HA mode null. `maintenance`: the cluster
 * refuses every write until it ends (the server's own rule); `stale`: nodes registered
 * but silent; `leaderless`: no live leader, scheduled work waits for one.
 */
export function haState(health) {
  if (!health || !health.ha) return null
  const cluster = health.cluster && typeof health.cluster === 'object' ? health.cluster : null
  const nodes = typeof cluster?.nodes === 'number' ? cluster.nodes : null
  const stale = typeof cluster?.stale === 'number' ? cluster.stale : 0
  const maintenance = health.maintenance && typeof health.maintenance === 'object' ? health.maintenance : null
  return {
    node: health.node_id || null,
    leader: health.leader,
    leaderNode: cluster ? cluster.leader_node_id || null : undefined,
    nodes,
    stale,
    leaderless: !!cluster && !cluster.leader_node_id,
    maintenance,
  }
}

// Ids of the banner sentences that say why a control is disabled
export const WRITES_NOTE_ID = 'shell-writes-note'

/** Writes suspended while the cluster is in maintenance: { suspended, noteId }. */
export function useWriteGuard() {
  const ha = haState(useHealth())
  const suspended = !!ha?.maintenance
  return { suspended, noteId: suspended ? WRITES_NOTE_ID : undefined }
}

/** Props of a write control under the guard: disabled with the banner's reason, else unchanged. */
export function guardProps(guard, disabled) {
  if (!guard?.suspended) return { disabled }
  return { disabled: true, 'aria-describedby': guard.noteId, 'data-blocked': 'writes' }
}

// Test seam: forget the shared state between tests
export function resetHealthForTests() {
  clearInterval(timer)
  timer = null
  ctrl?.abort()
  ctrl = null
  current = null
  listeners.clear()
}
