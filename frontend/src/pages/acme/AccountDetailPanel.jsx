import { useTranslation } from 'react-i18next'
import { Key, Globe, ShieldCheck, CheckCircle, XCircle, Trash, Copy } from '@phosphor-icons/react'
import { Badge, Button, StatusIndicator, CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader } from '../../components'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks'
import { formatDate } from '../../lib/utils'

export default function AccountDetailPanel({ account, orders, challenges, detailTabs, activeDetailTab, onDetailTabChange, onDeactivate, onDelete }) {
  const { t } = useTranslation()
  const { showSuccess } = useNotification()
  const { copy } = useClipboard()

  return (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={Key}
        iconClass={account.status === 'valid' ? "bg-status-success-op20" : "bg-bg-tertiary"}
        title={account.contact?.[0]?.replace('mailto:', '') || account.email || t('acme.account')}
        subtitle={`ID: ${account.account_id?.substring(0, 24)}...`}
        badge={
          <Badge variant={account.status === 'valid' ? 'success' : 'secondary'} size="sm">
            {account.status === 'valid' && <CheckCircle size={10} weight="fill" />}
            {account.status}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Key, value: account.key_type || 'RSA-2048' },
        { icon: Globe, value: `${orders.length} ${t('acme.orders').toLowerCase()}` },
        { icon: ShieldCheck, value: `${challenges.length} ${t('common.challenges').toLowerCase()}` },
      ]} />

      <div className="flex gap-2">
        <Button 
          size="sm" 
          variant="secondary"
          className="flex-1"
          onClick={() => onDeactivate(account.id)}
          disabled={account.status !== 'valid'}
        >
          <XCircle size={14} />
          {t('common.deactivate')}
        </Button>
        <Button 
          size="sm" 
          variant="danger"
          onClick={() => onDelete(account.id)}
        >
          <Trash size={14} />
        </Button>
      </div>

      <div className="flex gap-1 border-b border-border">
        {detailTabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => onDetailTabChange(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
              activeDetailTab === tab.id
                ? 'border-accent-primary text-accent-primary'
                : 'border-transparent text-text-secondary hover:text-text-primary'
            }`}
          >
            <tab.icon size={14} />
            {tab.label}
            {tab.count > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-2xs rounded-full bg-bg-tertiary">
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {activeDetailTab === 'account' && (
        <div className="space-y-3">
          <CompactSection title={t('common.accountInformation')}>
            <CompactGrid>
              <CompactField autoIcon="email" label={t('common.email')} value={account.contact?.[0]?.replace('mailto:', '') || account.email} copyable />
              <CompactField autoIcon="status" label={t('common.status')}>
                <StatusIndicator status={account.status === 'valid' ? 'active' : 'inactive'}>
                  {account.status}
                </StatusIndicator>
              </CompactField>
              <CompactField autoIcon="keyType" label={t('common.keyType')} value={account.key_type || 'RSA-2048'} />
              <CompactField autoIcon="created" label={t('common.created')} value={formatDate(account.created_at)} />
            </CompactGrid>
          </CompactSection>

          <CompactSection title={t('acme.accountId')} collapsible defaultOpen={false}>
            <div className="relative group">
              <p className="font-mono text-2xs text-text-secondary break-all bg-tertiary-op50 p-2 rounded pr-8">
                {account.account_id}
              </p>
              <button
                type="button"
                onClick={() => { copy(account.account_id); showSuccess(t('common.copied')) }}
                className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary transition-all"
                aria-label={t('common.copy')}
              >
                <Copy size={14} />
              </button>
            </div>
          </CompactSection>

          <CompactSection title={t('acme.termsOfService')}>
            <div className="flex items-center gap-2 text-xs">
              {account.terms_of_service_agreed || account.tos_agreed ? (
                <>
                  <CheckCircle size={14} className="status-success-text" weight="fill" />
                  <span className="status-success-text">{t('acme.accepted')}</span>
                </>
              ) : (
                <>
                  <XCircle size={14} className="status-danger-text" weight="fill" />
                  <span className="status-danger-text">{t('acme.notAccepted')}</span>
                </>
              )}
            </div>
          </CompactSection>
        </div>
      )}

      {activeDetailTab === 'orders' && (
        <CompactSection title={`${orders.length} ${t('acme.orders')}`}>
          {orders.length === 0 ? (
            <p className="text-xs text-text-tertiary py-4 text-center">{t('acme.noCertificateOrders')}</p>
          ) : (
            <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
              {orders.map((order, i) => (
                <div key={i} className="p-3 bg-tertiary-op50 rounded-lg border border-border-op50 hover:border-border transition-colors">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-sm font-medium text-text-primary truncate flex-1">
                      {order.domain || order.identifier || t('common.unknown')}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {order.source === 'proxy' && (
                        <Badge variant="info" size="sm" title={order.environment || ''}>
                          {t('acme.proxy')}
                        </Badge>
                      )}
                      <Badge 
                        variant={
                          order.status?.toLowerCase() === 'valid' || order.status?.toLowerCase() === 'issued' ? 'success' : 
                          order.status?.toLowerCase() === 'pending' ? 'warning' :
                          order.status?.toLowerCase() === 'ready' ? 'info' :
                          'error'
                        } 
                        size="sm"
                      >
                        {order.status || t('common.unknown')}
                      </Badge>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">{t('acme.method')}</span>
                      <span className="text-text-secondary font-medium">{order.method || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">{t('common.expires')}</span>
                      <span className="text-text-secondary">{order.expires || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between col-span-2">
                      <span className="text-text-tertiary">{t('common.created')}</span>
                      <span className="text-text-secondary">{order.created_at ? formatDate(order.created_at) : 'N/A'}</span>
                    </div>
                    {order.order_id && (
                      <div className="flex justify-between col-span-2 mt-1 pt-1 border-t border-border-op30">
                        <span className="text-text-tertiary">{t('acme.orderId')}</span>
                        <span className="text-text-tertiary font-mono text-[10px] truncate max-w-[180px]" title={order.order_id}>
                          {order.order_id}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CompactSection>
      )}

      {activeDetailTab === 'challenges' && (
        <CompactSection title={`${challenges.length} ${t('common.challenges')}`}>
          {challenges.length === 0 ? (
            <p className="text-xs text-text-tertiary py-4 text-center">{t('acme.noActiveChallenges')}</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {challenges.map((ch, i) => (
                <div key={i} className="p-2 bg-tertiary-op30 rounded text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <Badge variant="secondary" size="sm">{ch.type}</Badge>
                    <Badge 
                      variant={ch.status === 'valid' ? 'success' : ch.status === 'pending' ? 'warning' : 'danger'} 
                      size="sm"
                    >
                      {ch.status}
                    </Badge>
                  </div>
                  <p className="text-text-secondary truncate">{ch.domain}</p>
                </div>
              ))}
            </div>
          )}
        </CompactSection>
      )}
    </div>
  )
}
