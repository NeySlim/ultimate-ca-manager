/**
 * CAs page: the state badge of an authority and the chips that follow it (offline, HSM, no key,
 * revoked upstream, cross-signed, no known parent), as the mockup's caBadges() draws them: a
 * `badge` with its icon, then `chip`s. Each one is an icon and a word; the colour only repeats them.
 */
import { Icon } from '../../components/atelier'
import { formatDate } from '../../lib/utils'
import { caState, caMarks, CA_STATES } from './caTree'

export function CAStatePill({ ca, t }) {
  const state = caState(ca)
  const { tone, icon, key } = CA_STATES[state]
  const end = ca.valid_to || ca.not_after
  return (
    <span className={`badge ${tone}`} data-state={state} title={end && state !== 'pending' ? formatDate(end, { time: false }) : undefined}>
      <Icon name={icon} />{t(key)}
    </span>
  )
}

export function CAMarks({ ca, t, orphan }) {
  return caMarks(ca, t, { orphan }).map(({ id, icon, label, title, tone, cross }) => (
    <span key={id} data-testid={id === 'pq' ? 'post-quantum-badge' : undefined} className={['chip', tone, cross && 'cross'].filter(Boolean).join(' ')} title={title} data-mark={id}>
      <Icon name={icon} />{label}
    </span>
  ))
}
