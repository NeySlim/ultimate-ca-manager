/**
 * ListTable: the desktop table of the list template (ResponsiveDataTable variant="list").
 * Columns take the width of their content and the `grow` column absorbs the rest, so a
 * name is never cut while there is room; every row keeps one height; a row carries its
 * checkbox, its own actions and a chevron that opens the detail.
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { CaretUp, CaretDown, CaretRight } from '@phosphor-icons/react'
import { cn } from '../../../lib/utils'
import '../../list/list.css'

const SORT = { asc: 'ascending', desc: 'descending' }

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

  // A width set by hand or capped by the column clips its cell; the others follow their content
  const sizing = (col) => {
    const px = columnWidths[col.key]
    if (px) return { clip: true, style: { width: px, minWidth: px, maxWidth: px } }
    if (col.grow) return { clip: true, style: undefined }
    if (col.maxWidth) return { clip: true, style: { maxWidth: col.maxWidth } }
    return { clip: false, style: undefined }
  }

  const nameOf = (row) => rowLabel?.(row) ?? ''
  const hasActions = Boolean(rowActions || onRowClick)
  const span = columns.length + (hasActions ? 1 : 0) + (multiSelect ? 1 : 0)

  return (
    <div className="lv-scroll" role="region" tabIndex={0} aria-label={label}>
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
              const { style } = sizing(col)
              const canSort = sortable && col.sortable !== false
              const sorted = sort?.key === col.key ? sort.direction : null
              return (
                <th
                  key={col.key}
                  scope="col"
                  style={style}
                  className={cn(col.grow && !columnWidths[col.key] && 'lv-grow')}
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
          {loading ? (
            <tr><td colSpan={span}><div className="lv-loading" role="status">{t('common.loading')}</div></td></tr>
          ) : data.map((row, idx) => {
            const name = nameOf(row)
            const checked = multiSelect && (selectedIds?.has(row.id) || false)
            const actions = rowActions?.(row) || []
            return (
              <tr
                key={row.id || idx}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cn(onRowClick && 'is-clickable', selectedId === row.id && 'is-opened', checked && 'is-checked')}
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
                  const { clip, style } = sizing(col)
                  const raw = row[col.key]
                  const content = col.render ? col.render(raw, row) : (raw ?? '—')
                  const tip = col.title ? col.title(row) : raw
                  return (
                    <td
                      key={col.key}
                      style={style}
                      className={cn(
                        col.grow && !columnWidths[col.key] && 'lv-grow',
                        clip && 'is-clipped',
                        col.muted && 'is-muted',
                        col.small && 'is-small',
                        col.mono && 'font-mono',
                        col.className
                      )}
                    >
                      {clip
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
                            onClick={(e) => { e.stopPropagation(); action.onClick?.() }}
                          >
                            {Icon && <Icon size={15} aria-hidden="true" />}
                          </button>
                        )
                      })}
                      {onRowClick && (
                        <button
                          type="button"
                          className="lv-icon-btn"
                          title={t('table.open')}
                          aria-label={t('table.openRow', { name })}
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
