/**
 * The table of the mockup's tableView(), listView() and activity(): `.table-container` holding the
 * scrolling region and its table (caption, sortable headers, a checkbox per row, an entity button,
 * row actions and the opening chevron, skeleton rows, the empty block), or on a phone the mobile
 * records (`.mobile-list`), then the footer. `kind` names which of the mockup's tables it is:
 * 'certificates' (.cert-table), 'module' (.cert-table.module-table) or 'audit' (.audit-table).
 * A record that opens keeps its chevron on screen and opens from anywhere on it (adjust.css).
 * The columns follow one contract and one layout (columnShare.js, COLONNES-SPEC).
 */
import { useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useMobile } from '../../contexts/MobileContext'
import { Icon } from './Icon'
import { FilterSelect } from './Toolbar'
import { SkeletonRows, SkeletonCards } from './Skeleton'
import { columnKind, checkColumns, layoutColumns, NAME_TEXT_FLOOR } from './columnShare'
import { FoldedColumns } from './foldedColumns'

// `share`: one column takes the room left, the others their content's width within their bounds (columnShare.js)
const KINDS = {
  certificates: { table: 'cert-table', container: 'table-container', th: (c) => `col-${c.id}`, actionsBox: true, chevronQuiet: false, share: true },
  module: { table: 'cert-table module-table', container: 'table-container', th: (c) => (c.grow ? 'col-description' : ''), actionsBox: true, chevronQuiet: false, share: true },
  // The mockup's activity() sets the journal's bottom margin in a style attribute
  audit: { table: 'audit-table', container: 'table-container audit-container', th: () => '', actionsBox: false, chevronQuiet: true, style: { marginBottom: 20 } },
}
const SORT = { true: 'ascending', false: 'descending' }
const join = (...c) => c.filter(Boolean).join(' ') || undefined

/** Free text, which may end in an ellipsis with its whole text in a title: the name and the text columns. */
const freeText = (col) => ['entity', 'text'].includes(columnKind(col))

/** The cell's class from its column: the entity, a growing description, other free text, a number, a tone. */
function cellClass(col, kind) {
  const nature = columnKind(col)
  if (nature === 'entity') return 'entity-cell'
  const tones = [].concat(col.tone || [])
  const text = KINDS[kind]?.share && !col.grow && nature === 'text' && 'text-cell'
  const num = nature === 'number' && 'num'
  if (col.grow && kind !== 'audit') return join('description-cell', ...tones)
  return join(text, num, ...tones) || (kind === 'module' ? '' : undefined)
}

const px = (v) => parseFloat(v) || 0

/**
 * The width a header's label asks for: its text and arrow, plus the side padding of the cell and of its sort button,
 * which fills the cell (R4): the button's own box is the column's, not its label's.
 */
function headerWidth(th) {
  const cs = getComputedStyle(th)
  let pad = px(cs.paddingLeft) + px(cs.paddingRight)
  const button = th.querySelector(':scope > button')
  if (button) {
    const bs = getComputedStyle(button)
    pad += px(bs.paddingLeft) + px(bs.paddingRight)
    try {
      const range = document.createRange()
      range.selectNodeContents(button)
      return (range.getBoundingClientRect?.().width || 0) + pad
    } catch { return pad /* jsdom has no layout */ }
  }
  let w = 0
  for (const node of th.childNodes) {
    if (node.nodeType === 1 && node.matches('.col-sep, .col-resize')) continue
    try {
      const range = document.createRange()
      range.selectNode(node)
      w += range.getBoundingClientRect?.().width || 0
    } catch { /* jsdom has no layout */ }
  }
  return w + pad
}

/**
 * A name's floor: its marks beside it whole and NAME_TEXT_FLOOR of its own text, or the widest badge of a group
 * under it (.ca-badges, whose box spans the cell: its content counts, an empty group nothing), plus the cell's padding.
 */
function nameFloor(rows, index) {
  return Math.max(0, ...rows.map((tr) => {
    const td = tr.children[index]
    const line = td?.querySelector('.entity-line')
    if (!line) return 0
    let beside = 0
    let under = 0
    for (const el of line.children) {
      if (el.classList.contains('entity-name')) continue
      if (el.classList.contains('ca-badges')) under = Math.max(under, ...[...el.children].map((b) => b.offsetWidth))
      else {
        const ms = getComputedStyle(el)
        beside += el.offsetWidth + px(ms.marginLeft) + px(ms.marginRight)
      }
    }
    const gap = px(getComputedStyle(line).columnGap) * [...line.children].filter((el) => !el.classList.contains('ca-badges')).slice(1).length
    const cs = getComputedStyle(td)
    return Math.max(beside + gap + NAME_TEXT_FLOOR, under) + px(cs.paddingLeft) + px(cs.paddingRight)
  }))
}

