/**
 * The table of the mockup's tableView(), listView() and activity(): `.table-container` holding the
 * scrolling region and its table (caption, sortable headers, a checkbox per row, an entity button,
 * row actions and the opening chevron, skeleton rows, the empty block), or on a phone the mobile
 * records (`.mobile-list`), then the footer. `kind` names which of the mockup's tables it is:
 * 'certificates' (.cert-table), 'module' (.cert-table.module-table) or 'audit' (.audit-table).
 * A record that opens keeps its chevron on screen and opens from anywhere on it (adjust.css).
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useMobile } from '../../contexts/MobileContext'
import { Icon } from './Icon'
import { SkeletonRows, SkeletonCards } from './Skeleton'

const KINDS = {
  certificates: { table: 'cert-table', container: 'table-container', th: (c) => `col-${c.id}`, actionsBox: true, chevronQuiet: false },
  module: { table: 'cert-table module-table', container: 'table-container', th: (c) => (c.grow ? 'col-description' : ''), actionsBox: true, chevronQuiet: false },
  // The mockup's activity() sets the journal's bottom margin in a style attribute
  audit: { table: 'audit-table', container: 'table-container audit-container', th: () => '', actionsBox: false, chevronQuiet: true, style: { marginBottom: 20 } },
}
const SORT = { true: 'ascending', false: 'descending' }
const join = (...c) => c.filter(Boolean).join(' ') || undefined

/** The cell's class from its column: the entity, a growing description, a tone (muted, small, mono). A fitted column is
 * marked on its header only (adjust.css): every table of the mockup keeps its cells on one line. */
function cellClass(col, kind) {
  if (col.entity) return 'entity-cell'
  const tones = [].concat(col.tone || [])
  if (kind === 'certificates' && col.grow) return join('description-cell', ...tones)
  if (kind === 'module') return join(col.grow && 'description-cell', ...tones) || ''
  return join(...tones)
}

/**
 * @param {object} p
 * @param {'certificates'|'module'|'audit'} p.kind
 * @param {Array} p.columns  { id, label, sort?, entity?, resource?, grow?, tone?, fit?, cell(row), title?(row), icon?(row), extra?(row), skeleton? }
 * @param {Array} p.rows
 * @param {(row) => string} p.rowLabel  names a row in the labels of its checkbox, actions and chevron
 * @param {(row) => void} [p.onOpen]  the entity button and the chevron open the row; with `rowOpens`, the whole row too
 * @param {{ selected: Set, onToggle(id), onTogglePage(on) }} [p.selection]
 * @param {(row) => Array<{icon,label,onClick,write}>} [p.rowActions]  icon buttons before the chevron
 * @param {(row) => {description?, meta?: Array, status?, end?, note?}} [p.card]  the phone record
 */
export function DataTable({
  kind = 'certificates', scrollId, label, caption, columns, rows = [], rowKey = (r) => r.id, rowLabel = (r) => String(r.id),
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
  const colSpan = columns.length + (selection ? 1 : 0) + (hasActions ? 1 : 0)
  const firstRead = loading && !rows.length

  const openButton = (row, col) => {
    const name = col.cell(row)
    if (col.resource) {
      return <button type="button" className="resource" data-open={rowKey(row)} disabled={locked || undefined} onClick={(e) => { e.stopPropagation(); onOpen?.(row) }}>{name}</button>
    }
    return (
      <>
        <button type="button" className="entity-name" data-open={rowKey(row)} disabled={locked || undefined} onClick={(e) => { e.stopPropagation(); onOpen?.(row) }}>
          {col.icon && <Icon name={col.icon(row)} />}{name}
        </button>
        {col.extra?.(row)}
      </>
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
        <div className="table-scroll" id={scrollId} role="region" tabIndex={0} aria-label={label}>
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
                  <HeaderCell key={c.id} col={c} className={join(k.th(c), c.fit && 'fit')} sort={sort} onSort={onSort}
                    width={columnWidths?.[c.id]} onWidth={onColumnWidth} />
                ))}
                {hasActions && <th scope="col" className={kind === 'audit' ? 'fit' : undefined}><span className="sr-only">{actionsLabel || t('common.actions')}</span></th>}
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
                    {columns.map((c) => (
                      <td key={c.id} className={cellClass(c, kind)} title={c.title?.(row) || undefined}
                        style={columnWidths?.[c.id] ? { maxWidth: columnWidths[c.id] } : undefined}>
                        {c.entity || c.resource ? openButton(row, c) : c.cell(row)}
                      </td>
                    ))}
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
      style={width ? { width, minWidth: width, maxWidth: width } : undefined}>
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
        <button type="button" className="entity-name" data-open={id} disabled={locked || undefined} onClick={() => onOpen?.(row)}>{card.title ?? name}</button>
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
