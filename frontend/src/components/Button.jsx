import { Children, forwardRef, isValidElement } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '../lib/utils'
import './list/list.css'

/**
 * Button of the Atelier mockup (`.btn`): 32 px, radius 4, 12 px/500, on the list
 * template's `.lv-btn` so every button of the application has one geometry.
 * `primary`/`success` fill with the accent, `secondary`/`outline` are bordered,
 * `ghost` is quiet, `danger`/`danger-soft` and `warning-soft` take the tone's colours.
 * `xs` is the 26 px button of compact bars; `sm`, `default` and `lg` are all 32 px.
 */
const VARIANTS = {
  primary: 'is-primary',
  success: 'is-primary',
  secondary: '',
  outline: '',
  ghost: 'is-quiet',
  danger: 'is-danger',
  'danger-soft': 'is-danger',
  'warning-soft': 'is-warn',
}

const SIZES = { xs: 'is-small', sm: '', default: '', lg: '' }

// A lone icon with an accessible name is the mockup's 32 px square icon button.
function isIconOnly(children, props) {
  if (!props['aria-label'] && !props.title) return false
  const kids = Children.toArray(children)
  return kids.length === 1 && isValidElement(kids[0]) && typeof kids[0].type !== 'string'
}

// `type` defaults to 'button', not the HTML default of 'submit': every one of
// the 91 buttons inside a form already passes one explicitly, and the first
// omission would submit the form instead of opening a modal, silently.
export const Button = forwardRef(function Button({ children, type = 'button', variant = 'primary', size = 'sm', loading = false, loadingText, className, ...props }, ref) {
  const { t } = useTranslation()
  const iconOnly = !loading && isIconOnly(children, props)

  return (
    <button
      ref={ref}
      type={type}
      {...props}
      className={cn(
        'lv-btn ui-btn',
        VARIANTS[variant] ?? '',
        SIZES[size] ?? '',
        iconOnly && 'is-icon',
        loading && 'is-loading',
        className
      )}
      // Must stay AFTER the spread: a caller passing both `loading` and an
      // explicit `disabled` would otherwise have its own `disabled={false}`
      // overwrite the guard, leaving the button live during the request.
      disabled={loading || props.disabled}
    >
      {loading ? (
        <>
          <svg className="ui-spin" viewBox="0 0 24 24" aria-hidden="true">
            <circle opacity="0.25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path opacity="0.75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span>{loadingText || t('common.loading')}</span>
        </>
      ) : children}
    </button>
  )
})