/**
 * The layout of the columns at any desktop width: a measuring render (every column at its natural width,
 * table.measuring), then the decision of layoutColumns (ceilings, the absorbing column, the folded ones),
 * both before the browser paints. The region's width, the columns, the rows or the sort changing measure again.
 */
function useColumnLayout(scrollRef, columns, { lead, trail, rowsKey, sortKey, active }) {
  const [layout, setLayout] = useState(null)
  const [width, setWidth] = useState(0)
  const key = `${columns.map((c) => c.id).join(',')}|${rowsKey}|${width}|${sortKey ?? ''}`
  const measuring = active && layout?.key !== key
  useEffect(() => {
    const el = scrollRef.current
    if (!active || !el || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => {
      setWidth(el.clientWidth)
      // The dock opening shrinks the region: the open row stays in view (D4)
      el.querySelector('tbody tr.opened')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [active, scrollRef])
  useLayoutEffect(() => {
    if (!measuring) return
    const el = scrollRef.current
    const heads = [...(el?.querySelector('thead tr')?.children || [])]
    if (!el || !el.clientWidth || heads.length !== lead + columns.length + trail) {
      setLayout({ key, folded: [], caps: {} })
      return
    }
    const rows = [...el.querySelectorAll('tbody tr')].filter((tr) => tr.children.length === heads.length)
    const fixed = [...heads.slice(0, lead), ...heads.slice(heads.length - trail)].reduce((s, th) => s + th.getBoundingClientRect().width, 0)
    const measures = {}
    columns.forEach((c, i) => {
      const th = heads[lead + i]
      measures[c.id] = {
        natural: th.getBoundingClientRect().width,
        header: headerWidth(th),
        floor: columnKind(c) === 'entity' ? nameFloor(rows, lead + i) : 0,
      }
    })
    const out = layoutColumns(columns, measures, el.clientWidth - fixed, { sortKey, wide: window.innerWidth >= 1800 })
    setLayout({ key, folded: out.folded, caps: out.caps })
  }, [measuring, key]) // eslint-disable-line react-hooks/exhaustive-deps -- the key names everything the measure reads
  if (!active || measuring || !layout) return { measuring, folded: [], caps: {} }
  return { measuring, folded: layout.folded, caps: layout.caps }
}

/** The sign of a sortable column that is not the sorted one: two solid triangles in the label's colour (R3). */
function SortIdle() {
  return (
    <svg className="icon sort-idle" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true">
      <path d="M12 4l5 6H7zM12 20l-5-6h10z" />
    </svg>
  )
}

/** The direction of a sort: an arrow with its shaft, not a chevron, which reads as a menu (R5, G8). */
export function SortArrow({ asc }) {
  return (
    <svg className="icon sort-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={asc ? 'M12 19V5m-6 6 6-6 6 6' : 'M12 5v14m-6-6 6 6 6-6'} />
    </svg>
  )
}

const plainLabel = (col) => (typeof col.label === 'string' ? col.label : col.labelFull || col.id)

/**
 * @param {object} p
 * @param {'certificates'|'module'|'audit'} p.kind
 * @param {Array} p.columns  { id, label, labelFull?, kind?: 'entity'|'text'|'fit'|'number', grow?, priority?: 1-4, sort?, labelled?,
 *   cell(row), title?(row), icon?(row), extra?(row), tone?, skeleton?, resource? } — or the old flags (entity, fit, fold), translated
 * @param {Array} p.rows
 * @param {(row) => string} p.rowLabel  names a row in the labels of its checkbox, actions and chevron
 * @param {(row) => void} [p.onOpen]  the entity button and the chevron open the row; with `rowOpens`, the whole row too
 * @param {{ selection: Set, onToggle(id), onTogglePage(on) }} [p.selection]
 * @param {(row) => Array<{icon,label,onClick,write,spare}>} [p.rowActions]  icon buttons before the chevron; `spare`: hidden short of room
 * @param {{key, asc}} [p.sort]  with onSort the sortable headers are buttons; without it the sorted header only shows its arrow
 * @param {(row) => {description?, meta?: Array, status?, end?, note?}} [p.card]  the phone record
 */
export function DataTable({
  kind = 'certificates', scrollId, label, caption, columns: allColumns, rows = [], rowKey = (r) => r.id, rowLabel = (r) => String(r.id),
  onOpen, openLabel, openedId, rowOpens = false, selection, rowActions, sort, onSort, loading = false, skeletonRows = 12,
  empty, card, footer, actionsLabel, columnWidths, onColumnWidth, recordsId,
}) {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  if (!import.meta.env.PROD) checkColumns(allColumns)
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
  const cards = isMobile && card
  const { measuring, folded, caps } = useColumnLayout(scrollRef, allColumns, {
    lead: selection ? 1 : 0, trail: hasActions ? 1 : 0, rowsKey: rows.map(rowKey).join(','), sortKey: sort?.key, active: Boolean(k.share && !cards),
  })
  const columns = folded.length ? allColumns.filter((c) => !folded.includes(c.id)) : allColumns
  const foldedLabels = allColumns.filter((c) => folded.includes(c.id)).map(plainLabel)
  // The one column that takes the room left: the growing one, else the name (L7)
  const absorber = (columns.find((c) => c.grow) || columns.find((c) => columnKind(c) === 'entity'))?.id
  const sortable = Boolean(onSort) && allColumns.some((c) => c.sort)

  // A free-text cell stops at its ceiling or at the width set by hand, an ellipsis after it; any other column holds its content
  const cellStyle = (c) => {
    if (!freeText(c) || measuring) return undefined
    const max = [columnWidths?.[c.id], caps[c.id]?.max].filter(Boolean)
    const style = {}
    if (max.length) style.maxWidth = Math.min(...max)
    if (caps[c.id]?.min) style.minWidth = caps[c.id].min
    return max.length || style.minWidth ? style : undefined
  }
  const colSpan = columns.length + (selection ? 1 : 0) + (hasActions ? 1 : 0)

  // The open row stays in view after a sort or a fold (D4)
  const foldedKey = folded.join(',')
  useEffect(() => {
    scrollRef.current?.querySelector('tbody tr.opened')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }, [openedId, sort?.key, sort?.asc, foldedKey])

  // Each change of the sort is said in words to a screen reader (T6)
  const [announce, setAnnounce] = useState('')
  const lastSort = useRef(sort)
  useEffect(() => {
    const before = lastSort.current
    lastSort.current = sort
    if (!sort || !before || (before.key === sort.key && before.asc === sort.asc)) return
    const col = allColumns.find((c) => c.sort === sort.key)
    if (col) setAnnounce(t('table.sortedBy', { column: plainLabel(col), order: t(sort.asc ? 'table.sortAscending' : 'table.sortDescending') }))
  }, [sort?.key, sort?.asc]) // eslint-disable-line react-hooks/exhaustive-deps

  const openButton = (row, col) => {
    const name = col.cell(row)
    if (col.resource) {
      return <button type="button" className="resource" data-open={rowKey(row)} disabled={locked || undefined} onClick={(e) => { e.stopPropagation(); onOpen?.(row) }}>{name}</button>
    }
    const label = <>{col.icon && <Icon name={col.icon(row)} />}<span className="entity-label" title={typeof name === 'string' ? name : undefined}>{name}</span></>
    // A list with nothing to open (a task, an archive) names its row without a button
    return (
      <span className="entity-line">
        {onOpen ? (
          <button type="button" className="entity-name" data-open={rowKey(row)} disabled={locked || undefined} onClick={(e) => { e.stopPropagation(); onOpen(row) }}>
            {label}
          </button>
        ) : <span className="entity-name">{label}</span>}
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
      title={a.label} disabled={locked || undefined} data-write={a.write ? '' : undefined} data-spare={a.spare ? '' : undefined}
      onClick={(e) => { e.stopPropagation(); a.onClick?.(row) }}>
      <Icon name={a.icon} />
    </button>
  ))
  const sortables = allColumns.filter((c) => c.sort)

  return (
    <FoldedColumns.Provider value={foldedLabels.length ? foldedLabels : null}>
      {cards && sortable && (
        // On a phone the headers are gone: the same sort from a select and a button that reverses it (R5)
        <div className="toolbar mobile-sort">
          <FilterSelect id={scrollId ? `${scrollId}-sort` : undefined} label={t('table.sortBy')} value={sort?.key || ''} onChange={(v) => onSort(v)}
            options={[...(sort?.key ? [] : [{ value: '', label: t('table.sortBy') }]), ...sortables.map((c) => ({ value: c.sort, label: t('table.sortByColumn', { column: plainLabel(c) }) }))]} />
          <button type="button" className="icon-btn" data-action="reverse-sort" disabled={!sort?.key || undefined} onClick={() => onSort(sort.key)}
            aria-label={t(sort?.asc === false ? 'table.descendingReverse' : 'table.ascendingReverse')} title={t(sort?.asc === false ? 'table.descendingReverse' : 'table.ascendingReverse')}>
            <SortArrow asc={sort?.asc !== false} />
          </button>
        </div>
      )}
      <div className={k.container} style={k.style} aria-busy={firstRead || undefined}>
        <span className="sr-only" aria-live="polite">{announce}</span>
        {cards ? (
          <div className="mobile-list" id={recordsId}>
            {firstRead ? <SkeletonCards /> : rows.length ? rows.map((row) => (
              <MobileRecord key={rowKey(row)} row={row} id={rowKey(row)} name={rowLabel(row)} card={card(row) || {}} selection={selection}
                checked={selected.has(rowKey(row))} opened={kind === 'module' && openedId === rowKey(row)} locked={locked} onOpen={onOpen} chevronLabel={chevronLabel(row)} />
            )) : empty}
          </div>
        ) : (
          <div className="table-scroll" ref={scrollRef} id={scrollId} role="region" tabIndex={0} aria-label={label}>
            <table className={join(k.table, measuring && 'measuring')}>
              {(caption || sortable) && <caption className="sr-only">{[caption, sortable && t('table.sortHint')].filter(Boolean).join(' ')}</caption>}
              <thead>
                <tr>
                  {selection && (
                    <th scope="col" className="check-col">
                      <label className="check-hit">
                        <input ref={master} id="select-all" type="checkbox" aria-label={t('table.selectPage')} checked={pageAll}
                          onChange={() => selection.onTogglePage(!pageAll)} />
                      </label>
                    </th>
                  )}
                  {columns.map((c, i) => (
                    <HeaderCell key={c.id} col={c} sort={sort} onSort={onSort} last={i === columns.length - 1}
                      className={join(k.th(c), (k.share ? c.id !== absorber : c.fit) && 'fit', columnKind(c) === 'number' && 'num')}
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
                  const opened = openedId === id
                  return (
                    <tr key={id} className={join(opened && 'opened', checked && 'checked')} aria-current={opened ? 'true' : undefined}
                      onClick={rowOpens && onOpen ? (e) => { if (!locked && !e.target.closest?.('button, a, input, label')) onOpen(row) } : undefined}>
                      {selection && (
                        <td className="check-col">
                          <label className="check-hit">
                            <input type="checkbox" data-select={id} aria-label={t('table.selectRow', { name: rowLabel(row) })} checked={checked}
                              onChange={() => selection.onToggle(id)} />
                          </label>
                        </td>
                      )}
                      {columns.map((c) => {
                        const content = c.entity || c.kind === 'entity' || c.resource ? openButton(row, c) : c.cell(row)
                        // Free text that may end in an ellipsis names its whole text: the column's title, else the text itself (L6)
                        const tip = c.title ? c.title(row) : columnKind(c) === 'text' && typeof content === 'string' && content !== '—' ? content : undefined
                        return <td key={c.id} className={cellClass(c, kind)} title={tip || undefined} style={cellStyle(c)}>{content}</td>
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
    </FoldedColumns.Provider>
  )
}

/**
 * A header: a sort button when the list sorts by it (aria-sort, an arrow for the sorted direction, both arrows
 * otherwise); without onSort the sorted column only shows its arrow. A separator before the next header, which is
 * the grip that sets the width by hand when the list offers it.
 */
function HeaderCell({ col, className, sort, onSort, width, onWidth, last }) {
  const { t } = useTranslation()
  const sorted = Boolean(col.sort) && sort?.key === col.sort
  const button = Boolean(col.sort && onSort)
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
  const arrow = sorted ? <SortArrow asc={sort.asc} /> : button ? <SortIdle /> : null
  // A number's arrow comes first, so that its label ends on the digits' right edge (L9)
  const content = columnKind(col) === 'number' ? <>{arrow}{col.label}</> : <>{col.label}{arrow}</>
  const full = col.labelFull ? { title: col.labelFull, 'aria-label': col.labelFull } : {}
  // The button says what a click does: sort by the column, or reverse the sort it shows (R4)
  const does = sorted
    ? t('table.sortedByReverse', { column: col.labelFull || plainLabel(col), order: t(sort.asc ? 'table.sortAscending' : 'table.sortDescending') })
    : t('table.sortByColumn', { column: col.labelFull || plainLabel(col) })
  const grip = onWidth && col.resizable !== false
  return (
    <th scope="col" className={className} aria-sort={button ? (sorted ? SORT[sort.asc] : 'none') : sorted ? SORT[sort.asc] : undefined}
      style={width ? { width, minWidth: width } : undefined} {...(button ? {} : full)}>
      {button ? <button type="button" data-sort={col.sort} onClick={() => onSort(col.sort)} {...full} title={does}>{content}</button> : content}
      {grip ? (
        <span className={join('col-resize', !last && 'col-sep')} role="presentation" title={t('atelier.resizeColumn')} onPointerDown={down}
          onDoubleClick={(e) => { e.stopPropagation(); onWidth(col.id, null) }} />
      ) : !last && <span className="col-sep" aria-hidden="true" />}
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
