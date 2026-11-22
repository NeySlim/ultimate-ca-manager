/**
 * Two to four certificates side by side, the mockup's compare-table: a column per certificate, the
 * same lines for all. An identical line is merged across them; one that differs is marked (.different)
 * and announced, a list element one has alone marked too. Each certificate is read as the inspector reads it.
 */
import { useEffect, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SkeletonPanel } from '../../../components/atelier/Skeleton'
import { Breakable } from '../../../components/atelier/Breakable'
import { Icon } from '../../../components/atelier/Icon'
import { Pill } from '../../../components/atelier/Pill'
import { certificatesService } from '../../../services'
import { entityTitle } from '../../../lib/entityDetail'
import { extractData } from '../../../lib/utils'
import { ABSENT, compareRows } from './compareRows'
import '../../../styles/atelier/detached.css'

/** The certificates of `ids`, in that order; null while one is missing, false when one failed. */
export function useCertificates(ids) {
  const key = ids.join(',')
  const [certs, setCerts] = useState(null)
  useEffect(() => {
    let live = true
    setCerts(null)
    Promise.all(ids.map((id) => certificatesService.getById(id).then((res) => extractData(res) || res?.data || res)))
      .then((list) => { if (live) setCerts(list) })
      .catch(() => { if (live) setCerts(false) })
    return () => { live = false }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  return certs
}

const MONO = /^(sha|serial)/

/** A cell's value: a single one breaks after its separators; a list one element per line, each marked when `marked`. */
function Value({ row, index, marked }) {
  const { t } = useTranslation()
  if (!row.list) return <Breakable text={row.values[index]} />
  const items = row.items[index]
  if (!items.length) return <span className="absent">{ABSENT}</span>
  return (
    <ul className="compare-items">
      {items.map(({ value, common }, i) => (
        <li key={i} className={marked ? (common ? 'common' : 'only') : undefined}>
          <span><Breakable text={value} /></span>
          {marked && !common && <span className="sr-only"> ({t('compare.notInAll')})</span>}
        </li>
      ))}
    </ul>
  )
}

export function CompareTable({ certs }) {
  const { t } = useTranslation()
  const toggleId = `compare-only-${useId().replace(/:/g, '')}`
  const [only, setOnly] = useState(false)
  const rows = compareRows(certs, t)
  const differing = rows.filter((r) => r.differs).length
  const shown = only ? rows.filter((r) => r.differs) : rows
  return (
    <div className="compare-view" data-testid="compare-view">
      <div className="compare-options">
        <p className="compare-sum" aria-live="polite">
          <Pill tone={differing ? 'warn' : 'good'} label={t('compare.differences', { count: differing, total: rows.length })} />
          <span className="muted">{t('compare.lead')}</span>
        </p>
        <label className="checkbox-line" htmlFor={toggleId}>
          <input type="checkbox" id={toggleId} data-action="compare-only" checked={only} onChange={(e) => setOnly(e.target.checked)} />
          {t('compare.onlyDifferences')}
        </label>
      </div>
      <div className="compare-scroll">
        <table className="compare-table" style={{ '--compare-cols': certs.length }}>
          <thead>
            <tr>
              <th scope="col">{t('compare.property')}</th>
              {certs.map((c) => <th key={c.id} scope="col">{entityTitle('certificate', c, t)}</th>)}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const mono = MONO.test(r.key) ? 'mono' : undefined
              // Identical for all: one cell across the certificates, read once
              if (!r.differs) {
                return (
                  <tr key={r.key} className="same" data-row={r.key}>
                    <th scope="row">{r.label}</th>
                    <td colSpan={certs.length} className={mono}>
                      <span className="eq"><Icon name="equal" />{t('compare.identical')}</span>
                      <Value row={r} index={0} />
                    </td>
                  </tr>
                )
              }
              return (
                <tr key={r.key} className="different" data-row={r.key}>
                  <th scope="row">{r.label}<span className="sr-only"> ({t('compare.differs')})</span></th>
                  {certs.map((c, i) => <td key={c.id} className={mono}><Value row={r} index={i} marked={r.byElement} /></td>)}
                </tr>
              )
            })}
          </tbody>
        </table>
        {shown.length === 0 && <p className="muted small" data-testid="compare-none">{t('compare.noDifference')}</p>}
      </div>
    </div>
  )
}

/** The comparison of `ids`, read on demand. */
export function CompareView({ ids }) {
  const { t } = useTranslation()
  const certs = useCertificates(ids)
  if (certs === false) return <p className="notice warn compare-view">{t('compare.loadFailed')}</p>
  if (!certs) return <SkeletonPanel label={t('common.loading')} />
  return <CompareTable certs={certs} />
}

export default CompareView
