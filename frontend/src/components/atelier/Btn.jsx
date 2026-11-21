/**
 * Buttons of the mockup: `.btn` (primary, quiet, danger), `.icon-btn` (quiet) and `.text-link`.
 * A primary or danger button is a write for the central write guard (data-write) unless `write`
 * says otherwise; any other button is one only when `write` is set.
 */
import { forwardRef } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from './Icon'

const writeMark = (write, tone) => {
  if (write === true) return ''
  if (write === false) return tone === 'primary' || tone === 'danger' ? 'false' : undefined
  return tone === 'primary' || tone === 'danger' ? '' : undefined
}
const btnClass = (tone) => ['btn', tone].filter(Boolean).join(' ')

/** tone: 'primary' | 'quiet' | 'danger'; `to` draws a link styled as the button. */
export const Btn = forwardRef(function Btn({ icon, tone, write, to, children, type = 'button', ...rest }, ref) {
  const mark = writeMark(write, tone)
  if (to) {
    return <Link ref={ref} className={btnClass(tone)} to={to} data-write={mark} {...rest}>{icon && <Icon name={icon} />}{children}</Link>
  }
  return (
    <button ref={ref} type={type} className={btnClass(tone)} data-write={mark} {...rest}>
      {icon && <Icon name={icon} />}{children}
    </button>
  )
})

/** An icon alone: its accessible name is `label`, shown as its tooltip unless `title` is false. */
export const IconBtn = forwardRef(function IconBtn({ icon, label, quiet = false, title = true, write, children, type = 'button', ...rest }, ref) {
  return (
    <button ref={ref} type={type} className={quiet ? 'icon-btn quiet' : 'icon-btn'} aria-label={label}
      title={title === true ? label : title || undefined} data-write={write ? '' : undefined} {...rest}>
      <Icon name={icon} />{children}
    </button>
  )
})

/** `.text-link`: a button, or a link with `to`; the icon follows the words unless `iconFirst`. */
export const TextLink = forwardRef(function TextLink({ icon, iconFirst = false, to, children, type = 'button', ...rest }, ref) {
  const body = iconFirst ? <>{icon && <Icon name={icon} />}{children}</> : <>{children}{icon && <> <Icon name={icon} /></>}</>
  // The mockup draws these as buttons: the link keeps their box (extensions.css, a.text-link[data-link])
  if (to) return <Link ref={ref} className="text-link" data-link="" to={to} {...rest}>{body}</Link>
  return <button ref={ref} type={type} className="text-link" {...rest}>{body}</button>
})
