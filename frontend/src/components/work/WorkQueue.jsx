/**
 * Work queue template: open items grouped by urgency, one row per item (subject
 * and type, facts, relative due date, row actions), multiple selection for the
 * bulk actions, folded history. Loading, error and empty states of its own.
 */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Question, Warning, CaretRight, CaretDown } from '@phosphor-icons/react'
import { cn, formatDate } from '../../lib/utils'
import { compactDue, dueTone } from '../../lib/relativeTime'
import { RefreshIcon } from '../list/atelierIcons'
import { CheckIcon, ClockIcon } from './workIcons'
import { focusTitle } from './focus'
import '../list/list.css'
import './work.css'

/** A button of the queue: `primary`, `quiet` or `danger`; the icon goes first. */
export function WorkButton({ icon: Icon, primary, quiet, danger, className, children, type = 'button', ...props }) {
  return (
    <button type={type} className={cn('wk-btn', primary && 'is-primary', quiet && 'is-quiet', danger && 'is-danger', className)} {...props}>
      {Icon && <Icon aria-hidden="true" />}
      {children}
    </button>
  )
}

/** Due date of a row: relative wording in bold, exact date under it, coloured by urgency. */
export function WorkDue({ due, label, date, tone, warnDays = 7 }) {
  const { t } = useTranslation()
  const shown = tone ?? dueTone(due, { warnDays })
  const Icon = shown === 'bad' ? Warning : ClockIcon
  return (
    <div className={cn('wk-due', shown && `is-${shown}`)}>
      <Icon aria-hidden="true" />
      <span>
        <strong>{label ?? compactDue(due, t)}</strong>
        <small>{date ?? (due ? formatDate(due, { time: true }) : '')}</small>
      </span>
    </div>
  )
}

/** One line of a record list: title, meta, then a badge and an action on the right. */
export function WorkRecord({ title, meta, badge, action }) {
  return (
    <li>
      <div className="wk-rl-main">
        <strong>{title}</strong>
        {meta && <span className="wk-rl-meta">{meta}</span>}
      </div>
      {badge}
      {action && <div className="wk-rl-action">{action}</div>}
    </li>
  )
}

export function WorkRecords({ children, empty }) {
  const list = (Array.isArray(children) ? children : [children]).filter(Boolean)
  return list.length ? <ul className="wk-records">{list}</ul> : <p className="wk-none">{empty}</p>
}

// A row the user may not select keeps the check column empty: its text lines up with the others
function WorkRow({ row, checked, opened, selecting, onToggle, checkColumn, selectable }) {
  const { t } = useTranslation()
  return (
    <li className={cn('wk-row', checked && 'is-checked', opened && 'is-opened', !checkColumn && 'no-check')} data-work-row={row.id}>
      {checkColumn && (selectable ? (
        <label className="wk-check">
          <input type="checkbox" checked={checked} onChange={() => onToggle(row.id)}
            aria-label={t('work.selectRow', { name: row.title })} />
        </label>
      ) : <span className="wk-check" aria-hidden="true" />)}
      <div className="wk-main">
        <p className="wk-head">
          <button type="button" className="wk-subject" onClick={row.onOpen} data-work-open={row.id}>{row.titleNode ?? row.title}</button>
          {row.kind && <span className="wk-kind">{row.kind}</span>}
        </p>
        {row.facts?.length > 0 && <p className="wk-detail">{row.facts.filter(Boolean).join(' · ')}</p>}
      </div>
      <WorkDue due={row.due} label={row.dueLabel} date={row.dueDate} tone={row.tone} warnDays={row.warnDays} />
      <div className="wk-action">{row.actions?.(selecting)}</div>
    </li>
  )
}

// The group box is ticked once every row of it is, and stays clear before (no mixed state, as the mockup)
function WorkGroup({ group, selected, openedId, toggle, setMany, selecting, selectable }) {
  const { t } = useTranslation()
  const ids = group.items.filter((r) => r.selectable !== false).map((r) => r.id)
  const all = ids.length > 0 && ids.every((id) => selected.has(id))
  const Icon = group.icon || ClockIcon
  const headId = `wk-${group.id}`
  return (
    <section className="wk-panel wk-group" aria-labelledby={headId} data-work-group={group.id}>
      <header className="wk-group-head">
        {selectable && (ids.length > 0 ? (
          <label className="wk-check">
            <input type="checkbox" checked={all} onChange={() => setMany(ids, !all)}
              aria-label={t('work.selectAll', { group: group.label })} />
          </label>
        ) : <span className="wk-check" aria-hidden="true" />)}
        <h2 id={headId}>
          <span className={cn('wk-tone', group.tone && `is-${group.tone}`)}><Icon aria-hidden="true" /></span>
          {group.label}
          <span className="wk-counter">{group.items.length}</span>
        </h2>
      </header>
      <ul className="wk-list">
        {group.items.map((row) => (
          <WorkRow key={row.id} row={row} checked={selected.has(row.id)} opened={openedId === row.id}
            selecting={selecting} onToggle={toggle} checkColumn={selectable} selectable={selectable && row.selectable !== false} />
        ))}
      </ul>
    </section>
  )
}

