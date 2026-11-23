/**
 * Certificates issued through ACME (the built-in server and the client), drawn as the mockup's
 * module list with its dock: paged, sorted and filtered by the server (search, source, state, CA);
 * the export walks every page, in CSV or JSON, as the Activity's export dialog does.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Btn, Pill, ListView, Toolbar, SearchField, FilterSelect, ToolsDivider, Dock, DockBody, Section, Facts, EmptyBlock, NoMatch, AtelierDialog,
} from '../../components/atelier'
import { exportToCSV, exportToJSON } from '../../lib/utils'
import { fetchPages } from '../../lib/fetchAllPages'
import { dateOf, dateTimeOf } from '../admin/adminDates'
import { Notice } from '../protocols/atelierParts'
import { copyRow, fact } from '../../components/atelier/facts'
import { SlotDock } from '../protocols/dockSlot'

const EXPORT_PAGE_SIZE = 100
const EXPORT_MAX_ROWS = 10000

export default function HistoryTab({ history, total, page, perPage, onPageChange, onPerPageChange, search, onSearchChange, sort, onSort,
  caOptions, exportLoader, filterStatus, onFilterStatusChange, filterCA, onFilterCAChange, filterSource, onFilterSourceChange, selectedCert, onSelectCert, loading }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const [exporting, setExporting] = useState(false)
  const [format, setFormat] = useState('csv')
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)

  const sourceLabel = (r) => (r.source === 'letsencrypt' ? t('acme.letsEncryptLabel')
    : r.source === 'acme_client' ? (r.ca_account_label || t('certificates.sourceAcmeClient')) : t('acme.localAcmeLabel'))
  const pill = (r) => <Pill label={t(r.revoked ? 'common.revoked' : 'common.valid')} tone={r.revoked ? 'bad' : 'good'} />
  const environment = (r) => (!r.environment ? '—' : r.environment === 'local' || r.source === 'acme' ? t('acme.localAcmeLabel')
    : t(r.environment === 'production' ? 'acme.production' : 'acme.staging'))
  const pages = Math.max(1, Math.ceil(total / perPage))
  const start = total ? (page - 1) * perPage + 1 : 0
  const narrowed = Boolean(search || filterSource || filterCA || filterStatus.length)
  const columns = [
    { key: 'common_name', header: t('common.commonName') }, { key: 'issuer', header: t('common.issuer') },
    { key: 'source', header: t('common.source') }, { key: 'challenge_type', header: t('acme.method') },
    { key: 'valid_to', header: t('common.expires') }, { key: 'created_at', header: t('common.issued') },
  ]

  const runExport = async () => {
    setBusy(true)
    setNotice(null)
    try {
      const { rows, complete } = await fetchPages(exportLoader, { perPage: EXPORT_PAGE_SIZE, max: EXPORT_MAX_ROWS })
      if (!complete) { setNotice(t('table.exportFailed')); return }
      if (format === 'json') exportToJSON(rows, 'acme-certificates')
      else exportToCSV(rows, columns, 'acme-certificates')
      setExporting(false)
    } catch {
      setNotice(t('table.exportFailed'))
    } finally {
      setBusy(false)
    }
  }

  const cert = selectedCert
  const dock = cert && (
    <Dock label={t('atelier.detailOf', { name: t('common.history') })} tabsLabel={t('atelier.openItem')} activeKey={cert.id}
      tabs={[{ key: cert.id, title: cert.common_name, icon: 'cert' }]} onClose={() => onSelectCert(null)}>
      <DockBody icon="cert" title={cert.common_name} badge={pill(cert)} section="cert" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: cert.common_name })} sections={[['cert', t('atelier.overview')]]}>
        <div className="module-detail">
          <Section title={t('common.certificateDetails')}>
            <Facts items={[
              [t('common.commonName'), cert.common_name], copyRow(t('common.serialNumber'), cert.serial, 'hex', { long: String(cert.serial || '').length > 23 }),
              { ...fact(t('common.issuer'), cert.issuer, { absent: t('acme.unknownCA') }), long: true }, [t('common.source'), sourceLabel(cert)],
              fact(t('common.validFrom'), dateTimeOf(cert.valid_from, locale)), fact(t('common.validTo'), dateTimeOf(cert.valid_to, locale)),
              fact(t('common.issued'), dateTimeOf(cert.created_at, locale)),
            ]} />
          </Section>
          <Section title={t('acme.acmeOrder')}>
            <Facts items={[
              fact(t('acme.method'), cert.challenge_type?.toUpperCase()), fact(t('acme.provider'), cert.dns_provider),
              fact(t('acme.environment'), cert.environment ? environment(cert) : null),
              cert.order?.account && copyRow(t('acme.account'), cert.order.account, undefined, { long: true }),
              cert.order?.status && [t('acme.orderStatus'), cert.order.status],
              cert.order?.order_id && copyRow(t('acme.orderId'), cert.order.order_id, undefined, { long: true }),
            ]} />
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

  return (
    <>
      <ListView label={t('common.history')} caption={t('acme.historyCaption')} icon="cert" rows={history} loading={loading}
        filters={{
          views: [{ id: '', label: t('common.all') }, { id: 'valid', label: t('common.valid') }, { id: 'revoked', label: t('common.revoked') }],
          active: filterStatus.length === 1 ? filterStatus[0] : '', onChange: (v) => onFilterStatusChange(v ? [v] : []), label: t('acme.filterByState'),
        }}
        toolbar={(
          <Toolbar>
            <SearchField id="acme-history-search" name="q" label={t('common.searchCertificates')} placeholder={t('common.searchCertificates')} value={search} onChange={onSearchChange} />
            <FilterSelect id="acme-history-source" label={t('common.source')} value={filterSource} onChange={onFilterSourceChange}
              options={[{ value: '', label: t('acme.allSources') }, { value: 'acme', label: t('acme.localAcme') },
                { value: 'acme_client', label: t('certificates.sourceAcmeClient') }, { value: 'letsencrypt', label: t('acme.letsEncrypt') }]} />
            <FilterSelect id="acme-history-ca" label={t('common.issuer')} value={filterCA} onChange={onFilterCAChange}
              options={[{ value: '', label: t('acme.allCAs') }, ...caOptions]} />
            <ToolsDivider />
            <Btn icon="download" id="acme-history-export" onClick={() => { setNotice(null); setExporting(true) }}>{t('table.exportData')}</Btn>
          </Toolbar>
        )}
        title={(r) => r.common_name} status={pill} openedId={cert?.id} onOpen={onSelectCert}
        nameSort="common_name" sort={sort} onSort={onSort}
        columns={[
          // The name takes the room left; the issuer gives way with it, in proportion (R2)
          { id: 'issuer', label: t('common.issuer'), cell: (r) => r.issuer || t('common.unknown'), kind: 'text', priority: 2 },
          { id: 'source', label: t('common.source'), cell: sourceLabel, kind: 'fit', priority: 3, sort: 'source' },
          { id: 'method', label: t('acme.method'), cell: (r) => r.challenge_type?.toUpperCase() || '—', kind: 'fit', priority: 3 },
          { id: 'expires', label: t('common.expires'), labelFull: t('table.fullExpires'), cell: (r) => dateOf(r.valid_to, locale) || '—', kind: 'fit', priority: 2, labelled: true, sort: 'valid_to' },
          { id: 'issued', label: t('common.issued'), labelFull: t('table.fullIssued'), cell: (r) => dateOf(r.created_at, locale) || '—', kind: 'fit', priority: 2, labelled: true, sort: 'created_at' },
          { status: true, sort: 'status' },
        ]}
        empty={narrowed ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
            onReset={() => { onSearchChange(''); onFilterSourceChange(''); onFilterCAChange(''); onFilterStatusChange([]) }} />
        ) : <EmptyBlock id="acme-history" icon="cert" title={t('acme.noCertificates')} text={t('acme.noCertificatesDesc')} />}
        footer={{
          range: t('acme.historyRange', { start, end: Math.min(page * perPage, total), count: total }),
          pagination: { page, pages, perPage, onPage: onPageChange, onPerPage: onPerPageChange, jump: pages > 5 },
        }} />
      <SlotDock>{dock}</SlotDock>
      {exporting && (
        <AtelierDialog size="narrow" title={t('table.exportData')} onClose={() => setExporting(false)} returnTo="acme-history-export">
          <p className="event-detail">{t('acme.historyExportScope', { count: Math.min(total, EXPORT_MAX_ROWS) })}</p>
          <div className="format-grid">
            {['csv', 'json'].map((f) => (
              <label key={f} className="format-option">
                <input type="radio" name="acme-history-format" value={f} checked={format === f} onChange={() => setFormat(f)} />
                <span>{f.toUpperCase()}</span>
              </label>
            ))}
          </div>
          {notice && <Notice tone="warn" role="alert">{notice}</Notice>}
          <div className="modal-actions">
            <Btn onClick={() => setExporting(false)}>{t('common.cancel')}</Btn>
            <Btn tone="primary" icon="download" write={false} disabled={busy || undefined} onClick={runExport}>{t(format === 'json' ? 'table.exportJSON' : 'table.exportCSV')}</Btn>
          </div>
        </AtelierDialog>
      )}
    </>
  )
}
