/**
 * The toolbar of the mockup's tableView() and activity(): a search field, filter selects, a
 * divider, then the tools (Colonnes, density, export). Each piece is its own component so a
 * page lines up only what it has.
 */
import { Icon } from './Icon'

export function Toolbar({ children }) {
  return <div className="toolbar">{children}</div>
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
