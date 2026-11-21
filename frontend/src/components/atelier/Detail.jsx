/**
 * Pieces of the mockup's detail panels: section() (a titled block), props() (terms and values),
 * rows() and recordRow() (a list of records, or a sentence when empty), and the one-tab panel of
 * simplePage() (its properties, then its summary).
 */
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'

export function Section({ title, children }) {
  return <section><h3 className="section-title">{title}</h3>{children}</section>
}

/** items: [[term, value]]; a falsy item is skipped. */
export function Props({ items }) {
  return <dl className="props">{items.filter(Boolean).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}</dl>
}

/** The records, or `empty` in a muted sentence when there are none. */
export function RecordList({ children, empty, label }) {
  const list = [].concat(children || []).filter(Boolean)
  return list.length ? <ul className="record-list" aria-label={label}>{list}</ul> : <p className="muted small">{empty}</p>
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
