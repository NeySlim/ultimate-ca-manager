/**
 * Pieces of the mockup's detail panels: section() (a titled block), props() (terms and values),
 * rows() and recordRow() (a list of records, or a sentence when empty), and the one-tab panel of
 * simplePage() (its properties, then its summary). Facts are the typed rows of terms and values
 *: a fact, a state, an absence, a copyable digest or URL, an action apart, a folded help.
 */
import { Fragment, useId, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNotification } from '../../contexts/NotificationContext'
import { useClipboard } from '../../hooks/useClipboard'
import { Icon } from './Icon'
import { Pill } from './Pill'
import { hexLines, HEX_PER_LINE } from './helpers'
import { Breakable } from './Breakable'

export function Section({ title, children }) {
  return <section><h3 className="section-title">{title}</h3>{children}</section>
}

/** items: [[term, value]]; a falsy item is skipped. */
export function Props({ items }) {
  return <dl className="props">{items.filter(Boolean).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}</dl>
}

// Outside a NotificationProvider (a test, a page drawn alone) the copy still happens, its button says so
function useNotificationIfAny() {
  try {
    return useNotification()
  } catch {
    return null
  }
}

// The last characters of a URL stay in view when it is cut in its middle
const URL_TAIL = 14

const inner = (el) => {
  const css = getComputedStyle(el)
  const side = (k) => (parseFloat(css[`padding${k}`]) || 0) + (parseFloat(css[`border${k}Width`]) || 0)
  return el.getBoundingClientRect().width - side('Left') - side('Right')
}

/**
 * The bytes a line of a digest may hold in the width its chip can take: the width of the chip's parent (of the
 * parent's flex container when the parent is a flex item, whose width follows its content), less the chip's own
 * padding and button, in characters of 3 per byte. Measured again when that width changes; 10 when unmeasured.
 */
function useHexRoom(chip, text) {
  const [room, setRoom] = useState(HEX_PER_LINE)
  useLayoutEffect(() => {
    const el = chip.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const parent = el.parentElement
    const box = parent && /flex/.test(getComputedStyle(parent.parentElement || parent).display) ? parent.parentElement : parent
    if (!box) return undefined
    const measure = () => {
      const val = el.firstElementChild
      const line = val?.firstElementChild
      const chars = line?.textContent.length
      if (!chars) return
      const ch = line.getBoundingClientRect().width / chars
      const free = inner(box) - (el.getBoundingClientRect().width - val.getBoundingClientRect().width)
      if (ch > 0 && free > 0) setRoom(Math.max(1, Math.floor(Math.floor((free + 0.5) / ch) / 3)))
    }
    const observer = new ResizeObserver(measure)
    observer.observe(box)
    measure()
    document.fonts?.ready?.then(measure)
    return () => observer.disconnect()
  }, [chip, text])
  return room
}
/**
 * A technical value in mono and its copy button. kind 'hex': a digest in equal lines, never shortened;
 * as wide as its column allows; kind 'url': one line cut in its middle, whole in its title and on a click. The copy is
 * always the whole value.
 */
export function CodeValue({ value, kind, label }) {
  const { t } = useTranslation()
  const { copy, copied } = useClipboard()
  const notify = useNotificationIfAny()
  const [open, setOpen] = useState(false)
  const chip = useRef(null)
  const text = value === null || value === undefined ? '' : String(value)
  const room = useHexRoom(chip, kind === 'hex' ? text : null)
  if (text === '') return null
  const cut = kind === 'url' && text.length > URL_TAIL + 6
  const toggle = () => setOpen(!open)
  const shown = kind === 'hex'
    ? <span className="val hex">{hexLines(text, room).split('\n').map((line, i) => <span key={i} className="line">{line}</span>)}</span>
    : cut
      ? (
        <span className={open ? 'val mid open' : 'val mid'} role="button" tabIndex={0} aria-expanded={open} title={text}
          onClick={toggle} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle() } }}>
          <span className="head"><Breakable text={text.slice(0, -URL_TAIL)} /></span><span className="tail"><Breakable text={text.slice(-URL_TAIL)} /></span>
        </span>
      )
      : <span className="val"><Breakable text={text} /></span>
  return (
    <span ref={kind === 'hex' ? chip : null} className={kind ? `code-value ${kind}` : 'code-value'}>
      {shown}
      <button type="button" className="cp" aria-label={t('protocols.copyValue', { name: label })} title={t('protocols.copyValue', { name: label })}
        onClick={async () => { if (await copy(text)) notify?.showSuccess(t('common.copied')) }}>
        <Icon name={copied ? 'check' : 'copy'} />
      </button>
    </span>
  )
}

