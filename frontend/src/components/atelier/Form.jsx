/**
 * The fields and dialogs of the mockup's forms (issueDialog(), setupDialog(), settingsField()):
 * `.field` (label, control, hint `small`, `.field-error`), `.checkbox-line`, a radio choice in
 * `.choice-grid` of `.format-option`, `.form-fields`, `.modal-actions`. Input, Select, Textarea,
 * ToggleSwitch, Modal and FormModal keep the props of the product components they replace, so a
 * form moves to the mockup's markup by its import; `full` and `short` place a field in its grid.
 */
import { forwardRef, useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { Btn } from './Btn'
import { AtelierDialog } from './AtelierDialog'
import { FieldError } from './SettingsView'
import { Input as StrengthInput } from '../Input'

const join = (...c) => c.filter(Boolean).join(' ')
// The product's `sf-short` class placed a short field; it maps to the mockup's `.field.short`
const placeOf = ({ full, short, className }) => join('field', full && 'full', (short || /\bsf-short\b/.test(className || '')) && 'short')
const describedBy = (...ids) => ids.filter(Boolean).join(' ') || undefined

/** A labelled control of the mockup: hint under it, then the error that names it. */
export function Field({ id, label, hint, error, full, short, className, optional, children }) {
  return (
    <div className={placeOf({ full, short, className })}>
      {label && <label htmlFor={id}>{label}{optional && <span className="optional"> {optional}</span>}</label>}
      {children}
      {hint && <small id={`hint-${id}`}>{hint}</small>}
      {error && <FieldError id={`err-${id}`} message={error} />}
    </div>
  )
}

/**
 * A text input. hasExistingValue: a stored secret, shown as a masked placeholder with the hint
 * that typing replaces it. showStrength keeps the product's server-scored meter (no gabarit in the mockup).
 */
// eslint-disable-next-line no-unused-vars
export const Input = forwardRef(function Input({ label, error, helperText, hint, full, short, className, id, hasExistingValue, showStrength, mono, noAutofill, icon, ...rest }, ref) {
  const { t } = useTranslation()
  const auto = useId()
  const fid = id ?? auto
  if (showStrength) return <StrengthInput ref={ref} label={label} error={error} helperText={helperText ?? hint} id={id} showStrength hasExistingValue={hasExistingValue} {...rest} />
  const note = hasExistingValue ? t('common.enterNewToChange') : (helperText ?? hint)
  const placeholder = hasExistingValue && rest.type === 'password' ? '••••••••••••' : rest.placeholder
  return (
    <Field id={fid} label={label} hint={note} error={error} full={full} short={short} className={className}>
      <input ref={ref} autoComplete="off" spellCheck={false} {...rest} placeholder={placeholder} id={fid} className={mono ? 'mono' : undefined}
        required={rest.required && !hasExistingValue} aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy(note && `hint-${fid}`, error && `err-${fid}`, rest['aria-describedby'])} />
    </Field>
  )
})

/**
 * A whole number as the mockup types one (settingsField `numeric`): a text input in numeric mode,
 * a short field by default; onChange receives the event, the page checks the bounds at the save.
 */
export const NumberInput = forwardRef(function NumberInput({ short = true, ...rest }, ref) {
  return <Input ref={ref} inputMode="numeric" short={short} {...rest} />
})

/** A secret: masked, never offered by the browser's autofill; a stored one shows as a masked placeholder. */
export const SecretInput = forwardRef(function SecretInput(props, ref) {
  return <Input ref={ref} type="password" autoComplete="new-password" {...props} />
})

const splitList = (text) => text.split(',').map((v) => v.trim()).filter(Boolean)

/**
 * A list typed as the mockup's recipients field (scheduleDialog `sch-to`): entries separated by
 * commas. onChange receives the entries `validate` accepts; one it refuses is named under the
 * field once the field is left, and is not kept.
 */
export function ListInput({ value = [], onChange, validate, invalidMessage, id, ...rest }) {
  const auto = useId()
  const fid = id ?? auto
  const joined = value.join(', ')
  const [text, setText] = useState(joined)
  const [bad, setBad] = useState([])
  // A value set from outside (a reset, a load) replaces what is typed
  const last = useRef(joined)
  useEffect(() => {
    if (joined !== last.current && splitList(text).join(', ') !== joined) setText(joined)
    last.current = joined
  }, [joined]) // eslint-disable-line react-hooks/exhaustive-deps
  const change = (e) => {
    setText(e.target.value)
    const all = splitList(e.target.value)
    const ok = validate ? all.filter(validate) : all
    if (ok.join(', ') !== joined) { last.current = ok.join(', '); onChange?.(ok) }
    if (bad.length) setBad(validate ? all.filter((v) => !validate(v)) : [])
  }
  const leave = () => setBad(validate ? splitList(text).filter((v) => !validate(v)) : [])
  return (
    <Input id={fid} value={text} onChange={change} onBlur={leave} error={bad.length ? invalidMessage?.(bad) : undefined} {...rest} />
  )
}

