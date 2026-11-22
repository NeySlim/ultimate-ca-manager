/**
 * Small pieces the protocol pages draw with the mockup's classes: a copyable value (mono value and
 * the quiet copy button of the HSM configuration), a field (the mockup's .field: label, control,
 * hint), a checkbox line, a list of URLs with copy and remove, and the views of a module that holds
 * more than the mockup's list (a row of tabs under the page head).
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react'
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
 * The views of a protocol page that holds more than the mockup's list: a row of tabs under the page
 * head (the mockup's .view-btn with its .counter), then the panel they control (`children`). Groups
 * stand apart with the toolbar's .tools-divider, each tab described by its group's name. A row wider
 * than the page scrolls on its own, a shadow on the edge that hides tabs.
 * options/groups: { value, label, count? } where count null is a counter being read.
 */
export function ViewSwitch({ id, label, value, onChange, options = [], groups = [], children }) {
  const { i18n } = useTranslation()
  const number = new Intl.NumberFormat(i18n?.language || undefined)
  const rowRef = useRef(null)
  const [edges, setEdges] = useState({ start: false, end: false })
  const sets = [...(options.length ? [{ options }] : []), ...groups]
  const all = sets.flatMap((g) => g.options)
  const values = all.map((o) => o.value)
  const tabId = (v) => `${id}-tab-${v}`
  const panelId = `${id}-panel`

  const measure = useCallback(() => {
    const row = rowRef.current
    if (!row) return
    const start = row.scrollLeft > 1
    const end = row.scrollLeft + row.clientWidth < row.scrollWidth - 1
    setEdges((e) => (e.start === start && e.end === end ? e : { start, end }))
  }, [])

  // Measured after each render too: counters arriving widen the tabs, not the row
  useEffect(measure)
  useEffect(() => {
    const row = rowRef.current
    if (!row) return undefined
    // A mouse wheel scrolls a row that overflows, until its end lets the page take the wheel again
    const wheel = (e) => {
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return
      const max = row.scrollWidth - row.clientWidth
      if (max <= 0 || (e.deltaY < 0 && row.scrollLeft <= 0) || (e.deltaY > 0 && row.scrollLeft >= max - 1)) return
      e.preventDefault()
      row.scrollLeft += e.deltaY
    }
    row.addEventListener('wheel', wheel, { passive: false })
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    observer?.observe(row)
    return () => { observer?.disconnect(); row.removeEventListener('wheel', wheel) }
  }, [measure])

  // The shown tab stays inside the row, clear of the edge shadow
  useEffect(() => {
    const row = rowRef.current
    const tab = document.getElementById(tabId(value))
    if (!row || !tab || !row.contains(tab)) return
    const left = tab.offsetLeft
    const right = left + tab.offsetWidth
    const to = left < row.scrollLeft + EDGE ? left - EDGE
      : right > row.scrollLeft + row.clientWidth - EDGE ? right - row.clientWidth + EDGE : null
    if (to !== null && row.scrollWidth > row.clientWidth) row.scrollTo?.({ left: Math.max(0, to), behavior: smooth() })
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps

  const onKey = (e) => {
    const n = values.length
    const i = values.indexOf(value)
    const to = { ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1 }[e.key]
    if (to === undefined) return
    e.preventDefault()
    onChange(values[to])
    requestAnimationFrame(() => document.getElementById(tabId(values[to]))?.focus())
  }

  return (
    <>
      <div className="page-views" data-more-start={edges.start ? '' : undefined} data-more-end={edges.end ? '' : undefined}>
        <div className="page-views-row" role="tablist" aria-label={label} ref={rowRef} onScroll={measure}>
          {sets.map((g, gi) => [
            gi > 0 && <span key={`div-${gi}`} className="tools-divider" aria-hidden="true" />,
            ...g.options.map((o) => (
              <button key={o.value} type="button" role="tab" id={tabId(o.value)} className={o.value === value ? 'view-btn active' : 'view-btn'}
                aria-selected={o.value === value} aria-controls={panelId} tabIndex={o.value === value ? 0 : -1}
                aria-describedby={g.label ? `${id}-group-${gi}` : undefined} onClick={() => onChange(o.value)} onKeyDown={onKey}>
                {o.label}
                {o.count !== undefined && (
                  <span className="counter">{o.count === null ? <span className="sk sk-num" style={{ width: '14px' }} /> : number.format(o.count)}</span>
                )}
              </button>
            )),
          ])}
        </div>
        {sets.map((g, gi) => g.label && <span key={gi} id={`${id}-group-${gi}`} hidden>{g.label}</span>)}
      </div>
      <div className="view-panel" role="tabpanel" id={panelId} aria-labelledby={tabId(value)}>{children}</div>
    </>
  )
}

// The width of the edge shadow: a tab brought into the row clears it
const EDGE = 24
const smooth = () => (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth')

/** The mockup's yesNo(): a check and Oui, or a block sign and Non, in a flag. */
export function YesNo({ value }) {
  const { t } = useTranslation()
  return value
    ? <span className="flag"><Icon name="check" />{t('common.yes')}</span>
    : <span className="flag muted"><Icon name="block" />{t('common.no')}</span>
}
