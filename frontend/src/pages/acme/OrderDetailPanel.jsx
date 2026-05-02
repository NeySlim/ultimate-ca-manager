import { useTranslation } from 'react-i18next'
import { Certificate, Globe, PlugsConnected, CheckCircle, Trash, Play, DownloadSimple, Eye, LockKey, ArrowsClockwise } from '@phosphor-icons/react'
import { Badge, Button, CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader } from '../../components'
import { cn, formatDate } from '../../lib/utils'

export default function OrderDetailPanel({ order, onDownloadCert, onViewCertificate, onRenewCertificate, onVerifyChallenge, onFinalizeOrder, onDeleteOrder }) {
  const { t } = useTranslation()

  return (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={Certificate}
        iconClass={cn(
          order.status === 'valid' || order.status === 'issued' ? "bg-status-success-op20" :
          order.status === 'invalid' ? "bg-status-error-op20" :
          order.status === 'pending' ? "bg-status-warning-op20" : "bg-bg-tertiary"
        )}
        title={order.primary_domain || order.domains?.[0]}
        subtitle={`${order.environment} • ${order.challenge_type}`}
        badge={
          <Badge 
            variant={order.status === 'valid' || order.status === 'issued' ? 'success' : 
                     order.status === 'invalid' ? 'danger' : 
                     order.status === 'pending' ? 'warning' : 'default'}
            size="sm"
          >
            {order.status}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Globe, value: `${(order.domains || []).length} ${t('acme.domains').toLowerCase()}` },
        { icon: PlugsConnected, value: order.dns_provider_name || t('acme.manualDns') },
      ]} />
      
      <CompactSection title={t('acme.domains')}>
        <div className="space-y-1">
          {(order.domains || []).map((domain, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <Globe size={12} className="text-text-tertiary" />
              <span className="text-text-primary">{domain}</span>
            </div>
          ))}
        </div>
      </CompactSection>
      
      <CompactSection title={t('acme.orderInfo')}>
        <CompactGrid>
          <CompactField autoIcon="environment" label={t('acme.environment')} value={order.environment === 'production' ? t('acme.production') : t('acme.staging')} />
          <CompactField autoIcon="method" label={t('acme.method')} value={order.challenge_type?.toUpperCase()} />
          <CompactField autoIcon="provider" label={t('acme.provider')} value={order.dns_provider_name || t('acme.manualDns')} />
          <CompactField autoIcon="status" label={t('common.status')} value={order.status} />
          <CompactField autoIcon="created" label={t('common.created')} value={formatDate(order.created_at)} />
          {order.expires_at && (
            <CompactField autoIcon="expires" label={t('common.expires')} value={formatDate(order.expires_at)} />
          )}
        </CompactGrid>
      </CompactSection>
      
      {order.status === 'pending' && order.challenges && (
        <CompactSection title={t('acme.pendingChallenge')}>
          <div className="space-y-3">
            {Object.entries(order.challenges).map(([domain, data]) => (
              <div key={domain} className="p-2 bg-tertiary-op50 rounded-lg border border-border-op50">
                <p className="text-sm font-medium text-text-primary mb-2">{domain}</p>
                {order.challenge_type === 'dns-01' && (
                  <div className="space-y-2 text-xs">
                    <CompactField autoIcon="dnsRecordName" label={t('acme.dnsRecordName')} value={data.dns_txt_name || data.record_name} mono copyable />
                    <CompactField autoIcon="dnsRecordValue" label={t('acme.dnsRecordValue')} value={data.dns_txt_value || data.record_value} mono copyable />
                  </div>
                )}
              </div>
            ))}
          </div>
        </CompactSection>
      )}
      
      {order.error_message && (
        <CompactSection title={t('common.error')}>
          <div className="p-2 bg-status-error-op10 border border-status-error-op20 rounded-lg">
            <p className="text-sm text-status-error">{order.error_message}</p>
          </div>
        </CompactSection>
      )}
      
      {(order.status === 'valid' || order.status === 'issued') && order.certificate_id && (
        <CompactSection title={t('acme.certificateActions')}>
          <div className="grid grid-cols-2 gap-2">
            <Button type="button" size="sm" variant="secondary" onClick={() => onDownloadCert(order, 'pem', false)}>
              <DownloadSimple size={12} />
              {t('acme.downloadCert')}
            </Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => onDownloadCert(order, 'pem', true)}>
              <LockKey size={12} />
              {t('acme.downloadWithKey')}
            </Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => onViewCertificate(order)}>
              <Eye size={12} />
              {t('common.viewCertificate')}
            </Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => onRenewCertificate(order)}>
              <ArrowsClockwise size={12} />
              {t('acme.renewNow')}
            </Button>
          </div>
        </CompactSection>
      )}
      
      <div className="flex flex-wrap gap-2 pt-2">
        {order.status === 'pending' && (
          <Button type="button" size="sm" onClick={() => onVerifyChallenge(order)}>
            <Play size={12} />
            {t('acme.verifyChallenge')}
          </Button>
        )}
        {order.status === 'processing' && (
          <Button type="button" size="sm" onClick={() => onFinalizeOrder(order)}>
            <CheckCircle size={12} />
            {t('acme.finalize')}
          </Button>
        )}
        <Button type="button" size="sm" variant="danger" onClick={() => onDeleteOrder(order)}>
          <Trash size={12} />
          {t('common.delete')}
        </Button>
      </div>
    </div>
  )
}
