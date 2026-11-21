/** What the manual expiry check did: skipped (another HA node holds the run) or the alerts it sent. */
export function expiryCheckOutcome(data) {
  if (data?.status === 'skipped') return { skipped: true }
  const count = (data?.cert_expiring?.notified || 0) + (data?.crl_expiring?.notified || 0) + (data?.alerts_sent || 0)
  return { skipped: false, count }
}
