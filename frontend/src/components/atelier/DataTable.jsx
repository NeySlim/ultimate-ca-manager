/**
 * The table of the mockup's tableView(), listView() and activity(): `.table-container` holding the
 * scrolling region and its table (caption, sortable headers, a checkbox per row, an entity button,
 * row actions and the opening chevron, skeleton rows, the empty block), or on a phone the mobile
 * records (`.mobile-list`), then the footer. `kind` names which of the mockup's tables it is:
 * 'certificates' (.cert-table), 'module' (.cert-table.module-table) or 'audit' (.audit-table).
 * A record that opens keeps its chevron on screen and opens from anywhere on it (adjust.css).
 */
import { useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useMobile } from '../../contexts/MobileContext'
import { Icon } from './Icon'
import { SkeletonRows, SkeletonCards } from './Skeleton'
import { cedeWidths, CEDE_FLOOR } from './columnShare'

// `share`: the fixed-format columns and the actions take their content's width, the free text shares the rest (adjust.css)
const KINDS = {
  certificates: { table: 'cert-table', container: 'table-container', th: (c) => `col-${c.id}`, actionsBox: true, chevronQuiet: false, share: true },
  module: { table: 'cert-table module-table', container: 'table-container', th: (c) => (c.grow ? 'col-description' : ''), actionsBox: true, chevronQuiet: false, share: true },
  // The mockup's activity() sets the journal's bottom margin in a style attribute
  audit: { table: 'audit-table', container: 'table-container audit-container', th: () => '', actionsBox: false, chevronQuiet: true, style: { marginBottom: 20 } },
}
const SORT = { true: 'ascending', false: 'descending' }
const join = (...c) => c.filter(Boolean).join(' ') || undefined

/** Free text: the name, a growing description, or a column that names its whole text in `title`; it may end in an ellipsis. */
const freeText = (col) => Boolean(col.entity || col.grow || (col.title && !col.fit))

/** The cell's class from its column: the entity, a growing description, other free text, a tone (muted, small, mono). A fitted
 * column is marked on its header only (adjust.css): every table of the mockup keeps its cells on one line. */
function cellClass(col, kind) {
  if (col.entity) return 'entity-cell'
  const tones = [].concat(col.tone || [])
  const text = KINDS[kind]?.share && !col.grow && freeText(col) && 'text-cell'
  if (kind === 'certificates' && col.grow) return join('description-cell', ...tones)
  if (kind === 'module') return join(col.grow && 'description-cell', text, ...tones) || ''
  return join(text, ...tones)
}

/** The columns that may fold, first to go first: a column's `fold` rank (higher folds earlier), else its place
 * from the right; the entity and a column with `fold: false` never fold. */
export function foldOrder(columns) {
  return columns
    .map((c, i) => ({ id: c.id, rank: c.fold ?? i, keep: c.entity || c.fold === false }))
    .filter((c) => !c.keep)
    .sort((a, b) => b.rank - a.rank)
    .map((c) => c.id)
}

/**
 * A table wider than its region, or whose description keeps less than CEDE_FLOOR of its text, first shortens its
 * free text by an ellipsis (`texts`, cedeWidths); beside the dock
 * anchored at the right (#app.dock-right) it then folds its secondary columns one by one, the free text whole again
 * at each fold, until it fits: no horizontal scroll, the actions and the chevron in view. The region widening or
 * the rows changing restores every column and measures again, before the browser paints.
 */
