/**
 * Preview of a generated data report: its summary counts, then its rows in a
 * table (the first 200; the download holds them all).
 */
import { useTranslation } from 'react-i18next'
import { Play } from '@phosphor-icons/react'
import { WorkButton } from '../../components/work'

const SHOWN_ROWS = 200
const label = (col) => col.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

function cell(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? '✓' : '✗'
  if (typeof value === 'object') return JSON.stringify(value)
  const s = String(value)
  return s.length > 60 ? `${s.slice(0, 57)}…` : s
}

export function ReportPreview({ report, busy, failed, canGenerate, onGenerate }) {
  const { t } = useTranslation()
  if (!report) {
    return (
      <div>
        <p className="wk-none">{t('reports.work.previewIntro')}</p>
        <WorkButton icon={Play} disabled={!canGenerate || busy} onClick={onGenerate}>{t('reports.generate')}</WorkButton>
        {failed && <p className="ins-notice is-bad" role="alert">{t('reports.generateFailed')}</p>}
      </div>
    )
  }
  const summary = Object.entries(report.summary || {}).filter(([, v]) => typeof v !== 'object')
  // The audit summary holds one count table per category
  const grouped = report.items.length > 0 && report.items[0]?.category && report.items[0]?.data
  return (
    <div className="wk-detail-grid" style={{ gridTemplateColumns: '1fr' }}>
      {summary.length > 0 && (
        <dl className="ins-props">
          {summary.map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{label(k)}</dt><dd>{typeof v === 'number' ? v.toLocaleString() : String(v)}</dd></div>)}
        </dl>
      )}
      {grouped ? report.items.map((item) => (
        <section key={item.category}>
          <h3 className="ins-section-title">{label(item.category)}</h3>
          <div className="wk-table-box">
            <table className="wk-table">
              <tbody>
                {Object.entries(item.data || {}).map(([k, v]) => <tr key={k}><td className="ins-mono">{k}</td><td>{v}</td></tr>)}
              </tbody>
            </table>
          </div>
        </section>
      )) : report.items.length > 0 ? (
        <div className="wk-table-box" role="region" tabIndex={0} aria-label={t('reports.generatedPreview')}>
          <table className="wk-table">
            <thead><tr>{report.columns.map((c) => <th key={c} scope="col">{label(c)}</th>)}</tr></thead>
            <tbody>
              {report.items.slice(0, SHOWN_ROWS).map((row, i) => (
                <tr key={row.id ?? i}>{report.columns.map((c) => <td key={c}>{cell(row[c])}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="wk-none">{t('common.noData')}</p>
      )}
      <p className="ins-muted">
        {t('reports.work.previewCount', { count: Math.min(report.items.length, SHOWN_ROWS), total: report.items.length })}
      </p>
    </div>
  )
}
