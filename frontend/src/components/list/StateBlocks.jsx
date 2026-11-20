/**
 * Out-of-nominal states of any page, as the list template draws them: skeleton bars at the
 * size of the content they stand for (rows keep their final height, nothing jumps on arrival),
 * the read error with its cause and Retry, and the empty block (why, then the next action).
 */
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, CaretRight, FileX, Warning } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { ListButton } from './PageHead'
import './list.css'

/** Width of skeleton bar `i`: varies a little so the rows do not look identical. */
export const skWidth = (i, base, spread) => `${base + ((i * 37) % spread)}%`

/** One bar; `kind` 'pill' (a status), 'box' (a check box), 'thin' (a second line). */
export function SkeletonBar({ width, kind, className }) {
  return <span className={cn('lv-sk', kind && `is-${kind}`, className)} style={width ? { width } : undefined} />
}

/**
 * Skeleton rows of a table body: one cell per column, `columns` = [{ width, grow, kind }].
 * The first row carries the "loading" announcement; the others are hidden from assistive tech.
 */
export function SkeletonRows({ columns, rows = 12, check = false, actions = false }) {
  const { t } = useTranslation()
  return Array.from({ length: rows }, (_, i) => (
    <tr key={`sk-${i}`} className="lv-sk-row" aria-hidden={i > 0 || undefined}>
      {check && <td className="lv-col-check"><div className="lv-cell"><SkeletonBar kind="box" /></div></td>}
      {columns.map((col, c) => (
        <td key={col.key || c} className={cn(col.grow && 'lv-grow')}>
          <div className="lv-cell">
            {i === 0 && c === 0 && <span className="sr-only" role="status">{t('table.loadingRows')}</span>}
            <SkeletonBar kind={col.kind} width={col.grow ? skWidth(i, 45, 40) : (col.width || 64)} />
          </div>
        </td>
      ))}
      {actions && <td className="lv-col-actions" />}
    </tr>
  ))
}

/** Skeleton cards of a phone list: a name, a second line, a status. */
export function SkeletonCards({ count = 6 }) {
  const { t } = useTranslation()
  return (
    <div className="lv-sk-cards" aria-busy="true">
      <span className="sr-only" role="status">{t('table.loadingRows')}</span>
      {Array.from({ length: count }, (_, i) => (
        <article key={i} className="lv-sk-record" aria-hidden="true">
          <SkeletonBar width={skWidth(i, 50, 30)} />
          <SkeletonBar width={skWidth(i, 30, 40)} kind="thin" />
          <SkeletonBar width="90px" kind="pill" />
        </article>
      ))}
    </div>
  )
}

/**
 * A read that failed: what could not be read, its cause, Retry; the journal link only for
 * who may read it (`journal`: a path, or omitted). The other views stay usable.
 */
export function LoadError({ title, cause, onRetry, journal, journalLabel, className, ...props }) {
  const { t } = useTranslation()
  return (
    <div className={cn('lv-error', className)} role="alert" {...props}>
      <Warning aria-hidden="true" />
      <div>
        <h2>{title}</h2>
        {cause && <p>{cause}</p>}
        <div className="lv-error-actions">
          {onRetry && <ListButton primary data-write="false" icon={ArrowsClockwise} onClick={onRetry}>{t('table.retry')}</ListButton>}
          {journal && (
            <Link className="lv-text-link" to={journal}>{journalLabel || t('certificates.viewLog')}<CaretRight size={14} aria-hidden="true" /></Link>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * Nothing to show: icon, why, the next useful action. `action` = { label, onClick | to, icon, primary }.
 */
export function EmptyBlock({ icon: Icon = FileX, title, description, action, className, ...props }) {
  return (
    <div className={cn('lv-empty', className)} {...props}>
      {Icon && <Icon aria-hidden="true" />}
      {title && <h3>{title}</h3>}
      {description && <p>{description}</p>}
      {action && (action.to ? (
        <Link className={cn('lv-btn', action.primary && 'is-primary')} to={action.to}>
          {action.icon && <action.icon size={16} aria-hidden="true" />}{action.label}
        </Link>
      ) : (
        <ListButton primary={!!action.primary} icon={action.icon} onClick={action.onClick}>{action.label}</ListButton>
      ))}
    </div>
  )
}
