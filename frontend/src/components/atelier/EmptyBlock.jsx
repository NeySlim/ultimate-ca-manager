/**
 * The mockup's emptyBlock() and emptyAction(): never a blank page, but why the list is empty and
 * the next useful action; and the « nothing matches » block, whose action resets the filters.
 */
import { Icon } from './Icon'
import { Btn } from './Btn'

/**
 * action: { label, icon, onClick | to, primary, write } (`write`: held by the write guard).
 * id: the zone, as empty-<id>.
 */
export function EmptyBlock({ id, icon = 'file', title, text, action }) {
  return (
    <div className="empty empty-hint" id={id ? `empty-${id}` : undefined}>
      <Icon name={icon} />
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action && <EmptyAction {...action} />}
    </div>
  )
}

export function EmptyAction({ label, icon, onClick, to, primary = false, write }) {
  return <Btn tone={primary ? 'primary' : undefined} icon={icon} to={to} onClick={onClick} write={write}>{label}</Btn>
}

/** Nothing matches the search or the filters: `onReset` puts them back. `icon` false leaves it out. */
export function NoMatch({ title, text, resetLabel, onReset, icon = 'search' }) {
  return (
    <div className="empty">
      {icon && <Icon name={icon} />}
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {onReset && <button type="button" className="btn" data-action="reset-filters" onClick={onReset}>{resetLabel}</button>}
    </div>
  )
}

export default EmptyBlock
