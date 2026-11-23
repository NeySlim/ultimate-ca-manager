/**
 * Orders of the ACME client (Let's Encrypt and the other upstream CAs), drawn as the mockup's module
 * list with its dock: filtered by state, an order opens its detail and its actions; the renewal
 * failures stay on the row, a partial list says so.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ListView, Toolbar, IconBtn, Pill, EmptyBlock, NoMatch, useClientList, useSortParam } from '../../components/atelier'
import { stateLabel } from '../../lib/stateLabel'
import { dateOf } from '../admin/adminDates'
import { Notice } from '../protocols/atelierParts'
import { SlotDock } from '../protocols/dockSlot'
import OrderDetailPanel from './OrderDetailPanel'

const ORDER_STATUSES = ['pending', 'processing', 'validating', 'ready', 'valid', 'issued', 'invalid']
const TONES = { valid: 'good', issued: 'good', ready: 'good', pending: 'warn', processing: 'warn', validating: 'warn', invalid: 'bad' }
// The newest order first (T4), kept in the address (T9)
const NEWEST = { key: 'created', asc: false }
const SORT_KEYS = ['name', 'account', 'env', 'method', 'created', 'failures', 'state']

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
  const account = (o) => o.acme_client_account_label || o.account_email || (o.account_short_id ? `${o.account_short_id}…` : '—')
  // The page reads every order of the client (up to its cap): sorted and paged here
  const sortParam = useSortParam(NEWEST, SORT_KEYS)
  const list = useClientList(visibleOrders, {
    resetKey: status,
    sortParam,
    sorts: {
      name, account: (o) => (account(o) === '—' ? null : account(o)), env, method: (o) => o.challenge_type,
      created: (o) => o.created_at && Date.parse(o.created_at), failures: (o) => o.renewal_failures || 0,
      state: (o) => (ORDER_STATUSES.includes(statusOf(o)) ? ORDER_STATUSES.indexOf(statusOf(o)) : null),
    },
  })

  return (
    <>
      {partial && <Notice tone="warn" role="status">{t('acme.ordersListPartial', { loaded: partial.loaded, total: partial.total })}</Notice>}
      <ListView label={t('acme.letsEncryptOrders')} caption={t('acme.ordersCaption')} icon="refresh" list={list} nameSort="name" loading={loading}
        filters={{
          views: [{ id: '', label: t('common.all'), count: clientOrders.length }, ...present.map((s) => ({ id: s, label: stateLabel(t, s), count: clientOrders.filter((o) => statusOf(o) === s).length }))],
          active: status, onChange: setStatus, label: t('acme.filterByState'),
        }}
        toolbar={<Toolbar><span className="spacer" /><IconBtn icon="refresh" label={t('common.refresh')} onClick={onRefresh} /></Toolbar>}
        title={name} status={pill} openedId={selectedClientOrder?.id} onOpen={onSelectOrder}
        columns={[
          { id: 'account', label: t('acme.accountOrCa'), cell: account, kind: 'text', priority: 2, labelled: true, sort: 'account' },
          { id: 'env', label: t('acme.environment'), cell: env, kind: 'fit', priority: 3, labelled: true, sort: 'env' },
          { id: 'method', label: t('acme.method'), cell: (o) => o.challenge_type?.toUpperCase() || t('common.unknown'), kind: 'fit', priority: 3, labelled: true, sort: 'method' },
          { id: 'created', label: t('common.created'), labelFull: t('table.fullCreated'), cell: (o) => dateOf(o.created_at, locale) || '—', kind: 'fit', priority: 2, labelled: true, sort: 'created' },
          // A count under a short header, the whole name in its title (L8); the last error on a failing row
          { id: 'failures', label: t('acme.columns.failures'), labelFull: t('acme.renewalFailuresLabel'), kind: 'number', priority: 3, sort: 'failures',
            cell: (o) => (o.renewal_failures > 0 ? <span className="warn" title={o.error_message || undefined}>{o.renewal_failures}</span> : '0') },
          { status: true, sort: 'state' },
        ]}
        empty={clientOrders.length ? (
          <NoMatch title={t('table.noResults')} resetLabel={t('table.clearFilters')} onReset={() => setStatus('')} />
        ) : <EmptyBlock id="acme-client-orders" icon="refresh" title={t('acme.noCertificateOrders')} text={t('acme.viewHistoryForCertificates')} />}
        footer={{ range: t('acme.clientOrdersRange', list.counts(clientOrders.length)) }} />
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
