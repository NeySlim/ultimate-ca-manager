/**
 * The last gesture of the user (key, click, wheel, touch) in any tab of this browser: the tabs
 * share one session, so its inactivity lock counts the gestures of all of them, never a poll.
 */
const KEY = 'ucm_last_gesture'
// A gesture is written at most this often: the idle time is counted in minutes
const WRITE_EVERY_MS = 5000
let written = 0

export function noteGesture(now = Date.now()) {
  if (Math.abs(now - written) < WRITE_EVERY_MS) return
  written = now
  try { localStorage.setItem(KEY, String(now)) } catch { /* this tab's own count still holds */ }
}

export function lastSharedGesture() {
  try {
    const value = Number(localStorage.getItem(KEY))
    return Number.isFinite(value) && value > 0 ? value : 0
  } catch {
    return 0
  }
}
