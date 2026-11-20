/**
 * Page head of the list template: title, total in words, one sentence of intent,
 * page actions on the right with the main one last. Help lives in the top bar.
 */
import { cn } from '../../lib/utils'
import './list.css'

export function PageHead({ title, total, intent, actions, className }) {
  return (
    <header className={cn('lv-head', className)}>
      <div className="lv-head-text">
        <div className="lv-title-line">
          <h1>{title}</h1>
          {total !== undefined && total !== null && total !== '' && <span className="lv-total">{total}</span>}
        </div>
        {intent && <p className="lv-intent">{intent}</p>}
      </div>
      {actions && <div className="lv-actions">{actions}</div>}
    </header>
  )
}

/** Button of the template: `primary` for the page's main action, `quiet` for a secondary one; a labelled icon is 17 px, a lone one 16. */
export function ListButton({ icon: Icon, primary = false, quiet = false, small = false, className, children, type = 'button', ...props }) {
  return (
    <button
      type={type}
      className={cn('lv-btn', primary && 'is-primary', quiet && 'is-quiet', small && 'is-small', !children && 'is-icon', className)}
      {...props}
    >
      {Icon && <Icon size={small ? 14 : children ? 17 : 16} aria-hidden="true" />}
      {children}
    </button>
  )
}

export default PageHead
