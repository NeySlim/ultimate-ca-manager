import { daysRemaining } from './utils'

/**
 * What a `days_remaining` value means.
 *
 * The server publishes a signed number of days, or `null` when the row has
 * no expiry date at all (see backend/utils/days_remaining.py). Every badge,
 * colour and threshold in the product was deciding that for itself, and they
 * had drifted: the certificate detail panel called `<= 0` expired while the
 * CSR page called `< 0` expired, and the CSR page additionally ran
 * `cert.days_remaining || 0`, which turned a missing expiry date into a
 * confident "0 days left".
 *
 * contracts/days_remaining_contract.json is the shared table, and
 * backend/tests/test_days_remaining_contract.py holds the server to the
 * other half of it.
 */

/** Days inside which a certificate counts as expiring (backend EXPIRY_WINDOW_DAYS). */
export const EXPIRY_WINDOW_DAYS = 30

/**
 * @param {number|null|undefined} daysRemaining
 * @param {number} [windowDays] days inside which an entry is expiring
 * @returns {'none'|'expired'|'expiring'|'valid'}
 */
export function expiryBucket(daysRemaining, windowDays = EXPIRY_WINDOW_DAYS) {
  if (daysRemaining === null || daysRemaining === undefined) return 'none'
  const days = Number(daysRemaining)
  if (!Number.isFinite(days)) return 'none'
  if (days <= 0) return 'expired'
  if (days <= windowDays) return 'expiring'
  return 'valid'
}

/** Whether the row carries an expiry date the UI can talk about at all. */
export function hasExpiry(daysRemaining) {
  return expiryBucket(daysRemaining) !== 'none'
}

/** Badge variant for a bucket, the one mapping the pages shared by eye. */
export function expiryVariant(daysRemaining) {
  switch (expiryBucket(daysRemaining)) {
    case 'expired':
      return 'danger'
    case 'expiring':
      return 'warning'
    case 'valid':
      return 'success'
    default:
      return 'secondary'
  }
}

/** Whole days since expiry, for the "expired N days ago" wording. */
export function daysSinceExpiry(daysRemaining) {
  return expiryBucket(daysRemaining) === 'expired'
    ? Math.abs(Number(daysRemaining))
    : 0
}

/** Days ahead the trust store page and its export filter call an entry expiring. */
export const TRUST_STORE_EXPIRY_WINDOW_DAYS = 90

/**
 * The trust store page's state for an entry's `not_after`, on the shared
 * rounding (lib/utils daysRemaining); an entry with no date lists as valid.
 */
export function trustStoreExpiryStatus(notAfter) {
  const bucket = expiryBucket(daysRemaining(notAfter), TRUST_STORE_EXPIRY_WINDOW_DAYS)
  return bucket === 'none' ? 'valid' : bucket
}
