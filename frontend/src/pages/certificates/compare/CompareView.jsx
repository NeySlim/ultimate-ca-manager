/**
 * Two to four certificates side by side, the mockup's compare-table: a column per certificate, the
 * same lines for all, those that differ marked (.different) and announced, and the option to show
 * only them. Each certificate is read as the inspector reads it.
 */
import { Fragment, useEffect, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SkeletonPanel } from '../../../components/atelier/Skeleton'
import { certificatesService } from '../../../services'
import { entityTitle } from '../../../lib/entityDetail'
import { extractData } from '../../../lib/utils'
import { compareRows } from './compareRows'
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

const multiline = (value) => value.split('\n').map((line, i) => <Fragment key={i}>{i > 0 && <br />}{line}</Fragment>)

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
        <p className="muted small" aria-live="polite">{t('compare.lead')} {t('compare.differences', { count: differing })}</p>
        <label className="checkbox-line" htmlFor={toggleId}>
          <input type="checkbox" id={toggleId} data-action="compare-only" checked={only} onChange={(e) => setOnly(e.target.checked)} />
          {t('compare.onlyDifferences')}
        </label>
      </div>
      <div className="compare-scroll">
        <table className="compare-table">
          <thead>
            <tr>
              <th scope="col">{t('compare.property')}</th>
              {certs.map((c) => <th key={c.id} scope="col">{entityTitle('certificate', c, t)}</th>)}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.key} className={r.differs ? 'different' : undefined} data-row={r.key}>
                <th scope="row">{r.label}{r.differs && <span className="sr-only"> ({t('compare.differs')})</span>}</th>
                {r.values.map((v, i) => <td key={certs[i].id} className={/^(sha|serial)/.test(r.key) ? 'mono' : undefined}>{multiline(v)}</td>)}
              </tr>
            ))}
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