// Skeleton at the size of what replaces it: the hint line, groups with a 47 px head and
// 61 px rows, the folded section; fixed bars, nothing moves when the rows arrive
function WorkSkeleton({ history }) {
  const { t } = useTranslation()
  const bar = (style, kind) => <span className={cn('wk-skel-bar', kind && `is-${kind}`)} style={style} />
  return (
    <div className="wk-view wk-skel" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{t('work.loading')}</span>
      <p className="wk-hint" aria-hidden="true">{bar({ width: 14, height: 14 })}{bar({ width: 420 }, 'fluid')}</p>
      {[2, 1].map((n, g) => (
        <section key={g} className="wk-panel" aria-hidden="true">
          <header className="wk-group-head">
            <span className="wk-check">{bar({ width: 16, height: 16 }, 'box')}</span>
            {bar({ width: 160, height: 14 })}
          </header>
          <ul className="wk-list">
            {Array.from({ length: n }, (_, i) => (
              <li key={i} className="wk-row">
                <span className="wk-check">{bar({ width: 16, height: 16 }, 'box')}</span>
                <div className="wk-main">{bar({ width: '38%' })}{bar({ width: '56%' }, 'thin')}</div>
                <span className="wk-due">{bar({ width: 96 })}</span>
                <span className="wk-action">{bar({ width: 120, height: 26 })}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {history && (
        <section className="wk-panel" aria-hidden="true">
          <p className="wk-history-toggle">{bar({ width: 15, height: 15 })}{bar({ width: 140, height: 14 })}</p>
        </section>
      )}
    </div>
  )
}

/**
 * @param {object} p
 * @param {'loading'|'error'|'ready'} p.state
 * @param {{title, cause, onRetry, journal}} [p.error]  journal: the audit log path, for who may read it
 * @param {string} p.hint  shown above the groups while nothing is selected
 * @param {Array<{id,label,icon,tone,items}>} p.groups  rows: {id,title,kind,facts,due,dueLabel,dueDate,tone,onOpen,actions(disabled),selectable}
 * @param {(ids: string[], clear: () => void) => import('react').ReactNode} [p.bulkActions]  no selection without it
 * @param {{title,text,action}} p.empty
 * @param {{label,count,children}} [p.history]
 */
export function WorkQueue({ state = 'ready', error, hint, groups, bulkActions, openedId, empty, history, label, rootRef }) {
  const { t } = useTranslation()
  const [picked, setPicked] = useState(() => new Set())
  const [historyOpen, setHistoryOpen] = useState(false)
  const shown = useMemo(() => groups.filter((g) => g.items.length), [groups])
  const selectable = typeof bulkActions === 'function'

  // A selected row that left the queue leaves the selection
  const openIds = useMemo(() => new Set(shown.flatMap((g) => g.items.filter((r) => r.selectable !== false).map((r) => r.id))), [shown])
  const selected = useMemo(() => new Set([...picked].filter((id) => openIds.has(id))), [picked, openIds])

  const toggle = (id) => setPicked((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })
  const setMany = (ids, on) => setPicked((prev) => {
    const next = new Set(prev)
    for (const id of ids) { if (on) next.add(id); else next.delete(id) }
    return next
  })
  const clear = () => setPicked(new Set())
  // Clear selection leaves with its bar: the focus goes to the page title, as in the mockup
  const clearAndFocus = () => { clear(); requestAnimationFrame(focusTitle) }

  if (state === 'loading') return <div className="wk-scroll" ref={rootRef}><WorkSkeleton history={!!history} /></div>
  if (state === 'error') {
    return (
      <div className="wk-scroll" ref={rootRef}>
        <div className="lv-error" role="alert" data-testid="work-load-error">
          <Warning aria-hidden="true" />
          <div>
            <h2>{error?.title}</h2>
            {(error?.cause || error?.text) && <p>{error.cause || error.text}</p>}
            <div className="lv-error-actions">
              <WorkButton primary icon={RefreshIcon} onClick={error?.onRetry} data-write="false">{t('work.retry')}</WorkButton>
              {error?.journal && (
                <Link className="lv-text-link" to={error.journal}>{t('work.viewLog')}<CaretRight size={14} aria-hidden="true" /></Link>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  const ids = [...selected]
  return (
    <div className="wk-scroll" ref={rootRef}>
      <div className="wk-view" aria-label={label}>
        {selectable && ids.length > 0 ? (
          <div className="wk-bar" role="group" aria-label={t('work.bulkLabel')}>
            <strong>{t('work.selected', { count: ids.length })}</strong>
            {bulkActions(ids, clear)}
            <span className="wk-spacer" />
            <WorkButton quiet onClick={clearAndFocus}>{t('work.cancelSelection')}</WorkButton>
          </div>
        ) : (
          hint && <p className="wk-hint"><Question aria-hidden="true" /><span>{hint}</span></p>
        )}
        {shown.length ? shown.map((g) => (
          <WorkGroup key={g.id} group={g} selected={selected} openedId={openedId} toggle={toggle} setMany={setMany}
            selecting={selectable && ids.length > 0} selectable={selectable} />
        )) : (
          <div className="wk-panel wk-empty" data-testid="work-empty">
            <CheckIcon size={28} aria-hidden="true" />
            <h3>{empty?.title}</h3>
            <p>{empty?.text}</p>
            {empty?.action}
          </div>
        )}
        {history && (
          <section className="wk-panel" aria-labelledby="wk-history-title">
            <h2 className="wk-history-title" id="wk-history-title">
              <button type="button" className="wk-history-toggle" data-work-history="" aria-expanded={historyOpen}
                aria-controls="wk-history" onClick={() => setHistoryOpen((v) => !v)}>
                {historyOpen ? <CaretDown aria-hidden="true" /> : <CaretRight aria-hidden="true" />}
                {history.label}
                <span className="wk-counter">{history.count}</span>
              </button>
            </h2>
            <div className="wk-history-body" id="wk-history" hidden={!historyOpen}>
              {history.children}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

export default WorkQueue
