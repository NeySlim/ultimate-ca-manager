/**
 * Orders of the ACME client (Let's Encrypt and the other upstream CAs), drawn as the mockup's module
 * list with its dock: filtered by state, an order opens its detail and its actions; the renewal
 * failures stay on the row, a partial list says so.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ListView, Toolbar, IconBtn, Pill, EmptyBlock, NoMatch } from '../../components/atelier'
import { stateLabel } from '../../lib/stateLabel'
import { dateOf } from '../admin/adminDates'
import { Notice } from '../protocols/atelierParts'
import { SlotDock } from '../protocols/dockSlot'
import OrderDetailPanel from './OrderDetailPanel'

const ORDER_STATUSES = ['pending', 'processing', 'validating', 'ready', 'valid', 'issued', 'invalid']
const TONES = { valid: 'good', issued: 'good', ready: 'good', pending: 'warn', processing: 'warn', validating: 'warn', invalid: 'bad' }

export default function LetsEncryptOrdersTab({
  clientOrders = [], partial = null, selectedClientOrder, onSelectOrder, onRefresh, onCheckOrderStatus, onVerifyChallenge, onFinalizeOrder,
  onViewCertificate, onDownloadCertificate, onRenewCertificate, onDeleteOrder, onToggleRenewal, canDelete = false, canWrite = false, loading = false,
}) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const [status, setStatus] = useState('')
  const statusOf = (o) => String(o.status || '').toLowerCase()
  const visibleOrders = status ? clientOrders.filter((o) => statusOf(o) === status) : clientOrders
  const present = ORDER_STATUSES.filter((s) => clientOrders.some((o) => statusOf(o) === s))
  const name = (o) => o.primary_domain || o.domains?.[0] || t('common.unknown')
  const pill = (o) => <Pill label={stateLabel(t, o.status)} tone={TONES[statusOf(o)] || 'muted'} />
  const env = (o) => t(o.environment === 'production' ? 'acme.production' : 'acme.staging')

  return (
    <>
      {partial && <Notice tone="warn" role="status">{t('acme.ordersListPartial', { loaded: partial.loaded, total: partial.total })}</Notice>}
      <ListView label={t('acme.letsEncryptOrders')} caption={t('acme.ordersCaption')} icon="refresh" rows={visibleOrders} loading={loading}
        filters={{
          views: [{ id: '', label: t('common.all'), count: clientOrders.length }, ...present.map((s) => ({ id: s, label: stateLabel(t, s), count: clientOrders.filter((o) => statusOf(o) === s).length }))],
          active: status, onChange: setStatus, label: t('acme.filterByState'),
        }}
        toolbar={<Toolbar><IconBtn icon="refresh" label={t('common.refresh')} onClick={onRefresh} /></Toolbar>}
        title={name} status={pill} openedId={selectedClientOrder?.id} onOpen={onSelectOrder}
        columns={[
          { id: 'account', label: t('acme.accountOrCa'), cell: (o) => o.acme_client_account_label || o.account_email || (o.account_short_id ? `${o.account_short_id}…` : '—'), grow: true },
          { id: 'env', label: t('acme.environment'), cell: env },
          { id: 'method', label: t('acme.method'), cell: (o) => o.challenge_type?.toUpperCase() || t('common.unknown') },
          { id: 'created', label: t('common.created'), cell: (o) => dateOf(o.created_at, locale) || '—' },
          { id: 'failures', label: t('acme.renewalFailuresLabel'), cell: (o) => (o.renewal_failures > 0
            ? <span className="warn" title={o.error_message || ''}>{t('acme.renewalFailures', { count: o.renewal_failures })}</span> : '—') },
          { status: true },
        ]}
        empty={clientOrders.length ? (
          <NoMatch title={t('table.noResults')} resetLabel={t('table.clearFilters')} onReset={() => setStatus('')} />
        ) : <EmptyBlock id="acme-client-orders" icon="refresh" title={t('acme.noCertificateOrders')} text={t('acme.viewHistoryForCertificates')} />}
        footer={{ range: t('acme.clientOrdersRange', { shown: visibleOrders.length, count: clientOrders.length }) }} />
      <SlotDock>
        {selectedClientOrder && (
          <OrderDetailPanel order={selectedClientOrder} onClose={() => onSelectOrder(null)} onDownloadCert={onDownloadCertificate}
            onViewCertificate={onViewCertificate} onRenewCertificate={onRenewCertificate} onVerifyChallenge={onVerifyChallenge}
            onCheckOrderStatus={onCheckOrderStatus} onFinalizeOrder={onFinalizeOrder} onDeleteOrder={onDeleteOrder}
            onToggleRenewal={onToggleRenewal} canWrite={canWrite} canDelete={canDelete} />
        )}
      </SlotDock>
    </>
  )
}
