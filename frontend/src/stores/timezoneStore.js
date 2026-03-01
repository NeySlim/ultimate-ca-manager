/**
 * Timezone Store - lightweight global state for app timezone
 * 
 * Not a React context — works in plain JS utility functions.
 * Set by AuthContext on session verify, read by formatDate utilities.
 */

let _timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

export function getAppTimezone() {
  return _timezone
}

export function setAppTimezone(tz) {
  if (tz && typeof tz === 'string') {
    try {
      Intl.DateTimeFormat(undefined, { timeZone: tz })
      _timezone = tz
    } catch {
      console.warn(`Invalid timezone "${tz}", keeping current: ${_timezone}`)
    }
  }
}
