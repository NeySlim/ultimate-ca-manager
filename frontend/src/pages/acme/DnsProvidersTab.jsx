import { useTranslation } from 'react-i18next'
import { Plus, Trash, Play, Gear, PlugsConnected } from '@phosphor-icons/react'
import { Button, Badge, Card, HelpCard } from '../../components'
import { cn } from '../../lib/utils'

export default function DnsProvidersTab({ dnsProviders, onAddProvider, onEditProvider, onTestProvider, onDeleteProvider, canWrite, canDelete }) {
  const { t } = useTranslation()

  return (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('acme.dnsProviders')} compact>
        {t('acme.dnsProvidersAboutDesc')}
      </HelpCard>
      
      <div className="flex flex-wrap items-center gap-2">
        {canWrite && (
          <Button type="button" onClick={onAddProvider}>
            <Plus size={14} />
            {t('common.addDnsProvider')}
          </Button>
        )}
      </div>
      
      {dnsProviders.length === 0 ? (
        <div className="text-center py-8 text-text-secondary">
          <PlugsConnected size={40} className="mx-auto mb-2 opacity-40" />
          <p>{t('acme.noDnsProviders')}</p>
          <p className="text-sm text-text-tertiary mt-1">{t('acme.noDnsProvidersDesc')}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {dnsProviders.map(provider => (
            <Card key={provider.id} className="p-4">
              <div className="flex items-center justify-between gap-3 mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                    provider.is_default ? "icon-bg-emerald" : "icon-bg-violet"
                  )}>
                    <PlugsConnected size={16} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">{provider.name}</p>
                    <p className="text-xs text-text-tertiary">{provider.provider_type}</p>
                  </div>
                </div>
                {provider.is_default && (
                  <Badge variant="success" size="sm">{t('common.default')}</Badge>
                )}
              </div>
              
              <div className="flex gap-2 mt-3">
                <Button 
                  size="sm" 
                  variant="secondary"
                  onClick={() => onTestProvider(provider)}
                >
                  <Play size={12} />
                  {t('common.test')}
                </Button>
                {canWrite && (
                  <Button 
                    size="sm" 
                    variant="secondary"
                    onClick={() => onEditProvider(provider)}
                  >
                    <Gear size={12} />
                    {t('common.edit')}
                  </Button>
                )}
                {canDelete && (
                  <Button 
                    size="sm" 
                    variant="danger"
                    onClick={() => onDeleteProvider(provider)}
                  >
                    <Trash size={12} />
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
