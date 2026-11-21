/**
 * The toolbar of the mockup's tableView() and activity(): a search field, filter selects, a
 * divider, then the tools (Colonnes, density, export). Each piece is its own component so a
 * page lines up only what it has.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Icon } from './Icon'

/** Short of room: the search field at its floor (the copied min-width), or the tools overflowing. */
function cramped(el) {
  const search = el.querySelector(':scope > .search')
  const floor = search ? parseFloat(getComputedStyle(search).minWidth) || 0 : 0
  return el.scrollWidth > el.clientWidth + 1 || (!!search && floor > 0 && search.offsetWidth <= floor + 1)
}

/**
 * Beside the dock anchored at the right (#app.dock-right), a toolbar short of room folds as the mockup's
 * phone toolbar: the search on its own line, the filters and tools on the next. A change of width unfolds
 * it and measures again, before the browser paints.
 */
function useFoldedToolbar(ref) {
  const [folded, setFolded] = useState(false)
  const [width, setWidth] = useState(0)
  const measured = useRef(width)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => setWidth(el.clientWidth))
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])
  useLayoutEffect(() => {
    const el = ref.current
    const right = !!el?.closest('.dock-right')
    if (!right || measured.current !== width) {
      measured.current = width
      if (folded) { setFolded(false); return }
    }
    if (right && !folded && cramped(el)) setFolded(true)
  })
  return folded
}

export function Toolbar({ children }) {
  const ref = useRef(null)
  const folded = useFoldedToolbar(ref)
  return <div ref={ref} className={folded ? 'toolbar folded' : 'toolbar'}>{children}</div>
}

/** `.search`: the field, its hidden label and the live count of results when the server searches. */
export function SearchField({ id, name, label, placeholder, value, onChange, onKeyDown, status }) {
  return (
    <>
      <label className="search">
        <Icon name="search" />
        <span className="sr-only">{label}</span>
        <input id={id} type="search" name={name} placeholder={placeholder} value={value} autoComplete="off" spellCheck={false}
          onChange={(e) => onChange?.(e.target.value)} onKeyDown={onKeyDown} />
      </label>
      {status !== undefined && <span className="search-status" id={id ? `${id}-status` : undefined} aria-live="polite">{status}</span>}
    </>
  )
}

/** options: [{ value, label }]; groups: [{ label, options }] drawn as optgroups after the options. */
export function FilterSelect({ id, label, value, onChange, options = [], groups = [] }) {
  return (
    <select className="filter-select" id={id} aria-label={label} value={value} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      {groups.map((g) => (
        <optgroup key={g.label} label={g.label}>
          {g.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </optgroup>
      ))}
    </select>
  )
}

export function ToolsDivider() {
  return <span className="tools-divider" />
}

/** The Colonnes button: the label hides on a narrow screen, as the mockup's. */
export function ColumnsButton({ label, onClick }) {
  return (
    <button type="button" className="btn columns-button" data-action="columns" onClick={onClick}>
      <Icon name="columns" /><span>{label}</span>
    </button>
  )
}

/** The density toggle: pressed when the rows are comfortable. */
export function DensityButton({ label, title, pressed, onClick }) {
  return (
    <button type="button" className="icon-btn density-button display-button" data-action="density" aria-label={label}
      aria-pressed={pressed} title={title} onClick={onClick}>
      <Icon name="rows" />
    </button>
  )
}
