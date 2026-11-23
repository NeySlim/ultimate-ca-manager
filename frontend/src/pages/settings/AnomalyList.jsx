import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ListView, Toolbar, SearchField, EmptyBlock, NoMatch, Pill, useClientList } from '../../components/atelier'
import { formatDate } from '../../lib/utils'

// The newest first: a log, its order kept by the list rather than the address
const NEWEST = { key: 'time', asc: false }
const high = (row) => row.details?.severity === 'high'

/** The anomalies of the last day as the settings tables: an attack can write hundreds in a few hours. */
export default function AnomalyList({ anomalies, loading }) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const kind = (row) => row.details?.type || t('settings.unknownAnomaly')
  const needle = search.trim().toLowerCase()
  const shown = needle
    ? anomalies.filter((row) => [kind(row), row.details?.ip, row.details?.message, row.details?.user_id && `#${row.details.user_id}`]
      .some((v) => String(v || '').toLowerCase().includes(needle)))
    : anomalies
  const list = useClientList(shown, {
    initial: NEWEST,
    resetKey: needle,
    sorts: {
      type: kind, time: (r) => (r.timestamp ? Date.parse(r.timestamp) : null),
      source: (r) => r.details?.ip || null, severity: (r) => (high(r) ? 0 : 1),
    },
  })
  const source = (row) => [row.details?.ip, row.details?.user_id && `#${row.details.user_id}`].filter(Boolean).join(' · ') || '—'

  return (
    <ListView label={t('settings.anomalyDetection')} icon="radar" list={list} nameSort="type" loading={loading} scrollId="anomalies-scroll"
      rowKey={(row) => `${row.timestamp}|${row.details?.type}|${row.details?.ip}|${row.details?.message}`}
      title={kind}
      status={(row) => <Pill tone={high(row) ? 'bad' : 'warn'} label={high(row) ? t('settings.anomalyHigh') : t('settings.anomalyWarn')} />}
      toolbar={(
        <Toolbar>
          <SearchField id="anomaly-search" label={t('common.search')} placeholder={t('settings.anomalySearchPlaceholder')} value={search} onChange={setSearch} />
        </Toolbar>
      )}
      columns={[
        { id: 'time', label: t('common.date'), cell: (row) => formatDate(row.timestamp, { time: true }), kind: 'fit', priority: 2, sort: 'time' },
        { id: 'source', label: t('settings.anomalySource'), cell: (row) => <span className="mono">{source(row)}</span>, kind: 'fit', priority: 3, sort: 'source' },
        { id: 'message', label: t('common.details'), cell: (row) => row.details?.message || '—', title: (row) => row.details?.message || undefined, kind: 'text', priority: 4, grow: true },
        { status: true, label: t('settings.anomalySeverity'), sort: 'severity' },
      ]}
      empty={anomalies.length ? (
        <NoMatch title={t('common.noResults')} resetLabel={t('common.clear')} onReset={() => setSearch('')} />
      ) : (
        <EmptyBlock id="anomalies" icon="shield" title={t('settings.noAnomalies')} text={t('settings.noAnomaliesDesc')} />
      )}
      footer={list.paged ? { range: t('table.range', { start: list.start, end: list.end, total: list.total }) } : undefined} />
  )
}