/** The action of a row, apart from its value: a small outlined button, a write for the central write guard. */
export function RowAction({ children, ...rest }) {
  return <button type="button" className="btn-sm" data-write="" {...rest}>{children}</button>
}

/**
 * One row of Facts: dt, then the value (dd.v, or dd.absent for a value that is missing), the action
 * (dd.act) and the help (dd.help, folded behind the button after the term). `product` marks a row
 * the mockup does not have (data-product, declared to the comparator).
 */
export function FactRow({ label, value, state, absent, kind, sub, action, help, long = false, wide = false, product = false, copyLabel, className, ...rest }) {
  const { t } = useTranslation()
  const helpId = `help${useId().replace(/:/g, '')}`
  const [helpOpen, setHelpOpen] = useState(false)
  const mark = product ? { 'data-product': '' } : {}
  const name = copyLabel || (typeof label === 'string' ? label : '')
  const missing = absent !== undefined && absent !== null && absent !== false
  const shown = state ? <Pill tone={state[0]} label={state[1]} icon={state[2]} />
    : kind ? <CodeValue value={value} kind={kind} label={name} />
      : value
  const rowClass = ['row', long && 'long', wide && 'wide', className].filter(Boolean).join(' ')
  return (
    <div className={rowClass} {...rest}>
      <dt {...mark}>
        {label}
        {help && (
          <button type="button" className="tip" aria-expanded={helpOpen} aria-controls={helpId}
            aria-label={t('common.helpAbout', { name })} title={t('common.helpAbout', { name })} onClick={() => setHelpOpen(!helpOpen)}>
            <Icon name="help" />
          </button>
        )}
      </dt>
      {missing
        ? <dd className="absent" {...mark}>{absent}</dd>
        : <dd className="v" {...mark}>{shown}{sub && <span className="sub">{sub}</span>}</dd>}
      {action && <dd className="act">{action}</dd>}
      {help && <dd className="help" id={helpId} hidden={!helpOpen}>{help}</dd>}
    </div>
  )
}

/**
 * items: [term, value] pairs or rows ({ label, value, state: [tone, text], absent, kind: 'hex' | 'url',
 * sub, action, help, long, wide, product }); a falsy item is skipped. Further rows may come as children.
 */
export function Facts({ items = [], children, className, ...rest }) {
  return (
    <dl className={className ? `kv ${className}` : 'kv'} {...rest}>
      {items.filter(Boolean).map((item, i) => {
        const row = Array.isArray(item) ? { label: item[0], value: item[1] } : item
        const { key, ...props } = row
        return <FactRow key={key ?? (typeof row.label === 'string' ? row.label : i)} {...props} />
      })}
      {children}
    </dl>
  )
}

/** Sections of one panel whose Facts share one label column, so their values line up from one section to the next. */
export function FactsGroup({ children, className }) {
  return <div className={className ? `kvg ${className}` : 'kvg'}>{children}</div>
}

/** The records, or `empty` in a muted sentence when there are none. */
/** `step`: a long list shows its first `step` records, then as many more at each ask (a button under it). */
/** `columns`: the badges and the actions of every record in columns of their own, so they line up from row to row. */
export function RecordList({ children, empty, label, step, columns = false }) {
  const { t } = useTranslation()
  const [limit, setLimit] = useState(step || Infinity)
  const list = [].concat(children || []).filter(Boolean)
  if (!list.length) return <p className="muted small">{empty}</p>
  const rest = list.length - limit
  return (
    <>
      <ul className={columns ? 'record-list rl-cols' : 'record-list'} aria-label={label}>{rest > 0 ? list.slice(0, limit) : list}</ul>
      {rest > 0 && (
        <p className="record-more">
          <button type="button" className="btn" data-action="records-more" onClick={() => setLimit((n) => n + step)}>
            {t('work.historyMore', { count: Math.min(step, rest) })}
          </button>
        </p>
      )}
    </>
  )
}

/** A record; other props (a data attribute, aria-current) go on its row. */
export function RecordRow({ title, meta, badge, action, extra, ...row }) {
  return (
    <li {...row}>
      <div className="rl-main"><strong>{title}</strong>{meta && <span className="rl-meta">{meta}</span>}{extra}</div>
      {badge}
      {action && <div className="rl-action">{action}</div>}
    </li>
  )
}

/** The Aperçu panel of a simple module page: every property, the state, then the summary. */
export function SimpleOverview({ properties, summary }) {
  const { t } = useTranslation()
  return (
    <div className="module-detail">
      <Section title={t('atelier.properties')}><Props items={properties} /></Section>
      {summary !== undefined && <Section title={t('atelier.summary')}><p className="summary">{summary}</p></Section>}
    </div>
  )
}
