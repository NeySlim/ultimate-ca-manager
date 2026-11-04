import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ArrowsClockwise, Certificate, CheckCircle, DownloadSimple, Eye,
  MagnifyingGlass, Play, Trash,
} from '@phosphor-icons/react'
import { Badge, Button, EmptyState, FilterSelect } from '../../components'
import { cn, formatDate } from '../../lib/utils'

const ORDER_STATUSES = [
  'pending', 'processing', 'validating', 'ready', 'valid', 'issued', 'invalid',
]

const statusVariant = (status) => {
  if (status === 'valid' || status === 'issued') return 'success'
  if (status === 'pending' || status === 'processing' || status === 'validating') return 'warning'
  if (status === 'ready') return 'info'
  return 'danger'
}

export default function LetsEncryptOrdersTab({
  clientOrders = [],
  selectedClientOrder,
  onSelectOrder,
  onRefresh,
  onCheckOrderStatus,
  onVerifyChallenge,
  onFinalizeOrder,
  onViewCertificate,
  onDownloadCertificate,
  onRenewCertificate,
  onDeleteOrder,
  canDelete = false,
}) {
  const { t } = useTranslation()
  const [status, setStatus] = useState('')
  const visibleOrders = status
    ? clientOrders.filter((order) => (order.status || '').toLowerCase() === status)
    : clientOrders

  return (
    <div className="p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-text-primary">{t('acme.letsEncryptOrders')}</h2>
          <Badge variant="secondary" size="sm">{clientOrders.length}</Badge>
          <FilterSelect
            value={status}
            onChange={setStatus}
            allLabel={t('common.allStatuses')}
            options={ORDER_STATUSES.map((value) => ({ value, label: value }))}
            size="sm"
          />
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          aria-label={t('common.refresh')}
          onClick={onRefresh}
        >
          <ArrowsClockwise size={14} />
        </Button>
      </div>

      {clientOrders.length === 0 ? (
        <EmptyState
          icon={Certificate}
          title={t('acme.noCertificateOrders')}
          description={t('acme.viewHistoryForCertificates')}
        />
      ) : visibleOrders.length === 0 ? (
        <EmptyState icon={Certificate} title={t('common.noResults')} />
      ) : (
        <div className="space-y-3">
          {visibleOrders.map((order) => {
            const selected = selectedClientOrder?.id === order.id
            return (
              <div
                key={order.id}
                className={cn(
                  'p-3 bg-tertiary-op50 rounded-lg border transition-colors cursor-pointer',
                  selected
                    ? 'border-accent-primary ring-1 ring-accent-primary-op30'
                    : 'border-border-op50 hover:border-border'
                )}
                onClick={() => onSelectOrder?.(selected ? null : order)}
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="text-sm font-medium text-text-primary truncate flex-1">
                    {order.primary_domain || order.domains?.[0] || t('common.unknown')}
                  </span>
                  <div className="flex items-center gap-2">
                    <Badge variant={order.environment === 'production' ? 'default' : 'secondary'} size="sm">
                      {order.environment}
                    </Badge>
                    <Badge variant={statusVariant(order.status)} size="sm">{order.status}</Badge>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">{t('acme.method')}</span>
                    <span className="text-text-secondary font-medium">
                      {order.challenge_type || t('common.unknown')}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">{t('common.created')}</span>
                    <span className="text-text-secondary">
                      {order.created_at ? formatDate(order.created_at) : '-'}
                    </span>
                  </div>
                  {order.dns_provider_name && (
                    <div className="flex justify-between col-span-2">
                      <span className="text-text-tertiary">{t('acme.dnsProviders')}</span>
                      <span className="text-text-secondary">{order.dns_provider_name}</span>
                    </div>
                  )}
                  {order.is_proxy_order && (order.account_email || order.account_short_id) && (
                    <div className="flex justify-between col-span-2">
                      <span className="text-text-tertiary">{t('acme.account')}</span>
                      <span className="text-text-secondary truncate max-w-[220px]" title={order.account_id || ''}>
                        {order.account_email || `${order.account_short_id}…`}
                      </span>
                    </div>
                  )}
                  {order.error_message && (
                    <div className="col-span-2 mt-1 pt-1 border-t border-border-op30">
                      <span className="text-xs status-danger-text">{order.error_message}</span>
                    </div>
                  )}
                </div>

                {selected && (
                  <div className="mt-3 pt-3 border-t border-border-op30 space-y-2">
                    {order.expires_at && (
                      <div className="flex justify-between text-xs">
                        <span className="text-text-tertiary">{t('common.expires')}</span>
                        <span className="text-text-secondary">{formatDate(order.expires_at)}</span>
                      </div>
                    )}
                    {order.is_proxy_order && (
                      <p className="text-xs text-text-tertiary">{t('acme.proxyOrderClientDriven')}</p>
                    )}
                    <div className="flex flex-wrap gap-2 pt-1">
                      {!order.is_proxy_order && ['pending', 'processing'].includes(order.status) && onVerifyChallenge && (
                        <Button type="button" variant="secondary" size="sm" onClick={(event) => { event.stopPropagation(); onVerifyChallenge(order) }}>
                          <Play size={12} />
                          {t('acme.verifyChallenge')}
                        </Button>
                      )}
                      {!order.is_proxy_order && order.status === 'validating' && (
                        <>
                          {onCheckOrderStatus && (
                            <Button type="button" variant="secondary" size="sm" onClick={(event) => { event.stopPropagation(); onCheckOrderStatus(order) }}>
                              <MagnifyingGlass size={12} />
                              {t('acme.checkStatus')}
                            </Button>
                          )}
                          {onVerifyChallenge && (
                            <Button type="button" variant="secondary" size="sm" onClick={(event) => { event.stopPropagation(); onVerifyChallenge(order) }}>
                              <Play size={12} />
                              {t('acme.retryVerification')}
                            </Button>
                          )}
                        </>
                      )}
                      {!order.is_proxy_order && order.status === 'ready' && onFinalizeOrder && (
                        <Button type="button" variant="secondary" size="sm" onClick={(event) => { event.stopPropagation(); onFinalizeOrder(order) }}>
                          <CheckCircle size={12} />
                          {t('acme.finalize')}
                        </Button>
                      )}
                      {order.certificate_id && onViewCertificate && (
                        <Button type="button" variant="secondary" size="sm" onClick={(event) => { event.stopPropagation(); onViewCertificate(order) }}>
                          <Eye size={12} />
                          {t('common.viewCertificate')}
                        </Button>
                      )}
                      {order.certificate_id && onDownloadCertificate && (
                        <Button type="button" variant="secondary" size="sm" onClick={(event) => { event.stopPropagation(); onDownloadCertificate(order) }}>
                          <DownloadSimple size={12} />
                          {t('common.download')}
                        </Button>
                      )}
                      {!order.is_proxy_order && (order.status === 'issued' || (order.status === 'valid' && (order.certificate_id || order.error_message))) && onRenewCertificate && (
                        <Button type="button" variant="secondary" size="sm" onClick={(event) => { event.stopPropagation(); onRenewCertificate(order) }}>
                          <ArrowsClockwise size={12} />
                          {t('acme.renew')}
                        </Button>
                      )}
                      {canDelete && onDeleteOrder && (
                        <Button type="button" variant="danger" size="sm" onClick={(event) => { event.stopPropagation(); onDeleteOrder(order) }}>
                          <Trash size={12} />
                          {t('common.delete')}
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
