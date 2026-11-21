/**
 * The state pill of a certificate in the shell's inspector (the product's panels outside the
 * Certificates zone); the zone itself draws the mockup's badge (certificateRows.jsx).
 */
import { Info, Check, Clock, Warning, Prohibit } from '@phosphor-icons/react'

/** The one state a row shows: tone, icon and label of its pill. */
export function certificateState(row, t) {
  const status = row.revoked ? 'revoked' : row.status || 'unknown'
  return {
    valid: { tone: 'good', icon: Check, label: t('common.valid') },
    expiring: { tone: 'warn', icon: Clock, label: t('certificates.views.expiring') },
    expired: { tone: 'bad', icon: Warning, label: t('common.expired') },
    revoked: { tone: 'muted', icon: Prohibit, label: t('common.revoked') },
  }[status] || { tone: 'muted', icon: Info, label: t('common.unknown') }
}