function useFittedColumns(scrollRef, columns, texts, lead, rowsKey, active) {
  const [count, setCount] = useState(0)
  const [caps, setCaps] = useState(null)
  const [width, setWidth] = useState(0)
  const order = foldOrder(columns)
  const key = `${order.join(',')}|${texts.join(',')}|${rowsKey}|${width}`
  const measured = useRef(key)
  useEffect(() => {
    const el = scrollRef.current
    if (!active || !el || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => setWidth(el.clientWidth))
    observer.observe(el)
    return () => observer.disconnect()
  }, [active, scrollRef])
  useLayoutEffect(() => {
    const el = scrollRef.current
    const right = active && !!el?.closest('.dock-right')
    if (!active || !el || measured.current !== key) {
      measured.current = key
      if (count || caps) { setCount(0); setCaps(null); return }
    }
    if (!active || !el) return
    if (!right && count) { setCount(0); setCaps(null); return }
    const heads = [...(el.querySelector('thead tr')?.children || [])]
    const rowsShown = [...el.querySelectorAll('tbody tr')].filter((tr) => tr.children.length === heads.length)
    const shown = columns.filter((c) => !order.slice(0, count).includes(c.id))
    // Short of room: the table overflows, or a growing description keeps less than the floor its text asks for
    let over = el.scrollWidth - el.clientWidth
    shown.forEach((c, i) => {
      if (!c.grow || !heads[lead + i]) return
      const text = Math.max(0, ...rowsShown.map((tr) => tr.children[lead + i].scrollWidth))
      over = Math.max(over, Math.min(CEDE_FLOOR, text) - heads[lead + i].getBoundingClientRect().width)
    })
    if (over <= 1) return
    if (!caps) {
      // The free text at its natural width (only the description takes the room left): its headers give its widths
      const cells = rowsShown[0]?.children || []
      const widths = {}
      const floors = {}
      shown.forEach((c, i) => {
        if (!texts.includes(c.id) || !heads[lead + i]) return
        widths[c.id] = heads[lead + i].getBoundingClientRect().width
        floors[c.id] = cells[lead + i] ? parseFloat(getComputedStyle(cells[lead + i]).minWidth) || 0 : 0
      })
      const next = cedeWidths(widths, over, floors)
      if (next) { setCaps(next); return }
    }
    if (right && count < order.length) { setCount(count + 1); setCaps(null) }
  })
  return { folded: new Set(order.slice(0, count)), caps: caps || {} }
}

/**
 * @param {object} p
 * @param {'certificates'|'module'|'audit'} p.kind
 * @param {Array} p.columns  { id, label, sort?, entity?, resource?, grow?, tone?, fit?, fold?, cell(row), title?(row), icon?(row), extra?(row), skeleton? }
 * @param {Array} p.rows
 * @param {(row) => string} p.rowLabel  names a row in the labels of its checkbox, actions and chevron
 * @param {(row) => void} [p.onOpen]  the entity button and the chevron open the row; with `rowOpens`, the whole row too
 * @param {{ selected: Set, onToggle(id), onTogglePage(on) }} [p.selection]
 * @param {(row) => Array<{icon,label,onClick,write}>} [p.rowActions]  icon buttons before the chevron
 * @param {(row) => {description?, meta?: Array, status?, end?, note?}} [p.card]  the phone record
 */
