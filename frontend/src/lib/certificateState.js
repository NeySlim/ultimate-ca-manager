/** The one state a certificate shows: tone, icon and label of its pill. */
import { Info, CheckCircle, Clock, Warning, Prohibit } from '@phosphor-icons/react'

export function certificateState(row, t) {
  const status = row.revoked ? 'revoked' : row.status || 'unknown'
  return {
    valid: { tone: 'good', icon: CheckCircle, label: t('common.valid') },
    expiring: { tone: 'warn', icon: Clock, label: t('certificates.views.expiring') },
    expired: { tone: 'bad', icon: Warning, label: t('common.expired') },
    revoked: { tone: 'muted', icon: Prohibit, label: t('common.revoked') },
  }[status] || { tone: 'muted', icon: Info, label: t('common.unknown') }
}