/**
 * A native select; onChange receives the value, as the product's Select did. A placeholder is an
 * empty first entry when no option is empty. `searchable` is accepted: the native list types ahead.
 */
// eslint-disable-next-line no-unused-vars
export function Select({ label, options = [], value, onChange, placeholder, error, disabled, helperText, hint, full, short, className, id, searchable, ...rest }) {
  const auto = useId()
  const fid = id ?? auto
  const note = helperText ?? hint
  const empty = !options.some((o) => o.value === '' || o.value === null)
  return (
    <Field id={fid} label={label} hint={note} error={error} full={full} short={short} className={className}>
      <select id={fid} value={value ?? ''} disabled={disabled} onChange={(e) => onChange?.(e.target.value)} aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy(note && `hint-${fid}`, error && `err-${fid}`)} {...rest}>
        {empty && (placeholder || value === '' || value == null) && <option value="" disabled>{placeholder || ''}</option>}
        {options.map((o) => <option key={String(o.value)} value={o.value ?? ''} disabled={o.disabled}>{o.label}</option>)}
      </select>
    </Field>
  )
}

/** A textarea; `mono` sets it in the mockup's monospace (keys, PEM, scripts). */
// eslint-disable-next-line no-unused-vars
export function Textarea({ label, error, helperText, hint, full = true, short, className, id, mono, showCount, maxLength, value = '', ...rest }) {
  const auto = useId()
  const fid = id ?? auto
  const note = helperText ?? hint
  return (
    <Field id={fid} label={label} hint={note} error={error} full={full} short={short} className={className}>
      <textarea id={fid} value={value} maxLength={maxLength} className={mono ? 'mono' : undefined} aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy(note && `hint-${fid}`, error && `err-${fid}`)} {...rest} />
    </Field>
  )
}

/** A setting on or off: the mockup's `.checkbox-line`; a description becomes the field's hint. */
// eslint-disable-next-line no-unused-vars
export function ToggleSwitch({ checked = false, onChange, disabled = false, size, label, description, className, id, ...rest }) {
  const auto = useId()
  const fid = id ?? auto
  const box = (
    <input type="checkbox" id={fid} checked={!!checked} disabled={disabled} onChange={(e) => { if (!disabled) onChange?.(e.target.checked) }}
      aria-describedby={description ? `hint-${fid}` : undefined} {...rest} />
  )
  if (!label) return box
  if (!description) return <label className={join('checkbox-line field full', className)}>{box}{label}</label>
  return (
    <div className={join('field full', className)}>
      <label className="checkbox-line">{box}{label}</label>
      <small id={`hint-${fid}`}>{description}</small>
    </div>
  )
}

/**
 * A choice among a few values: the mockup's `.segmented` group of pressed buttons, named by the
 * field's label. `pressed(value)` says which are on; several may be (a set of days).
 */
export function SegmentedField({ id, label, hint, options, pressed, onPick, full = true, short, disabled }) {
  const auto = useId()
  const fid = id ?? auto
  return (
    <div className={placeOf({ full, short })}>
      <span id={`label-${fid}`}>{label}</span>
      <div className="segmented" role="group" aria-labelledby={`label-${fid}`} aria-describedby={hint ? `hint-${fid}` : undefined}>
        {options.map((o) => (
          <button key={String(o.value)} type="button" aria-pressed={pressed(o.value)} disabled={disabled || undefined} onClick={() => onPick(o.value)}>{o.label}</button>
        ))}
      </div>
      {hint && <small id={`hint-${fid}`}>{hint}</small>}
    </div>
  )
}

/** A choice of a few options: `fieldset.field.full`, its legend, `.choice-grid` of `.format-option` radios. */
export function ChoiceField({ name, legend, value, onChange, options, disabled, hint }) {
  const id = useId()
  return (
    <fieldset className="field full" aria-describedby={hint ? `hint-${id}` : undefined}>
      <legend>{legend}</legend>
      <div className="choice-grid">
        {options.map((o) => (
          <label key={o.value} className="format-option">
            <input type="radio" name={name} value={o.value} checked={value === o.value} disabled={disabled || o.disabled} onChange={() => onChange?.(o.value)} />
            <span>{o.label}{o.hint && <small>{o.hint}</small>}</span>
          </label>
        ))}
      </div>
      {hint && <small id={`hint-${id}`}>{hint}</small>}
    </fieldset>
  )
}

