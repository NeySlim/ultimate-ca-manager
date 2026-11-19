/**
 * CAs page: the state pill of an authority and the quiet marks that follow it
 * (offline, HSM, no key, revoked upstream, cross-signed, no known parent).
 * Each one is an icon and a word; the colour only repeats them.
 */
import { CheckCircle, Clock, Warning, Prohibit, Hourglass, Lock, Cpu, Key, LinkSimple, LinkBreak } from '@phosphor-icons/react'
import { StatusPill, RowMark } from '../../components/list'
import { cn, formatDate } from '../../lib/utils'
import { holdsNoKey, needsKeyImport } from '../../lib/caSelection'
import { caState } from './caTree'

const STATES = {
  active: { tone: 'good', icon: CheckCircle, key: 'common.active' },
  expiring: { tone: 'warn', icon: Clock, key: 'cas.state.expiring' },
  expired: { tone: 'bad', icon: Warning, key: 'common.expired' },
  revoked: { tone: 'bad', icon: Prohibit, key: 'common.revoked' },
  pending: { tone: 'warn', icon: Hourglass, key: 'cas.awaitingCertificate' },
}

export function CAStatePill({ ca, t }) {
  const state = caState(ca)
  const { tone, icon, key } = STATES[state]
  const end = ca.valid_to || ca.not_after
  return (
    <StatusPill
      tone={tone}
      icon={icon}
      label={t(key)}
      data-state={state}
      title={end && state !== 'pending' ? formatDate(end, { time: false }) : undefined}
    />
  )
}

/** The marks an authority carries, as [{ id, icon, label, title, tone }]. */
function caMarks(ca, t, { orphan = false } = {}) {
  const marks = []
  if (ca.offline) {
    const mode = ca.offline_mode === 'file_exported' ? t('cas.offlineFileExported') : t('cas.offlinePasswordProtected')
    marks.push({ id: 'offline', icon: Lock, label: t('cas.offline'), title: ca.offline_reason || mode })
  }
  if (ca.uses_hsm) {
    const where = [ca.hsm_provider_name, ca.hsm_key_label].filter(Boolean).join(' / ')
    marks.push({ id: 'hsm', icon: Cpu, label: 'HSM', title: where || t('cas.detail.hsmBacked') })
  }
  if (holdsNoKey(ca)) {
    const expected = needsKeyImport(ca)
    marks.push({
      id: 'nokey', icon: Key, tone: expected ? 'warn' : undefined,
      label: t(expected ? 'cas.certificateOnly' : 'cas.noPrivateKey'),
      title: t(expected ? 'cas.certificateOnlyBanner' : 'cas.noPrivateKeyBanner'),
    })
  }
  if (ca.revoked_in_chain && !ca.revoked) {
    marks.push({ id: 'chain', icon: Warning, tone: 'bad', label: t('cas.chainRevoked'), title: t('cas.chainRevokedBanner') })
  }
  if (ca.cross_certificate_count > 0) {
    marks.push({ id: 'cross', icon: LinkSimple, cross: true, label: t('crossCerts.badge', { count: ca.cross_certificate_count }) })
  }
  if (orphan) marks.push({ id: 'orphan', icon: LinkBreak, tone: 'warn', label: t('cas.tree.orphan') })
  return marks
}

/** `compact` keeps the icons and reads the labels out; otherwise each mark is a bordered chip. */
export function CAMarks({ ca, t, orphan, compact = false }) {
  const marks = caMarks(ca, t, { orphan })
  if (compact) {
    return marks.map((m) => (
      <RowMark key={m.id} icon={m.icon} tone={m.tone === 'warn' ? 'warn' : undefined} label={m.label} data-mark={m.id} />
    ))
  }
  return marks.map(({ id, icon: Icon, label, title, tone, cross }) => (
    <span key={id} className={cn('ca-chip', tone && `is-${tone}`, cross && 'is-cross')} title={title} data-mark={id}>
      <Icon aria-hidden="true" />
      {label}
    </span>
  ))
}
