/**
 * State tabs with counters: one view of the list per state, replacing stat tiles
 * and a status dropdown. Arrow keys, Home and End move between tabs; Enter or
 * Space selects the focused one.
 */
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '../../lib/utils'
import { viewTabId } from './viewTabId'
import './list.css'

/**
 * @param {Array<{id: string, label: string, count?: number, tone?: 'warn'}>} views
 * @param {string|null} active  id of the selected view; null when the state on screen is no single view
 * @param {(id: string) => void} onChange
 * @param {string} label  accessible name of the tab list
 * @param {string} [baseId]  prefix of the tab ids; `controls` is the id of the panel they filter
 */
export function StateTabs({ views = [], active, onChange, label, baseId = 'lv-view', controls, aside, className }) {
  const { i18n } = useTranslation()
  const refs = useRef([])
  const number = new Intl.NumberFormat(i18n?.language || undefined)
  const selected = views.findIndex((v) => v.id === active)
  // One tab stop: the selected tab, or the first when none is
  const stop = selected >= 0 ? selected : 0

  const onKeyDown = (e, index) => {
    const last = views.length - 1
    const next = { ArrowRight: index === last ? 0 : index + 1, ArrowLeft: index === 0 ? last : index - 1, Home: 0, End: last }[e.key]
    if (next === undefined) return
    e.preventDefault()
    refs.current[next]?.focus()
  }

  return (
    <div className={cn('lv-views-row', className)}>
      <div className="lv-views" role="tablist" aria-label={label}>
        {views.map((view, index) => (
          <button
            key={view.id}
            ref={(el) => { refs.current[index] = el }}
            type="button"
            role="tab"
            id={viewTabId(baseId, view.id)}
            aria-selected={index === selected}
            aria-controls={controls}
            tabIndex={index === stop ? 0 : -1}
            className="lv-view"
            onClick={() => onChange?.(view.id)}
            onKeyDown={(e) => onKeyDown(e, index)}
          >
            {view.tone === 'warn' && <span className="lv-dot" aria-hidden="true" />}
            {view.label}
            {typeof view.count === 'number' && <span className="lv-counter">{number.format(view.count)}</span>}
          </button>
        ))}
      </div>
      {aside && <div className="lv-views-aside">{aside}</div>}
    </div>
  )
}

export default StateTabs