/**
 * A folded part of a form: the issue form's « Avancé » (`.field.full.advanced`), its toggle naming the
 * part (and a `sub` line), then the two-column panel. The fields stay mounted: a field the form
 * refuses (`invalid`) opens the part that holds it.
 */
export function Fold({ id, title, sub, defaultOpen = false, children }) {
  const auto = useId()
  const fid = id ?? `fold${auto.replace(/:/g, '')}`
  const [open, setOpen] = useState(defaultOpen)
  const root = useRef(null)
  useEffect(() => {
    const el = root.current
    const reveal = () => setOpen(true)
    el?.addEventListener('invalid', reveal, true)
    return () => el?.removeEventListener('invalid', reveal, true)
  }, [])
  return (
    <div className="field full advanced" ref={root}>
      <button type="button" className="advanced-toggle" id={`${fid}-toggle`} aria-expanded={open} aria-controls={fid} onClick={() => setOpen((v) => !v)}>
        <Icon name={open ? 'down' : 'right'} /><span>{title}</span>{sub && <small>{sub}</small>}
      </button>
      <div className="advanced-panel" id={fid} hidden={!open}>{children}</div>
    </div>
  )
}

export function FormFields({ children }) {
  return <div className="form-fields">{children}</div>
}

export function ModalActions({ children }) {
  return <div className="modal-actions">{children}</div>
}

/** The mockup's `.notice`, `warn` or `bad` with the warning icon, else the help icon; `role` announces it (a `bad` one is an alert). */
export function Notice({ tone, children, id, role }) {
  return <div className={join('notice', tone)} id={id} role={role ?? (tone === 'bad' ? 'alert' : undefined)}><Icon name={tone ? 'warning' : 'help'} /><span>{children}</span></div>
}

const SIZES = { sm: 'narrow', md: '', lg: 'wide', xl: 'wide' }

/** The product's Modal, drawn as the mockup's modal(): mounted while open. */
// eslint-disable-next-line no-unused-vars
export function Modal({ open, onClose, onOpenChange, title, subtitle, size = 'md', children, showClose, className, returnTo, testId }) {
  if (!open) return null
  const close = onClose || (() => onOpenChange?.(false))
  return <AtelierDialog title={title} subtitle={subtitle} size={SIZES[size] ?? ''} onClose={close} returnTo={returnTo} testId={testId}>{children}</AtelierDialog>
}

/**
 * The product's FormModal in the mockup's dialog: the fields in `.form-fields`, then Annuler and
 * the primary (or danger) submit under the rule. onSubmit gets the form's named values; a second
 * submit while the first runs is dropped.
 */
export function FormModal({
  open, onClose, onOpenChange, title, subtitle, size = 'md', onSubmit, submitLabel, submitIcon, cancelLabel,
  loading = false, disabled = false, variant = 'primary', children, footer, returnTo, testId,
}) {
  const { t } = useTranslation()
  const inFlight = useRef(false)
  if (!open) return null
  const close = onClose || (() => onOpenChange?.(false))
  const submit = async (e) => {
    e?.preventDefault()
    if (inFlight.current) return
    inFlight.current = true
    try {
      const form = e?.target
      if (form && onSubmit) await onSubmit(Object.fromEntries(new FormData(form).entries()))
      else await onSubmit?.()
    } finally {
      inFlight.current = false
    }
  }
  return (
    <AtelierDialog title={title} subtitle={subtitle} size={SIZES[size] ?? ''} onClose={close} returnTo={returnTo} testId={testId}>
      <form onSubmit={submit}>
        <div className="form-fields">{children}</div>
        {footer ?? (
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" disabled={loading || undefined} onClick={close}>{cancelLabel ?? t('common.cancel')}</button>
            <Btn type="submit" tone={variant === 'danger' ? 'danger' : 'primary'} icon={submitIcon || (variant === 'danger' ? undefined : 'check')}
              disabled={loading || disabled || undefined}>
              {loading ? t('common.saving') : (submitLabel ?? t('common.save'))}
            </Btn>
          </div>
        )}
      </form>
    </AtelierDialog>
  )
}

/** The product's ConfirmModal: a sentence, then Annuler and the confirming button. */
export function ConfirmModal({ open, onClose, onConfirm, title, message, confirmLabel, cancelLabel, variant = 'danger', loading = false }) {
  const { t } = useTranslation()
  if (!open) return null
  return (
    <AtelierDialog title={title ?? t('common.confirm')} size="narrow" onClose={onClose}>
      <p>{message}</p>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" disabled={loading || undefined} onClick={onClose}>{cancelLabel ?? t('common.cancel')}</button>
        <Btn tone={variant === 'danger' ? 'danger' : 'primary'} disabled={loading || undefined} onClick={onConfirm}>{confirmLabel ?? t('common.confirm')}</Btn>
      </div>
    </AtelierDialog>
  )
}

export default FormModal
