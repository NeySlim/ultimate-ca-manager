/** The mockup's badge() of a certificate and its expiry cell (tableView()). */
import { Pill } from '../../components/atelier'
import { formatDate } from '../../lib/utils'
import { relativeShort } from '../../lib/relativeTime'
import { STATES, stateOf } from './certState'

/** The state badge of a certificate (unknown states read « Inconnu »). */
export function CertBadge({ cert, t }) {
  const s = STATES[stateOf(cert)]
  if (!s) return <Pill label={t('common.unknown')} tone="muted" icon="help" />
  return <Pill label={t(s.key)} tone={s.tone} icon={s.icon} />
}

/** The expiry cell: the date, then what is left (« 3 j », « 1 a 4 mois », « Échu », « Révoqué »). */
export function ExpiryCell({ row, t }) {
  if (!row.valid_to) return <span className="expiry-cell">—</span>
  const state = stateOf(row)
  const lapsed = new Date(row.valid_to).getTime() <= Date.now()
  const left = state === 'revoked' ? t('common.revoked') : relativeShort(row.valid_to, t)
  return (
    <span className={state === 'expiring' ? 'expiry-cell warn' : 'expiry-cell'}>
      {formatDate(row.valid_to, { time: false })}
      <span className={lapsed && state !== 'revoked' ? 'remaining bad' : 'remaining muted'}>{left}</span>
    </span>
  )
}

