/**
 * The list template on a phone, after the Atelier mobile records: per row a checkbox,
 * the name (the only control that opens, disabled while rows are ticked), the
 * description, a line of facts, then the state and an end value. `card(row)` gives
 * { description, meta: [], status, end }. With `chevron`, the whole record opens the row
 * and a chevron at its right reaches it from the keyboard.
 */
import { useTranslation } from 'react-i18next'
import { CaretRight } from '@phosphor-icons/react'
import { cn } from '../../../lib/utils'

export function ListCards({ data, card, rowLabel, label, onRowClick, multiSelect, selectedIds, onToggleRow, selectedId, locked, loading, emptyContent, skeletonRows = 6, chevron = false }) {
  const { t } = useTranslation()
  if (loading && !data.length) {
    return (
      <div className="lv-mlist" aria-busy="true">
        {Array.from({ length: skeletonRows }, (_, i) => (
          <div key={i} className="lv-mrecord" aria-hidden="true">
            <div className="lv-mrecord-top"><span className="lv-sk" style={{ width: `${50 + ((i * 17) % 35)}%` }} /></div>
            <div className="lv-mrecord-meta"><span className="lv-sk" style={{ width: '60%' }} /></div>
          </div>
        ))}
      </div>
    )
  }
  if (!data.length) return <div className="lv-mlist">{emptyContent}</div>
  return (
    <div className="lv-mlist" role="list" aria-label={label}>
      {data.map((row) => {
        const c = card(row) || {}
        const name = rowLabel ? rowLabel(row) : String(row.id)
        const checked = !!selectedIds?.has(row.id)
        const meta = (c.meta || []).filter((m) => m !== null && m !== undefined && m !== false && m !== '')
        return (
          <article key={row.id} role="listitem"
            className={cn('lv-mrecord', chevron && 'is-opening', checked && 'is-checked', selectedId === row.id && 'is-opened')}
            onClick={chevron ? (e) => {
              // The checkbox selects; the name and the chevron open through their own click
              if (locked || e.target.closest?.('.lv-check-hit, button')) return
              onRowClick?.(row)
            } : undefined}>
            <div className="lv-mrecord-top">
              {multiSelect && (
                <label className="lv-check-hit">
                  <input type="checkbox" checked={checked} aria-label={t('table.selectRow', { name })} onChange={() => onToggleRow?.(row.id)} />
                </label>
              )}
              <button type="button" className="lv-entity" disabled={locked} onClick={() => onRowClick?.(row)}>
                {c.icon}
                <span className="lv-entity-text">{name}</span>
              </button>
              {chevron && (
                <button type="button" className="lv-icon-btn lv-mrecord-open" title={t('table.open')}
                  aria-label={t('table.openRow', { name })} disabled={locked} onClick={() => onRowClick?.(row)}>
                  <CaretRight size={16} aria-hidden="true" />
                </button>
              )}
            </div>
            {c.description && <p className="lv-mrecord-desc">{c.description}</p>}
            {meta.length > 0 && <div className="lv-mrecord-meta">{meta.map((m, i) => <span key={i}>{m}</span>)}</div>}
            {(c.status || c.end) && (
              <div className="lv-mrecord-status">{c.status}<span className="lv-mrecord-end">{c.end}</span></div>
            )}
          </article>
        )
      })}
    </div>
  )
}

export default ListCards