export function DataTable({
  kind = 'certificates', scrollId, label, caption, columns: allColumns, rows = [], rowKey = (r) => r.id, rowLabel = (r) => String(r.id),
  onOpen, openLabel, openedId, rowOpens = false, selection, rowActions, sort, onSort, loading = false, skeletonRows = 12,
  empty, card, footer, actionsLabel, columnWidths, onColumnWidth, recordsId,
}) {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const k = KINDS[kind] || KINDS.certificates
  const selected = selection?.selected || new Set()
  const locked = selected.size > 0
  const hasActions = Boolean(onOpen || rowActions)
  const pageAll = rows.length > 0 && rows.every((r) => selected.has(rowKey(r)))
  const pageSome = rows.some((r) => selected.has(rowKey(r)))
  const master = useRef(null)
  useEffect(() => { if (master.current) master.current.indeterminate = pageSome && !pageAll }, [pageSome, pageAll])
  const chevronLabel = (row) => (openLabel ? openLabel(row) : t('table.openRow', { name: rowLabel(row) }))
  const firstRead = loading && !rows.length
  const scrollRef = useRef(null)
  // The free text that gives way when short of room (the growing description shortens itself in CSS)
  const texts = k.share ? allColumns.filter((c) => freeText(c) && !c.grow).map((c) => c.id) : []
  const { folded, caps } = useFittedColumns(scrollRef, allColumns, texts, selection ? 1 : 0, rows.map(rowKey).join(','), !(isMobile && card))
  const columns = folded.size ? allColumns.filter((c) => !folded.has(c.id)) : allColumns
  // A free-text cell stops at its ceiling or at the width set by hand, an ellipsis after it; any other column holds its content
  const ceiling = (c) => {
    if (!freeText(c)) return undefined
    const w = [columnWidths?.[c.id], caps[c.id]].filter(Boolean)
    return w.length ? { maxWidth: Math.min(...w) } : undefined
  }
  const colSpan = columns.length + (selection ? 1 : 0) + (hasActions ? 1 : 0)

  const openButton = (row, col) => {
    const name = col.cell(row)
    if (col.resource) {
      return <button type="button" className="resource" data-open={rowKey(row)} disabled={locked || undefined} onClick={(e) => { e.stopPropagation(); onOpen?.(row) }}>{name}</button>
    }
    return (
      <span className="entity-line">
        <button type="button" className="entity-name" data-open={rowKey(row)} disabled={locked || undefined} onClick={(e) => { e.stopPropagation(); onOpen?.(row) }}>
          {col.icon && <Icon name={col.icon(row)} />}<span className="entity-label" title={typeof name === 'string' ? name : undefined}>{name}</span>
        </button>
        {col.extra?.(row)}
      </span>
    )
  }

  const chevron = (row) => (
    <button type="button" className={k.chevronQuiet ? 'icon-btn quiet' : 'icon-btn'} data-open={rowKey(row)} aria-label={chevronLabel(row)}
      disabled={locked || undefined} onClick={(e) => { e.stopPropagation(); onOpen(row) }}>
      <Icon name="right" />
    </button>
  )
  const actionButtons = (row) => (rowActions?.(row) || []).map((a, i) => (
    <button key={i} type="button" className="icon-btn" aria-label={t('table.rowAction', { action: a.label, name: rowLabel(row) })}
      title={a.label} disabled={locked || undefined} data-write={a.write ? '' : undefined} onClick={(e) => { e.stopPropagation(); a.onClick?.(row) }}>
      <Icon name={a.icon} />
    </button>
  ))

  return (
    <div className={k.container} style={k.style} aria-busy={firstRead || undefined}>
      {isMobile && card ? (
        <div className="mobile-list" id={recordsId}>
          {firstRead ? <SkeletonCards /> : rows.length ? rows.map((row) => (
            <MobileRecord key={rowKey(row)} row={row} id={rowKey(row)} name={rowLabel(row)} card={card(row) || {}} selection={selection}
              checked={selected.has(rowKey(row))} opened={kind === 'module' && openedId === rowKey(row)} locked={locked} onOpen={onOpen} chevronLabel={chevronLabel(row)} />
          )) : empty}
        </div>
      ) : (
        <div className="table-scroll" ref={scrollRef} id={scrollId} role="region" tabIndex={0} aria-label={label}>
          <table className={k.table}>
            {caption && <caption className="sr-only">{caption}</caption>}
            <thead>
              <tr>
                {selection && (
                  <th scope="col">
                    <label className="check-hit">
                      <input ref={master} id="select-all" type="checkbox" aria-label={t('table.selectPage')} checked={pageAll}
                        onChange={() => selection.onTogglePage(!pageAll)} />
                    </label>
                  </th>
                )}
                {columns.map((c) => (
                  <HeaderCell key={c.id} col={c} className={join(k.th(c), (c.fit || (k.share && !freeText(c))) && 'fit')} sort={sort} onSort={onSort}
                    width={columnWidths?.[c.id]} onWidth={onColumnWidth} />
                ))}
                {hasActions && <th scope="col" className={kind === 'audit' || k.share ? 'fit' : undefined}><span className="sr-only">{actionsLabel || t('common.actions')}</span></th>}
              </tr>
            </thead>
            <tbody>
              {firstRead ? (
                <SkeletonRows columns={columns} rows={skeletonRows} check={!!selection} actions={hasActions} />
              ) : rows.length ? rows.map((row) => {
                const id = rowKey(row)
                const checked = selected.has(id)
                return (
                  <tr key={id} className={join(openedId === id && 'opened', checked && 'checked')}
                    onClick={rowOpens && onOpen ? (e) => { if (!locked && !e.target.closest?.('button, a, input, label')) onOpen(row) } : undefined}>
                    {selection && (
                      <td>
                        <label className="check-hit">
                          <input type="checkbox" data-select={id} aria-label={t('table.selectRow', { name: rowLabel(row) })} checked={checked}
                            onChange={() => selection.onToggle(id)} />
                        </label>
                      </td>
                    )}
                    {columns.map((c) => {
                      const content = c.entity || c.resource ? openButton(row, c) : c.cell(row)
                      // Free text that may end in an ellipsis names its whole text: the column's title, else the text itself
                      const tip = c.title ? c.title(row) : !c.entity && freeText(c) && typeof content === 'string' ? content : undefined
                      return <td key={c.id} className={cellClass(c, kind)} title={tip || undefined} style={ceiling(c)}>{content}</td>
                    })}
                    {hasActions && (
                      <td>
                        {k.actionsBox
                          ? <div className="table-actions">{actionButtons(row)}{onOpen && chevron(row)}</div>
                          : <>{actionButtons(row)}{onOpen && chevron(row)}</>}
                      </td>
                    )}
                  </tr>
                )
              }) : (
                <tr><td colSpan={colSpan}>{empty}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {footer}
    </div>
  )
}

/** A header: a sort button when the column sorts (aria-sort, the arrow of the direction); a grip to set its width by hand. */
function HeaderCell({ col, className, sort, onSort, width, onWidth }) {
  const { t } = useTranslation()
  const sorted = col.sort && sort?.key === col.sort
  const start = useRef(null)
  const [dragging, setDragging] = useState(false)
  const down = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    start.current = { x: e.clientX, w: e.currentTarget.parentElement.offsetWidth }
    setDragging(true)
  }, [])
  useEffect(() => {
    if (!dragging) return undefined
    const move = (e) => onWidth?.(col.id, Math.max(50, Math.round(start.current.w + e.clientX - start.current.x)))
    const up = () => setDragging(false)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  }, [dragging, onWidth, col.id])
  return (
    <th scope="col" className={className} aria-sort={col.sort ? (sorted ? SORT[sort.asc] : 'none') : undefined}
      style={width ? { width, minWidth: width } : undefined}>
      {col.sort ? (
        <button type="button" data-sort={col.sort} onClick={() => onSort?.(col.sort)}>
          {col.label}{sorted && <Icon name={sort.asc ? 'up' : 'down'} />}
        </button>
      ) : col.label}
      {onWidth && col.resizable !== false && (
        <span className="col-resize" role="presentation" title={t('atelier.resizeColumn')} onPointerDown={down}
          onDoubleClick={(e) => { e.stopPropagation(); onWidth(col.id, null) }} />
      )}
    </th>
  )
}

/**
 * The mockup's mobile record: the checkbox, the name, then the description, the facts and the
 * state (a module's open item is marked as a ticked one, as the mockup does). A record that opens carries its chevron at the right and opens from anywhere on it;
 * the checkbox only selects, and nothing opens while rows are ticked.
 */
export function MobileRecord({ row, id, name, card, selection, checked, opened, locked, onOpen, chevronLabel }) {
  const { t } = useTranslation()
  const meta = (card.meta || []).filter((m) => m !== null && m !== undefined && m !== false && m !== '')
  return (
    <article className={join('mobile-record', onOpen && 'opens', (checked || opened) && 'checked')} data-open={id}
      onClick={onOpen ? (e) => { if (!locked && !e.target.closest?.('button, a, label, input')) onOpen(row) } : undefined}>
      <div className="row-top">
        {selection && (
          <label className="check-hit">
            <input type="checkbox" data-select={id} aria-label={t('table.selectRow', { name })} checked={checked} onChange={() => selection.onToggle(id)} />
          </label>
        )}
        {/* A record with nothing to open (a task, an archive) names itself without a button */}
        {onOpen
          ? <button type="button" className="entity-name" data-open={id} disabled={locked || undefined} onClick={() => onOpen(row)}>{card.title ?? name}</button>
          : <strong className="entity-name">{card.title ?? name}</strong>}
        {onOpen && (
          <button type="button" className="icon-btn quiet" data-open={id} aria-label={chevronLabel} disabled={locked || undefined} onClick={() => onOpen(row)}>
            <Icon name="right" />
          </button>
        )}
      </div>
      {card.description && <p className="row-description">{card.description}</p>}
      {(meta.length > 0 || card.note) && <div className="row-meta">{meta.map((m, i) => <span key={i}>{m}</span>)}{card.note}</div>}
      {(card.status || card.end) && <div className="row-status">{card.status}{card.end !== undefined && <span className="remaining">{card.end}</span>}</div>}
    </article>
  )
}

export default DataTable
