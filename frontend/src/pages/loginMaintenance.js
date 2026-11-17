// A sign-in refused by a maintenance (a restore, until this node has restarted): tried again
// after its Retry-After, kept within these bounds
const RETRY_MIN_S = 2
const RETRY_MAX_S = 30
const RETRY_DEFAULT_S = 10

// No answer at all, or a proxy's answer for a node that is down: what a restart looks like
export const NO_ANSWER_RETRY_S = 5
export const NO_ANSWER_TRIES = 12
export const isNoAnswer = (error) =>
  [0, 502, 503, 504].includes(error?.status) && error?.data?.code !== 'maintenance'

// Known by its RFC 9457 extension member, never by its text
export const isMaintenanceRefusal = (error) => error?.status === 503 && error?.data?.code === 'maintenance'

export const isRestoreMaintenance = (error) =>
  ['restore', 'local_restore'].includes(error?.data?.maintenance?.reason)

export const maintenanceRetrySeconds = (error) => {
  const asked = Number.isFinite(error?.retryAfter) ? error.retryAfter : RETRY_DEFAULT_S
  return Math.min(RETRY_MAX_S, Math.max(RETRY_MIN_S, asked))
}
