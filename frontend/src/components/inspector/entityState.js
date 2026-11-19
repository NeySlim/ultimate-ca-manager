import { certificateState } from '../../lib/certificateState'

/** The state pill of an opened object once it is loaded; null for a type that shows none. */
export function entityState(type, data, t) {
  if (!data || (type !== 'certificate' && type !== 'user_certificate')) return null
  if (type === 'user_certificate' && !data.status && data.revoked === undefined) return null
  return certificateState(data, t)
}
