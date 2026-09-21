import { useTranslation } from 'react-i18next'
import { IdentificationBadge, TestTube, Power, PencilSimple, ArrowsClockwise } from '@phosphor-icons/react'
import { Button, Badge, HelpCard, DetailHeader, DetailContent } from '../../components'
import { formatDate } from '../../lib/utils'
import CopyableUrl from './CopyableUrl'

export default function AdConnectorSection({ adConnectorConfig, adConnectorLoading, adConnectorTesting, handleAdConnectorEdit, handleAdConnectorToggle, handleAdConnectorTest, hasPermission }) {
  const { t } = useTranslation()
  const configured = Boolean(adConnectorConfig?.server)
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''
  // Summarise rather than list: the row is one line, and a domain with
  // four DCs would push the enabled/disabled badge off it.
  const servers = adConnectorConfig?.servers || []
  const summary = servers.length > 1
    ? t('adConnector.serverSummary', { server: servers[0], port: adConnectorConfig.port, count: servers.length - 1 })
    : `${adConnectorConfig?.server}:${adConnectorConfig?.port}`
  const testMark = { success: '✓', partial: '!' }[adConnectorConfig?.last_test_result] || '✗'
  // The probe's verdict sits next to the enabled/disabled switch: a
  // connector that is enabled but cannot reach a single DC is not "on" in
  // any useful sense, and that is exactly what an operator needs to see
  // without opening the dialog.
  const healthState = adConnectorConfig?.health?.state
  const healthBadge = {
    down: { variant: 'danger', label: t('adConnector.healthStateDown') },
    degraded: { variant: 'warning', label: t('adConnector.healthStateDegraded') },
  }[healthState]

  return (
    <DetailContent>
      <DetailHeader
        icon={IdentificationBadge}
        title={t('adConnector.title')}
        subtitle={t('adConnector.subtitle')}
      />

      <HelpCard variant="info" title={t('adConnector.helpTitle')} className="mb-4">
        {t('adConnector.helpDescription')}
      </HelpCard>

      <HelpCard variant="tip" title={t('adConnector.gpoUrlsTitle')} className="mb-4">
        <p className="mb-3">{t('adConnector.gpoUrlsDescription')}</p>
        <div className="space-y-3">
          <CopyableUrl
            label={t('adConnector.gpoUsernamePasswordUrl')}
            value={`${baseUrl}/ADPolicyProvider_CEP_UsernamePassword/service.svc`}
            description={t('adConnector.gpoUsernamePasswordUrlDesc')}
          />
          <CopyableUrl
            label={t('adConnector.gpoKerberosUrl')}
            value={`${baseUrl}/ADPolicyProvider_CEP_Kerberos/service.svc`}
            description={t('adConnector.gpoKerberosUrlDesc')}
          />
        </div>
      </HelpCard>

      {adConnectorLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
        </div>
      ) : (
        <div className="flex items-center justify-between p-4 bg-tertiary-50 border border-border rounded-lg">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center icon-bg-blue">
              <IdentificationBadge size={20} weight="bold" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-medium text-text-primary">{t('adConnector.title')}</span>
                {configured ? (
                  <>
                    <Badge variant={adConnectorConfig.enabled ? 'success' : 'secondary'} size="sm">
                      {adConnectorConfig.enabled ? t('common.enabled') : t('common.disabled')}
                    </Badge>
                    {adConnectorConfig.enabled && healthBadge && (
                      <Badge variant={healthBadge.variant} size="sm">{healthBadge.label}</Badge>
                    )}
                  </>
                ) : (
                  <Badge variant="secondary" size="sm">{t('adConnector.notConfigured')}</Badge>
                )}
              </div>
              <p className="text-xs text-text-secondary">
                {configured ? summary : t('adConnector.notConfiguredDesc')}
              </p>
              {adConnectorConfig?.last_test_at && (
                <p className="text-xs text-text-tertiary">
                  {t('adConnector.testConnection')}: {testMark} {formatDate(adConnectorConfig.last_test_at)}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {configured && (
              <>
                <Button type="button" size="sm" variant="secondary" onClick={handleAdConnectorTest} disabled={adConnectorTesting} title={t('adConnector.testConnection')}>
                  {adConnectorTesting ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
                </Button>
                {hasPermission('write:ad_connector') && (
                  <Button type="button" size="sm" variant="secondary" onClick={handleAdConnectorToggle} title={adConnectorConfig.enabled ? t('common.disable') : t('common.enable')}>
                    <Power size={14} />
                  </Button>
                )}
              </>
            )}
            {hasPermission('write:ad_connector') && (
              <Button type="button" size="sm" variant="secondary" onClick={handleAdConnectorEdit} title={t('common.edit')}>
                <PencilSimple size={14} />
              </Button>
            )}
          </div>
        </div>
      )}
    </DetailContent>
  )
}
