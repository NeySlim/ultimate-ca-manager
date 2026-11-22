/**
 * Small pieces the protocol pages draw with the mockup's classes: a copyable value (mono value and
 * the quiet copy button of the HSM configuration), a field (the mockup's .field: label, control,
 * hint), a checkbox line, a list of URLs with copy and remove, and the views of a module that holds
 * more than the mockup's list (a row of tabs under the page head).
 */
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon, IconBtn, Btn } from '../../components/atelier'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks'
import { splitByWidth } from '../../components/inspector/tabFit'
import { useToolbarMenu } from '../../components/list/useToolbarMenu'

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
 * stand apart with the toolbar's .tools-divider, each tab described by its group's name. The tabs that
 * do not fit go into a « More » menu at the end of the row (the mockup's .tabs-menu), their counters with
 * them; the shown tab always stays in the row, in the last place if it must.
 * options/groups: { value, label, count? } where count null is a counter being read.
 */
export function ViewSwitch({ id, label, value, onChange, options = [], groups = [], children }) {
  const { t, i18n } = useTranslation()
  const number = new Intl.NumberFormat(i18n?.language || undefined)
  const frameRef = useRef(null)
  const rowRef = useRef(null)
  const moreRef = useRef(null)
  const [split, setSplit] = useState({ hidden: [] })
  const [size, setSize] = useState(0)
  const [menu, setMenu] = useState(false)
  const { buttonRef, menuRef, onButtonKeyDown } = useToolbarMenu(menu, setMenu)
  const sets = [...(options.length ? [{ options }] : []), ...groups]
  const all = sets.flatMap((g) => g.options)
  const values = all.map((o) => o.value)
  const tabId = (v) => `${id}-tab-${v}`
  const panelId = `${id}-panel`
  const hidden = new Set(split.hidden)
  const shownIn = (g) => g.options.some((o) => !hidden.has(o.value))

  // Every tab stays drawn for its width; the ones that do not fit are taken out of the row and of the
  // tab order (extensions.css). Read after each render: counters arriving widen the tabs; set only on a change.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    const frame = frameRef.current
    const row = rowRef.current
    if (!frame || !row) return
    const gap = parseFloat(getComputedStyle(row).columnGap) || 0
    const widths = {}
    let lead = 0
    for (const el of row.children) {
      if (el.classList.contains('tools-divider')) { lead += el.offsetWidth + gap; continue }
      const v = el.dataset.view
      if (v === undefined) continue
      widths[v] = el.offsetWidth + gap + lead
      lead = 0
    }
    const more = moreRef.current?.offsetWidth || 96
    const next = splitByWidth(values, widths, value, frame.clientWidth, more + gap)
    const key = next.hidden.join('|')
    setSplit((s) => (s.hidden.join('|') === key ? s : next))
  })
  useEffect(() => {
    const frame = frameRef.current
    if (!frame || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => setSize(frame.clientWidth))
    observer.observe(frame)
    for (const el of rowRef.current?.children || []) observer.observe(el)
    return () => observer.disconnect()
  }, [values.join('|')]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!split.hidden.length) setMenu(false) }, [split.hidden.length])
  // A click elsewhere closes the menu, as the inspector's « +N » menu
  useEffect(() => {
    if (!menu) return undefined
    const away = (e) => { if (!moreRef.current?.contains(e.target)) setMenu(false) }
    const out = (e) => { if (e.relatedTarget && !moreRef.current?.contains(e.relatedTarget)) setMenu(false) }
    document.addEventListener('pointerdown', away)
    document.addEventListener('focusout', out)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('focusout', out) }
  }, [menu])

  // The focus follows the view shown once its tab is back in the row: the page may set the value later
  const focusNext = useRef(null)
  const show = (v) => {
    focusNext.current = v
    onChange(v)
  }
  useEffect(() => {
    const v = focusNext.current
    if (v === null || v !== value) return
    const tab = document.getElementById(tabId(v))
    if (tab && !tab.hasAttribute('data-overflow')) {
      focusNext.current = null
      tab.focus()
    }
  })
  const onKey = (e) => {
    const n = values.length
    const i = values.indexOf(value)
    const to = { ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1 }[e.key]
    if (to === undefined) return
    e.preventDefault()
    show(values[to])
  }
  const counter = (o) => o.count !== undefined && (
    <span className="counter">{o.count === null ? <span className="sk sk-num" style={{ width: '14px' }} /> : number.format(o.count)}</span>
  )
  const describedBy = (g, gi) => (g.label ? `${id}-group-${gi}` : undefined)

  return (
    <>
      <div className="page-views" ref={frameRef} data-size={size || undefined}>
        <div className="page-views-row" role="tablist" aria-label={label} ref={rowRef}>
          {sets.map((g, gi) => [
            gi > 0 && <span key={`div-${gi}`} className="tools-divider" aria-hidden="true"
              data-overflow={!shownIn(g) || !sets.slice(0, gi).some(shownIn) ? '' : undefined} />,
            ...g.options.map((o) => {
              const out = hidden.has(o.value)
              return (
                <button key={o.value} type="button" role="tab" id={tabId(o.value)} data-view={o.value} className={o.value === value ? 'view-btn active' : 'view-btn'}
                  aria-selected={o.value === value} aria-controls={panelId} tabIndex={o.value === value && !out ? 0 : -1}
                  aria-hidden={out || undefined} inert={out ? '' : undefined} data-overflow={out ? '' : undefined}
                  aria-describedby={describedBy(g, gi)} onClick={() => onChange(o.value)} onKeyDown={onKey}>
                  {o.label}
                  {counter(o)}
                </button>
              )
            }),
          ])}
        </div>
        {split.hidden.length > 0 && (
          <div className="pop-wrap views-more" ref={moreRef}>
            <button ref={buttonRef} type="button" className="view-btn views-more-btn" id={`${id}-more`} aria-haspopup="menu" aria-expanded={menu}
              aria-controls={`${id}-more-menu`} onClick={() => setMenu(!menu)} onKeyDown={onButtonKeyDown}>
              {t('common.more')}<Icon name="down" />
            </button>
            <ul ref={menuRef} className="pop-menu tabs-menu views-menu" id={`${id}-more-menu`} role="menu" aria-label={t('common.otherViews')} hidden={!menu}>
              {sets.map((g, gi) => {
                const rest = g.options.filter((o) => hidden.has(o.value))
                if (!rest.length) return null
                const before = sets.slice(0, gi).some((p) => p.options.some((o) => hidden.has(o.value)))
                return [
                  before && <li key={`sep-${gi}`} role="separator" className="pop-sep" />,
                  ...rest.map((o) => (
                    <li key={o.value} role="none">
                      <button type="button" role="menuitem" tabIndex={-1} className="tabs-menu-open" data-view-more={o.value}
                        aria-describedby={describedBy(g, gi)} onClick={() => { setMenu(false); show(o.value) }}>
                        <span className="pop-label">{o.label}</span>{counter(o)}
                      </button>
                    </li>
                  )),
                ]
              })}
            </ul>
          </div>
        )}
        {sets.map((g, gi) => g.label && <span key={gi} id={`${id}-group-${gi}`} hidden>{g.label}</span>)}
      </div>
      <div className="view-panel" role="tabpanel" id={panelId} aria-labelledby={tabId(value)}>{children}</div>
    </>
  )
}

/** The mockup's yesNo(): a check and Oui, or a block sign and Non, in a flag. */
export function YesNo({ value }) {
  const { t } = useTranslation()
  return value
    ? <span className="flag"><Icon name="check" />{t('common.yes')}</span>
    : <span className="flag muted"><Icon name="block" />{t('common.no')}</span>
}
