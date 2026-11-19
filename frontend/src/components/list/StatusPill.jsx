/**
 * State pill of the list template: an icon and a coloured label, no fill and no
 * animated dot. The icon and the word carry the state; the colour only repeats it.
 */
import { useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
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

/**
 * The name that opens a row's detail: its click reaches the row, which opens it. A name
 * cut by an ellipsis shows whole in a tip on hover and on keyboard focus (Escape hides it).
 */
export function EntityName({ icon: Icon, children, className, ...props }) {
  const text = useRef(null)
  const tipId = useId()
  const [tip, setTip] = useState(null)
  const show = () => {
    const el = text.current
    if (!el || el.scrollWidth <= el.clientWidth) return
    const box = el.getBoundingClientRect()
    setTip({ left: Math.max(8, box.left), top: box.bottom + 6 })
  }
  const hide = () => setTip(null)
  return (
    <button type="button" className={cn('lv-entity', className)} aria-describedby={tip ? tipId : undefined} {...props}
      onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}
      onKeyDown={(e) => { if (e.key === 'Escape' && tip) { e.stopPropagation(); hide() } }}>
      {Icon && <Icon aria-hidden="true" />}
      <span ref={text} className="lv-entity-text">{children}</span>
      {tip && createPortal(
        <span role="tooltip" id={tipId} className="lv-float-tip" style={{ left: tip.left, top: tip.top }}>{children}</span>,
        document.body
      )}
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
