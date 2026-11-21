/**
 * The mockup's statusFilters() and the state chips of listView(): one toggle button per state
 * with its counter (a bar while the counters are read), and the aside on the right (a reference
 * date, or a link that clears the search and filters).
 */
import { useTranslation } from 'react-i18next'

/**
 * @param {Array<{id: string, label: string, count?: number, warn?: boolean}>} views
 * @param {string} active
 * @param {(id: string) => void} onChange
 * @param {string} label  accessible name of the group
 */
export function StateFilters({ views, active, onChange, label, aside, busy = false }) {
  const { i18n } = useTranslation()
  const number = new Intl.NumberFormat(i18n?.language || undefined)
  return (
    <div className="filters-row">
      <div className="views" role="group" aria-label={label}>
        {views.map((v) => (
          <button key={v.id} type="button" className={v.id === active ? 'view-btn active' : 'view-btn'} data-status={v.id}
            aria-pressed={v.id === active} onClick={() => onChange?.(v.id)}>
            {v.warn && <span className="dot warn" aria-hidden="true" />}
            {v.label}
            {v.count !== undefined && (
              <span className="counter">{busy ? <span className="sk sk-num" style={{ width: '14px' }} /> : number.format(v.count)}</span>
            )}
          </button>
        ))}
      </div>
      <div className="active-filters">{aside}</div>
    </div>
  )
}

export default StateFilters
