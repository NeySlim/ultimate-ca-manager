/**
 * The mockup's skeletons: bars at the size of the content they stand for, widths varying a
 * little from row to row; rows keep their final height so nothing jumps on arrival. The first
 * row carries the loading announcement, the others are hidden from assistive technology.
 */
import { useTranslation } from 'react-i18next'

import { skWidth, barOf } from './helpers'
import { columnKind } from './columnShare'

/** kind: 'box' | 'pill' | 'thin' | 'num' | 'figure' */
export function Bar({ width, kind }) {
  return <span className={kind ? `sk sk-${kind}` : 'sk'} style={width ? { width } : undefined} />
}

/**
 * @param {Array<{ id, skeleton?: {width?, base?, spread?, kind?} }>} columns
 * @param {number} rows  at most 12, as the mockup
 */
export function SkeletonRows({ columns, rows = 12, check = false, actions = false }) {
  const { t } = useTranslation()
  const n = Math.max(1, Math.min(rows, 12))
  return Array.from({ length: n }, (_, i) => (
    <tr key={`sk-${i}`} className="sk-row" aria-hidden={i > 0 ? 'true' : undefined}>
      {check && <td><Bar width="16px" kind="box" /></td>}
      {columns.map((c, k) => (
        <td key={c.id} className={columnKind(c) === 'entity' ? 'entity-cell' : undefined}>
          {i === 0 && k === 0 && <span className="sr-only" role="status">{t('table.loadingRows')}</span>}
          {c.skeleton !== null && <Bar width={barOf(c.skeleton || { base: 45, spread: 40 }, i)} kind={c.skeleton?.kind} />}
        </td>
      ))}
      {actions && <td />}
    </tr>
  ))
}

/** Six phone records: a name, a second line, a state. */
export function SkeletonCards({ count = 6 }) {
  const { t } = useTranslation()
  return Array.from({ length: count }, (_, i) => (
    <article key={`sk-${i}`} className="mobile-record sk-record" aria-hidden={i > 0 ? 'true' : undefined}>
      {i === 0 && <span className="sr-only" role="status">{t('table.loadingRows')}</span>}
      <Bar width={skWidth(i, 50, 30)} /><Bar width={skWidth(i, 30, 40)} kind="thin" /><Bar width="90px" kind="pill" />
    </article>
  ))
}

/** The inspector's panel while its object is read: three columns of bars. */
export function SkeletonPanel({ label }) {
  return (
    <>
      <div className="sk-panel" aria-hidden="true">
        {[0, 1, 2].map((c) => (
          <div key={c} className="sk-col"><Bar width="40%" kind="thin" />{[0, 1, 2, 3].map((i) => <Bar key={i} width={skWidth(i + c, 45, 45)} />)}</div>
        ))}
      </div>
      <p className="sr-only">{label}</p>
    </>
  )
}
