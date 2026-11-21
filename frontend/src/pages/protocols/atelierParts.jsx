/**
 * Small pieces the protocol pages draw with the mockup's classes: a copyable value (mono value and
 * the quiet copy button of the HSM configuration), a field (the mockup's .field: label, control,
 * hint), a checkbox line, a list of URLs with copy and remove, and the page switch of a module that
 * holds more than the mockup's list (a select in the page head, labelled for screen readers).
 */
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon, IconBtn, Btn } from '../../components/atelier'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks'

/** A value in mono, then the quiet copy button; « — » when there is none. */
export function Copyable({ value, label, url = false }) {
  const { t } = useTranslation()
  const { copy } = useClipboard()
  const { showSuccess } = useNotification()
  if (!value) return '—'
  return (
    <>
      <span className={url ? 'mono url' : 'mono'}>{value}</span>{' '}
      <IconBtn quiet icon="copy" label={t('protocols.copyValue', { name: label })}
        onClick={async () => { if (await copy(value)) showSuccess(t('common.copied')) }} />
    </>
  )
}

/**
 * The mockup's form field: label, control (children get `id` and `aria-describedby`), hint, error.
 * `full` spans both columns of .form-fields, `short` takes the narrow width.
 */
export function Field({ label, hint, error, full = false, short = false, children, id: given }) {
  const auto = useId()
  const id = given || `f${auto.replace(/:/g, '')}`
  const ids = [hint && `hint-${id}`, error && `err-${id}`].filter(Boolean).join(' ') || undefined
  const control = typeof children === 'function' ? children({ id, 'aria-describedby': ids, 'aria-invalid': error ? 'true' : undefined }) : children
  return (
    <div className={['field', full ? 'full' : short ? 'short' : ''].filter(Boolean).join(' ')}>
      <label htmlFor={id}>{label}</label>
      {control}
      {hint && <small id={`hint-${id}`}>{hint}</small>}
      {error && <p className="field-error" id={`err-${id}`}><Icon name="warning" /><span>{error}</span></p>}
    </div>
  )
}

/** A checkbox and its words on one line (the mockup's .checkbox-line). */
export function CheckLine({ checked, onChange, disabled, children, id }) {
  return (
    <label className="checkbox-line">
      <input type="checkbox" id={id} checked={!!checked} disabled={disabled || undefined} onChange={(e) => onChange?.(e.target.checked)} />
      {children}
    </label>
  )
}

/** A notice of the mockup: help (muted) or warn. */
export function Notice({ tone, icon, children, id, role }) {
  return (
    <p className={tone ? `notice ${tone}` : 'notice'} id={id} role={role}>
      <Icon name={icon || (tone === 'warn' || tone === 'bad' ? 'warning' : 'help')} /><span>{children}</span>
    </p>
  )
}

/**
 * URLs as record rows: the URL in mono, copy, and remove when allowed; then the field to add one.
 */
export function UrlList({ urls = [], label, onRemove, adding, onAdding, onAdd, busy, placeholder, empty }) {
  const { t } = useTranslation()
  const { copy } = useClipboard()
  const { showSuccess } = useNotification()
  return (
    <>
      {urls.length ? (
        <ul className="record-list">
          {urls.map((url, i) => (
            <li key={`${url}-${i}`}>
              <div className="rl-main"><span className="mono url">{url}</span></div>
              <div className="rl-action">
                <IconBtn quiet icon="copy" label={t('protocols.copyValue', { name: label })}
                  onClick={async () => { if (await copy(url)) showSuccess(t('common.copied')) }} />
                {onRemove && <IconBtn quiet icon="close" write label={t('protocols.removeUrl', { url })} disabled={busy || undefined} onClick={() => onRemove(i)} />}
              </div>
            </li>
          ))}
        </ul>
      ) : empty !== undefined && <p className="muted small">{empty}</p>}
      {onAdd && (adding !== null ? (
        <div className="url-add">
          <Field label={t('protocols.newUrl', { name: label })}>
            {(p) => (
              <input {...p} type="url" className="mono" placeholder={placeholder} value={adding} autoFocus
                onChange={(e) => onAdding(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { e.preventDefault(); onAdd() }
                  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onAdding(null) }
                }} />
            )}
          </Field>
          <div className="copy-url">
            <Btn icon="plus" write disabled={busy || !adding.trim() || undefined} onClick={onAdd}>{t('crlOcsp.addUrl')}</Btn>{' '}
            <Btn onClick={() => onAdding(null)}>{t('common.cancel')}</Btn>
          </div>
        </div>
      ) : (
        <div className="copy-url"><Btn icon="plus" write onClick={() => onAdding('')}>{t('crlOcsp.addUrl')}</Btn></div>
      ))}
    </>
  )
}

/**
 * The page switch of a protocol page that holds more than the mockup's list: a select styled as the
 * mockup's toolbar filter, in the page head.
 */
export function ViewSwitch({ id, label, value, onChange, options = [], groups = [] }) {
  return (
    <>
      <label className="sr-only" htmlFor={id}>{label}</label>
      <select className="filter-select view-switch" id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        {groups.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </optgroup>
        ))}
      </select>
    </>
  )
}
