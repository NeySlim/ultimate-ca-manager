/**
 * The mockup's workView(), workGroup() and workRow(): the open items grouped by urgency, one row
 * per item (subject and kind, facts, due date, its main action), a checkbox per row and per group
 * for the bulk actions (the row actions wait meanwhile), then the folded history. A selected item
 * that left the queue leaves the selection; clearing it gives the focus to the page title.
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { compactDue, dueTone } from '../../lib/relativeTime'
import { formatDate } from '../../lib/utils'
import { Icon } from './Icon'
import { Bar } from './Skeleton'
import { BatchBar } from './BatchBar'
import { RecordList } from './Detail'

/** The due date of a row: the relative words in bold, the exact date under them, coloured by urgency. */
export function QueueDue({ due, label, date, tone, warnDays = 7, children }) {
  const { t } = useTranslation()
  const shown = tone ?? dueTone(due, { warnDays })
  return (
    <div className={shown ? `queue-due ${shown}` : 'queue-due'}>
      <Icon name={shown === 'bad' ? 'warning' : 'clock'} />
      <span><strong>{label ?? compactDue(due, t)}</strong><small>{date ?? (due ? formatDate(due, { time: true }) : '')}</small>{children}</span>
    </div>
  )
}

function WorkRow({ row, checked, opened, selecting, selectable, onToggle }) {
  const { t } = useTranslation()
  const facts = (row.facts || []).filter(Boolean)
  return (
    <li className={['work-row', opened && 'opened', checked && 'checked'].filter(Boolean).join(' ')} data-work-row={row.id}>
      <label className="check-hit">
        {selectable && (
          <input type="checkbox" id={`work-sel-${row.id}`} data-work-select={row.id} aria-label={t('work.selectRow', { name: row.title })}
            checked={checked} onChange={() => onToggle(row.id)} />
        )}
      </label>
      <div className="work-main">
        <p className="work-head">
          <button type="button" className="text-link work-subject" data-open={row.id} onClick={row.onOpen}>{row.title}</button>
          {row.kind && <span className="queue-kind">{row.kind}</span>}
        </p>
        {facts.length > 0 && <p className="work-detail">{facts.join(' · ')}</p>}
      </div>
      <QueueDue due={row.due} label={row.dueLabel} date={row.dueDate} tone={row.tone} warnDays={row.warnDays} />
      <div className="work-action">{row.actions?.(selecting)}</div>
    </li>
  )
}

// The group box is ticked once every row of it is, and stays clear before (no mixed state, as the mockup)
function WorkGroup({ group, selected, openedId, selecting, selectable, toggle, setMany }) {
  const { t } = useTranslation()
  const ids = group.items.filter((r) => r.selectable !== false).map((r) => r.id)
  const all = ids.length > 0 && ids.every((id) => selected.has(id))
  return (
    <section className="panel work-group" aria-labelledby={`wg-${group.id}`} data-work-group={group.id}>
      <header className="work-group-head">
        <label className="check-hit">
          {selectable && ids.length > 0 && (
            <input type="checkbox" id={`work-all-${group.id}`} aria-label={t('work.selectAll', { group: group.label })} checked={all}
              onChange={() => setMany(ids, !all)} />
          )}
        </label>
        <h2 id={`wg-${group.id}`}><span className={group.tone || undefined}><Icon name={group.icon || 'clock'} /></span>{group.label}<span className="counter">{group.items.length}</span></h2>
      </header>
      <ul className="work-list">
        {group.items.map((row) => (
          <WorkRow key={row.id} row={row} checked={selected.has(row.id)} opened={openedId === row.id} selecting={selecting}
            selectable={selectable && row.selectable !== false} onToggle={toggle} />
        ))}
      </ul>
    </section>
  )
}

