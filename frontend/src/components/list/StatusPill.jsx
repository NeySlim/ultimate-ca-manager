/**
 * State pill of the list template: an icon and a coloured label, no fill and no
 * animated dot. The icon and the word carry the state; the colour only repeats it.
 */
import { CheckCircle, Clock, Warning, Prohibit } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import './list.css'

const TONE_ICONS = { good: CheckCircle, warn: Clock, bad: Warning, muted: Prohibit }

/** @param {'good'|'warn'|'bad'|'muted'} tone */
export function StatusPill({ tone = 'muted', icon, label, className, ...props }) {
  const Icon = icon || TONE_ICONS[tone] || TONE_ICONS.muted
  return (
    <span className={cn('lv-pill', `is-${TONE_ICONS[tone] ? tone : 'muted'}`, className)} {...props}>
      <Icon aria-hidden="true" />
      {label}
    </span>
  )
}

/** Where a row comes from: a quiet label with its icon. */
export function SourceLabel({ icon: Icon, label, className, ...props }) {
  if (!label) return null
  return (
    <span className={cn('lv-source', className)} {...props}>
      {Icon && <Icon aria-hidden="true" />}
      {label}
    </span>
  )
}

/** The name that opens a row's detail: its click reaches the row, which opens it. */
export function EntityName({ icon: Icon, children, className, ...props }) {
  return (
    <button type="button" className={cn('lv-entity', className)} {...props}>
      {Icon && <Icon aria-hidden="true" />}
      {children}
    </button>
  )
}

/** A small sign after the name (key held, orphan...): its label is read and shown on hover. */
export function RowMark({ icon: Icon, label, tone, children, className, ...props }) {
  return (
    <span className={cn('lv-mark', tone && `is-${tone}`, className)} role="img" aria-label={label} title={label} {...props}>
      {Icon && <Icon aria-hidden="true" />}
      {children}
    </span>
  )
}

export default StatusPill
