/**
 * Preview of a generated data report: its summary counts in Facts, then its rows
 * in the module table of listView() (the first 200; the download holds them all).
 */
import { useTranslation } from 'react-i18next'
import { Btn, Facts, Section } from '../../components/atelier'

const SHOWN_ROWS = 200
const label = (col) => col.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

function cell(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? '✓' : '✗'
  if (typeof value === 'object') return JSON.stringify(value)
  const s = String(value)
  return s.length > 60 ? `${s.slice(0, 57)}…` : s
}

function Table({ name, head, rows }) {
  return (
    <div className="table-container">
      <div className="table-scroll" role="region" tabIndex={0} aria-label={name}>
        <table className="cert-table module-table">
          {head && <thead><tr>{head.map((c) => <th key={c} scope="col">{label(c)}</th>)}</tr></thead>}
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
  )
}

export function ReportPreview({ report, busy, failed, canGenerate, onGenerate }) {
  const { t } = useTranslation()
  if (!report) {
    return (
      <div className="module-detail">
        <section>
          <p className="muted small">{t('reports.work.previewIntro')}</p>
          <p><Btn icon="refresh" disabled={!canGenerate || busy || undefined} onClick={onGenerate}>{t('reports.generate')}</Btn></p>
          {failed && <p className="notice warn" role="alert">{t('reports.generateFailed')}</p>}
        </section>
      </div>
    )
  }
  const summary = Object.entries(report.summary || {}).filter(([, v]) => typeof v !== 'object')
  // The audit summary holds one count table per category
  const grouped = report.items.length > 0 && report.items[0]?.category && report.items[0]?.data
  return (
    <div className="module-detail">
      {summary.length > 0 && (
        <Section title={t('atelier.summary')}>
          <Facts items={summary.map(([k, v]) => [label(k), typeof v === 'number' ? v.toLocaleString() : String(v)])} />
        </Section>
      )}
      {grouped ? report.items.map((item) => (
        <Section key={item.category} title={label(item.category)}>
          <Table name={label(item.category)} rows={Object.entries(item.data || {}).map(([k, v]) => <tr key={k}><td className="mono">{k}</td><td>{v}</td></tr>)} />
        </Section>
      )) : (
        <Section title={t('reports.generatedPreview')}>
          {report.items.length > 0 ? (
            <Table name={t('reports.generatedPreview')} head={report.columns}
              rows={report.items.slice(0, SHOWN_ROWS).map((row, i) => <tr key={row.id ?? i}>{report.columns.map((c) => <td key={c}>{cell(row[c])}</td>)}</tr>)} />
          ) : <p className="muted small">{t('common.noData')}</p>}
          <p className="small muted">{t('reports.work.previewCount', { count: Math.min(report.items.length, SHOWN_ROWS), total: report.items.length })}</p>
        </Section>
      )}
    </div>
  )
}