/** Skeleton at the size of what replaces it: the hint line, two groups of rows, the folded history. */
function WorkSkeleton({ history }) {
  const { t } = useTranslation()
  return (
    <div className="work-view" aria-busy="true">
      <p className="sr-only" role="status">{t('work.loading')}</p>
      <p className="work-hint" aria-hidden="true"><Bar width="14px" /><Bar width="min(420px, 100%)" /></p>
      {[2, 1].map((n, g) => (
        <section key={g} className="panel work-group" aria-hidden="true">
          <header className="work-group-head"><span className="check-hit"><Bar width="16px" kind="box" /></span><Bar width="160px" /></header>
          <ul className="work-list">
            {Array.from({ length: n }, (_, i) => (
              <li key={i} className="work-row">
                <span className="check-hit"><Bar width="16px" kind="box" /></span>
                <div className="work-main"><Bar width="38%" /><Bar width="56%" kind="thin" /></div>
                <span className="queue-due"><Bar width="96px" /></span>
                <span className="work-action"><Bar width="120px" /></span>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {history && <section className="panel work-history" aria-hidden="true"><p className="work-history-title"><Bar width="140px" /></p></section>}
    </div>
  )
}

// The history shows its newest twenty lines, then as many more at each ask: never a page of a hundred lines at once
const HISTORY_STEP = 20

/**
 * @param {object} p
 * @param {'loading'|'error'|'ready'} [p.state]
 * @param {import('react').ReactNode} [p.error]  a LoadError, shown in place of the queue
 * @param {string} p.hint  shown above the groups while nothing is selected
 * @param {Array<{id,label,icon,tone,items}>} p.groups  rows: { id, title, kind, facts, due, dueLabel, dueDate, tone, onOpen, actions(disabled), selectable }
 * @param {(ids: string[], clear: () => void) => import('react').ReactNode} [p.bulk]  no selection without it
 * @param {{ title, text, action }} p.empty
 * @param {{ label, count, children, empty, catalog }} [p.history]  `catalog`: a list of kinds, not of dated events: two abreast in a wide panel
 */
export function WorkView({ state = 'ready', error, hint, groups, bulk, openedId, empty, history, after, label }) {
  const { t } = useTranslation()
  const [picked, setPicked] = useState(() => new Set())
  const [historyOpen, setHistoryOpen] = useState(false)
  const shown = useMemo(() => groups.filter((g) => g.items.length), [groups])
  const selectable = typeof bulk === 'function'
  const openIds = useMemo(() => new Set(shown.flatMap((g) => g.items.filter((r) => r.selectable !== false).map((r) => r.id))), [shown])
  const selected = useMemo(() => new Set([...picked].filter((id) => openIds.has(id))), [picked, openIds])
  const toggle = (id) => setPicked((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const setMany = (ids, on) => setPicked((prev) => { const n = new Set(prev); for (const id of ids) { if (on) n.add(id); else n.delete(id) } return n })
  const clear = () => setPicked(new Set())
  const ids = [...selected]

  let body
  if (state === 'loading') body = <WorkSkeleton history={!!history} />
  else if (state === 'error') body = <div className="work-view">{error}</div>
  else {
    body = (
      <div className="work-view" aria-label={label}>
        {/* The hint says how to tick several rows: none when there is no row to tick */}
        {selectable && ids.length > 0 ? (
          <BatchBar work count={t('work.selected', { count: ids.length })} onClear={clear}>{bulk(ids, clear)}</BatchBar>
        ) : hint && shown.length > 0 && <p className="work-hint"><Icon name="help" /><span>{hint}</span></p>}
        {shown.length ? shown.map((g) => (
          <WorkGroup key={g.id} group={g} selected={selected} openedId={openedId} selecting={selectable && ids.length > 0}
            selectable={selectable} toggle={toggle} setMany={setMany} />
        )) : (
          <div className="panel queue-empty" data-testid="work-empty">
            <Icon name="check" /><h3>{empty?.title}</h3><p>{empty?.text}</p>{empty?.action}
          </div>
        )}
        {history && (
          <section className={history.catalog ? 'panel work-history catalog' : 'panel work-history'} aria-labelledby="work-history-title">
            <h2 className="work-history-title" id="work-history-title">
              <button type="button" className="work-history-toggle" id="work-history-toggle" data-work-history="" aria-expanded={historyOpen}
                aria-controls="work-history" onClick={() => setHistoryOpen((v) => !v)}>
                <Icon name={historyOpen ? 'down' : 'right'} />{history.label}<span className="counter">{history.count}</span>
              </button>
            </h2>
            <div className="work-history-body" id="work-history" hidden={!historyOpen}>
              <RecordList empty={history.empty || t('work.historyEmpty')} step={HISTORY_STEP}>{history.children}</RecordList>
            </div>
          </section>
        )}
        {after}
      </div>
    )
  }
  return <div className="scroll-view" id="view-scroll">{body}</div>
}

export default WorkView
