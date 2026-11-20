/**
 * One page at a time may hold work that leaving would lose. It registers a guard that
 * resolves true to leave; navigation that does not go through a link asks it here.
 */
let guard = null

export function setLeaveGuard(fn) {
  guard = fn
  return () => { if (guard === fn) guard = null }
}

/** Runs `go` now when nothing is pending, else once the guard agrees. */
export function whenLeaving(go) {
  if (!guard) return go()
  Promise.resolve(guard()).then((ok) => { if (ok) go() })
  return undefined
}
