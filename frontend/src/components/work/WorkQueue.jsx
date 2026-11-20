/**
 * Work queue template: open items grouped by urgency, one row per item (subject
 * and type, facts, relative due date, row actions), multiple selection for the
 * bulk actions, folded history. Loading, error and empty states of its own.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Question, CheckCircle, Clock, Warning, CaretRight, CaretDown, ArrowsClockwise } from '@phosphor-icons/react'
import { cn, formatDate } from '../../lib/utils'
import { compactDue, dueTone } from '../../lib/relativeTime'
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
  const Icon = shown === 'bad' ? Warning : Clock
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

function WorkRow({ row, checked, opened, selecting, onToggle, selectable }) {
  const { t } = useTranslation()
  return (
    <li className={cn('wk-row', checked && 'is-checked', opened && 'is-opened', !selectable && 'no-check')} data-work-row={row.id}>
      {selectable && (
        <label className="wk-check">
          <input type="checkbox" checked={checked} onChange={() => onToggle(row.id)}
            aria-label={t('work.selectRow', { name: row.title })} />
        </label>
      )}
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

function WorkGroup({ group, selected, openedId, toggle, setMany, selecting, selectable }) {
  const { t } = useTranslation()
  const box = useRef(null)
  const ids = group.items.filter((r) => r.selectable !== false).map((r) => r.id)
  const picked = ids.filter((id) => selected.has(id)).length
  const all = ids.length > 0 && picked === ids.length
  const canPick = selectable && ids.length > 0
  useEffect(() => { if (box.current) box.current.indeterminate = picked > 0 && !all }, [picked, all])
  const Icon = group.icon || Clock
  const headId = `wk-${group.id}`
  return (
    <section className="wk-panel wk-group" aria-labelledby={headId} data-work-group={group.id}>
      <header className="wk-group-head">
        {canPick && (
          <label className="wk-check">
            <input ref={box} type="checkbox" checked={all} onChange={() => setMany(ids, !all)}
              aria-label={t('work.selectAll', { group: group.label })} />
          </label>
        )}
        <h2 id={headId}>
          <span className={cn('wk-tone', group.tone && `is-${group.tone}`)}><Icon aria-hidden="true" /></span>
          {group.label}
          <span className="wk-counter">{group.items.length}</span>
        </h2>
      </header>
      <ul className="wk-list">
        {group.items.map((row) => (
          <WorkRow key={row.id} row={row} checked={selected.has(row.id)} opened={openedId === row.id}
            selecting={selecting} onToggle={toggle} selectable={selectable && row.selectable !== false} />
        ))}
      </ul>
    </section>
  )
}

function WorkSkeleton() {
  const { t } = useTranslation()
  return (
    <div className="wk-skel" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{t('work.loading')}</span>
      {[2, 1].map((n, g) => (
        <section key={g} className="wk-panel" aria-hidden="true">
          <header className="wk-group-head"><span className="wk-skel-bar" style={{ width: 160, height: 14 }} /></header>
          <ul className="wk-list">
            {Array.from({ length: n }, (_, i) => (
              <li key={i} className="wk-row no-check">
                <div className="wk-main"><span className="wk-skel-bar" style={{ width: '38%' }} /><span className="wk-skel-bar" style={{ width: '56%' }} /></div>
                <span className="wk-skel-bar" style={{ width: 96 }} />
                <span className="wk-skel-bar" style={{ width: 120, height: 26 }} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

/**
 * @param {object} p
 * @param {'loading'|'error'|'ready'} p.state
 * @param {{title, text, onRetry}} [p.error]
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

  if (state === 'loading') return <div className="wk-scroll" ref={rootRef}><div className="wk-view"><WorkSkeleton /></div></div>
  if (state === 'error') {
    return (
      <div className="wk-scroll" ref={rootRef}>
        <div className="lv-error" role="alert" data-testid="work-load-error">
          <Warning aria-hidden="true" />
          <div>
            <h2>{error?.title}</h2>
            {error?.text && <p>{error.text}</p>}
            <div className="lv-error-actions">
              <WorkButton primary icon={ArrowsClockwise} onClick={error?.onRetry}>{t('work.retry')}</WorkButton>
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
            <WorkButton quiet onClick={clear}>{t('work.cancelSelection')}</WorkButton>
          </div>
        ) : (
          hint && <p className="wk-hint"><Question aria-hidden="true" /><span>{hint}</span></p>
        )}
        {shown.length ? shown.map((g) => (
          <WorkGroup key={g.id} group={g} selected={selected} openedId={openedId} toggle={toggle} setMany={setMany}
            selecting={selectable && ids.length > 0} selectable={selectable} />
        )) : (
          <div className="wk-panel wk-empty" data-testid="work-empty">
            <CheckCircle aria-hidden="true" />
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
