/**
 * ListTable: the desktop table of the list template (ResponsiveDataTable variant="list").
 * Columns take the width of their content and the `grow` column absorbs the rest, its
 * content shortened by an ellipsis when the room runs out (a `fill` cell lets its own
 * content do it); a `minWidth` column without `grow` keeps its whole text; every row
 * keeps one height; a row carries its checkbox, its own actions and a chevron that
 * opens the detail (with `openFromName`, only the name and the chevron open it; while
 * `locked`, a selection being made, they are disabled). Loading draws skeleton rows,
 * an empty list its `emptyContent` under the header.
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { CaretUp, CaretDown, CaretRight } from '@phosphor-icons/react'
import { cn } from '../../../lib/utils'
import { SkeletonBar, skWidth } from '../../list/StateBlocks'
import '../../list/list.css'

const SORT = { asc: 'ascending', desc: 'descending' }
const SKELETON_ROWS = 12
// A column's skeleton bar: its own width (px, CSS length, or per row), else a varying share
const skBar = (col, i) => {
  const w = typeof col.skeletonWidth === 'function' ? col.skeletonWidth(i, skWidth) : col.skeletonWidth
  if (w !== undefined) return w
  return col.grow ? skWidth(i, 45, 40) : 64
}

export function ListTable({
  data,
  columns,
  selectedId,
  onRowClick,
  rowActions,
  rowLabel,
  label,
  sort,
  onSort,
  sortable,
  loading,
  density = 'compact',
  columnWidths = {},
  setColumnWidth,
  resetColumnWidth,
  multiSelect,
  selectedIds,
  onToggleRow,
  onToggleAll,
  openFromName = false,
  locked = false,
  emptyContent,
  skeletonRows = SKELETON_ROWS,
}) {
  const { t } = useTranslation()
  const [resizing, setResizing] = useState(null)
  const start = useRef({ x: 0, width: 0 })

  const beginResize = useCallback((e, key) => {
    e.preventDefault()
    e.stopPropagation()
    const th = e.target.closest('th')
    if (!th) return
    start.current = { x: e.clientX, width: th.offsetWidth }
    setResizing(key)
  }, [])

  useEffect(() => {
    if (!resizing) return
    const move = (e) => setColumnWidth(resizing, Math.max(50, start.current.width + e.clientX - start.current.x))
    const stop = () => setResizing(null)
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', stop)
    return () => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', stop)
    }
  }, [resizing, setColumnWidth])

  // A width set by hand or capped by the column clips its cell; the others follow their content.
  // Caps and floors go through variables so a narrow page (right dock) can tighten them.
  const sizing = (col) => {
    const px = columnWidths[col.key]
    if (px) return { clip: true, style: { width: px, minWidth: px, maxWidth: px } }
    if (col.grow) return { clip: true, style: col.minWidth ? { '--lv-min': `${col.minWidth}px` } : undefined }
    if (col.minWidth && !col.maxWidth) return { clip: false, floor: true, style: { '--lv-min': `${col.minWidth}px` } }
    if (col.maxWidth) {
      return {
        clip: true, capped: true,
        style: { '--lv-max': `${col.maxWidth}px`, ...(col.narrowMaxWidth ? { '--lv-max-narrow': `${col.narrowMaxWidth}px` } : {}) },
      }
    }
    return { clip: false, style: undefined }
  }

  const nameOf = (row) => rowLabel?.(row) ?? ''
  const hasActions = Boolean(rowActions || onRowClick)

  return (
    <div className="lv-scroll" role="region" tabIndex={0} aria-label={label} aria-busy={loading || undefined}>
      <table className={cn('lv-table', `is-${density}`, resizing && 'select-none')}>
        {label && <caption className="sr-only">{label}</caption>}
        <thead>
          <tr>
            {multiSelect && (
              <th scope="col" className="lv-col-check">
                <label className="lv-check">
                  <input
                    type="checkbox"
                    aria-label={t('table.selectPage')}
                    checked={data.length > 0 && data.every(r => selectedIds?.has(r.id))}
                    onChange={onToggleAll}
                  />
                </label>
              </th>
            )}
            {columns.map((col) => {
              const { style, capped, floor } = sizing(col)
              const canSort = sortable && col.sortable !== false
              const sorted = sort?.key === col.key ? sort.direction : null
              return (
                <th
                  key={col.key}
                  scope="col"
                  style={style}
                  className={cn(col.grow && !columnWidths[col.key] && 'lv-grow', capped && 'lv-capped', floor && 'lv-floor')}
                  aria-sort={canSort ? (SORT[sorted] || 'none') : undefined}
                >
                  {canSort ? (
                    <button type="button" className="lv-sort" onClick={() => onSort(col.key)}>
                      {col.header || col.label}
                      {sorted && (sorted === 'asc'
                        ? <CaretUp size={12} weight="bold" aria-hidden="true" />
                        : <CaretDown size={12} weight="bold" aria-hidden="true" />)}
                    </button>
                  ) : (col.header || col.label)}
                  {setColumnWidth && (
                    <span
                      className={cn('lv-resize', resizing === col.key && 'is-active')}
                      onMouseDown={(e) => beginResize(e, col.key)}
                      onDoubleClick={(e) => { e.stopPropagation(); resetColumnWidth?.(col.key) }}
                    />
                  )}
                </th>
              )
            })}
            {hasActions && <th scope="col" className="lv-col-actions"><span className="sr-only">{t('common.actions')}</span></th>}
          </tr>
        </thead>
        <tbody>
          {loading ? Array.from({ length: skeletonRows }, (_, i) => (
            <tr key={`sk-${i}`} className="lv-sk-row" aria-hidden={i > 0 || undefined}>
              {multiSelect && <td className="lv-col-check"><div className="lv-cell"><SkeletonBar kind="box" /></div></td>}
              {columns.map((col) => {
                const { style, capped, floor } = sizing(col)
                return (
                  <td key={col.key} style={style}
                    className={cn(col.grow && !columnWidths[col.key] && 'lv-grow', capped && 'lv-capped', floor && 'lv-floor')}>
                    <div className="lv-cell">
                      {i === 0 && col === columns[0] && <span className="sr-only" role="status">{t('table.loadingRows')}</span>}
                      <SkeletonBar kind={col.skeleton === 'pill' ? 'pill' : undefined} width={skBar(col, i)} />
                    </div>
                  </td>
                )
              })}
              {hasActions && <td className="lv-col-actions" />}
            </tr>
          )) : !data.length && emptyContent ? (
            <tr className="lv-empty-row">
              <td className="lv-empty-cell" colSpan={columns.length + (multiSelect ? 1 : 0) + (hasActions ? 1 : 0)}>{emptyContent}</td>
            </tr>
          ) : data.map((row, idx) => {
            const name = nameOf(row)
            const checked = multiSelect && (selectedIds?.has(row.id) || false)
            const actions = rowActions?.(row) || []
            return (
              <tr
                key={row.id || idx}
                onClick={onRowClick ? (e) => {
                  // From the name only, when the name and the chevron are what opens the row
                  if (openFromName && !e.target.closest?.('.lv-entity')) return
                  if (!locked) onRowClick(row)
                } : undefined}
                className={cn(onRowClick && !openFromName && 'is-clickable', selectedId === row.id && 'is-opened', checked && 'is-checked')}
              >
                {multiSelect && (
                  <td className="lv-col-check" onClick={(e) => e.stopPropagation()}>
                    <label className="lv-check">
                      <input
                        type="checkbox"
                        aria-label={t('table.selectRow', { name })}
                        checked={checked}
                        onChange={() => onToggleRow(row.id)}
                      />
                    </label>
                  </td>
                )}
                {columns.map((col) => {
                  const { clip, capped, floor, style } = sizing(col)
                  const raw = row[col.key]
                  const content = col.render ? col.render(raw, row, { locked }) : (raw ?? '—')
                  const tip = col.title ? col.title(row) : raw
                  return (
                    <td
                      key={col.key}
                      style={style}
                      className={cn(
                        col.grow && !columnWidths[col.key] && 'lv-grow',
                        capped && 'lv-capped',
                        floor && 'lv-floor',
                        clip && 'is-clipped',
                        col.muted && 'is-muted',
                        col.small && 'is-small',
                        col.mono && 'font-mono',
                        col.className
                      )}
                    >
                      {col.fill
                        ? <div className="lv-cell lv-fill">{content}</div>
                        : clip
                          ? <div className="lv-clip" title={typeof tip === 'string' && tip ? tip : undefined}>{content}</div>
                          : <div className="lv-cell">{content}</div>}
                    </td>
                  )
                })}
                {hasActions && (
                  <td className="lv-col-actions">
                    <div className="lv-row-actions">
                      {actions.map((action, i) => {
                        const Icon = action.icon
                        return (
                          <button
                            key={i}
                            type="button"
                            className="lv-icon-btn"
                            title={action.label}
                            aria-label={t('table.rowAction', { action: action.label, name })}
                            disabled={locked}
                            onClick={(e) => { e.stopPropagation(); action.onClick?.() }}
                          >
                            {Icon && <Icon size={14} aria-hidden="true" />}
                          </button>
                        )
                      })}
                      {onRowClick && (
                        <button
                          type="button"
                          className="lv-icon-btn"
                          title={t('table.open')}
                          aria-label={t('table.openRow', { name })}
                          disabled={locked}
                          onClick={(e) => { e.stopPropagation(); onRowClick(row) }}
                        >
                          <CaretRight size={14} aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default ListTable
