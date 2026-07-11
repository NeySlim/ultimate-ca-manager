/**
 * Public endpoints panel — effective URLs, preflight, host-role status.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Globe, MagnifyingGlass, CheckCircle, XCircle, WarningCircle } from '@phosphor-icons/react'
import { Button, Badge, DetailSection } from '../../components'
import { useNotification } from '../../contexts'
import { settingsService } from '../../services'
import CopyableUrl from './CopyableUrl'

function StatusBadge({ status }) {
  const { t } = useTranslation()
  if (status === 'ok') {
    return (
      <Badge variant="success" size="sm">
        <CheckCircle size={12} className="mr-1 inline" />
        {t('settings.publicEndpoints.statusOk')}
      </Badge>
    )
  }
  if (status === 'fail') {
    return (
      <Badge variant="danger" size="sm">
        <XCircle size={12} className="mr-1 inline" />
        {t('settings.publicEndpoints.statusFail')}
      </Badge>
    )
  }
  if (status === 'warn') {
    return (
      <Badge variant="warning" size="sm">
        <WarningCircle size={12} className="mr-1 inline" />
        {t('settings.publicEndpoints.statusWarn')}
      </Badge>
    )
  }
  return (
    <Badge variant="secondary" size="sm">
      {t('settings.publicEndpoints.statusSkip')}
    </Badge>
  )
}

export default function PublicEndpointsPanel({ settings, updateSetting, refreshKey = 0 }) {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()
  const [effective, setEffective] = useState(null)
  const [preflight, setPreflight] = useState(null)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(false)

  const loadEffective = useCallback(async () => {
    setLoading(true)
    try {
      const res = await settingsService.getPublicEndpoints()
      setEffective(res.data || res)
    } catch (e) {
      showError(e.message || t('settings.publicEndpoints.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [showError, t])

  useEffect(() => {
    loadEffective()
  }, [loadEffective, refreshKey, settings.base_url, settings.acme_public_vhost])

  const runPreflight = async () => {
    setChecking(true)
    try {
      const res = await settingsService.preflightPublicEndpoints()
      setPreflight(res.data || res)
      showSuccess(t('settings.publicEndpoints.preflightDone'))
    } catch (e) {
      showError(e.message || t('settings.publicEndpoints.preflightFailed'))
    } finally {
      setChecking(false)
    }
  }

  const detectFromBrowser = () => {
    const { protocol, hostname, port } = window.location
    if (!hostname) return
    const p = port ? `:${port}` : ''
    updateSetting('base_url', `${protocol}//${hostname}${p}`)
    showSuccess(t('settings.publicEndpoints.detected'))
  }

  const eff = effective || {}

  return (
    <DetailSection title={t('settings.publicEndpoints.title')} icon={Globe} iconClass="icon-bg-cyan">
      <p className="text-sm text-text-secondary mb-4">{t('settings.publicEndpoints.subtitle')}</p>

      <div className="flex flex-wrap gap-2 mb-4">
        <Button type="button" variant="secondary" size="sm" onClick={detectFromBrowser}>
          {t('settings.publicEndpoints.detectFromBrowser')}
        </Button>
        <Button type="button" variant="secondary" size="sm" onClick={runPreflight} disabled={checking}>
          <MagnifyingGlass size={14} />
          {checking ? t('common.loading') : t('settings.publicEndpoints.runPreflight')}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={loadEffective} disabled={loading}>
          {t('settings.publicEndpoints.refresh')}
        </Button>
      </div>

      {eff.env_locked?.fqdn_env && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mb-3 flex items-center gap-1">
          <WarningCircle size={14} />
          {t('settings.publicEndpoints.fqdnEnvLocked')}
        </p>
      )}

      {eff.host_role_ok === false && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mb-3 flex items-center gap-1">
          <WarningCircle size={14} />
          {t('settings.publicEndpoints.wrongHost', { host: eff.request_host, admin: eff.admin?.host })}
        </p>
      )}

      <div className="space-y-3 mb-4">
        {eff.admin?.canonical_origin && (
          <CopyableUrl
            label={t('settings.publicEndpoints.adminCanonical')}
            value={eff.admin.canonical_origin}
            description={t('settings.publicEndpoints.adminCanonicalDesc')}
          />
        )}
        {eff.protocol?.effective_url && (
          <CopyableUrl
            label={t('settings.publicEndpoints.protocolEffective')}
            value={eff.protocol.effective_url}
            description={t('settings.publicEndpoints.protocolEffectiveDesc')}
          />
        )}
        {eff.acme?.directory_url && (
          <CopyableUrl
            label={t('settings.publicEndpoints.acmeDirectory')}
            value={eff.acme.directory_url}
          />
        )}
        {eff.acme?.proxy_url && (
          <CopyableUrl
            label={t('settings.publicEndpoints.acmeProxy')}
            value={eff.acme.proxy_url}
          />
        )}
        {eff.acme?.split_topology && (
          <Badge variant="info" size="sm">{t('settings.publicEndpoints.splitTopology')}</Badge>
        )}
      </div>

      {preflight?.checks?.length > 0 && (
        <div className="rounded-lg border border-border p-3 space-y-2">
          <p className="text-xs font-medium text-text-secondary">{t('settings.publicEndpoints.preflightResults')}</p>
          {preflight.corporate_dns_servers?.length > 0 && (
            <p className="text-xs text-text-muted">
              {t('settings.publicEndpoints.corporateDnsServers', {
                servers: preflight.corporate_dns_servers.join(', '),
              })}
            </p>
          )}
          {preflight.checks.map((c) => (
            <div key={c.label} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-mono text-text-primary">{c.label}</span>
              <span className="text-text-muted">{c.host || '—'}</span>
              {c.dns_local != null && c.dns_local !== 'skip' ? (
                <>
                  <span className="text-xs text-text-muted">{t('settings.publicEndpoints.dnsLocal')}</span>
                  <StatusBadge status={c.dns_local} />
                </>
              ) : null}
              {c.dns_internal != null && c.dns_internal !== 'skip' ? (
                <>
                  <span className="text-xs text-text-muted">{t('settings.publicEndpoints.dnsInternal')}</span>
                  <StatusBadge status={c.dns_internal} />
                </>
              ) : null}
              {c.dns_public != null && c.dns_public !== 'skip' ? (
                <>
                  <span className="text-xs text-text-muted">{t('settings.publicEndpoints.dnsPublic')}</span>
                  <StatusBadge status={c.dns_public} />
                </>
              ) : (
                <StatusBadge status={c.dns} />
              )}
              {c.tls !== 'skip' && <StatusBadge status={c.tls} />}
              {c.detail && <span className="text-xs text-text-muted truncate max-w-full">{c.detail}</span>}
            </div>
          ))}
        </div>
      )}
    </DetailSection>
  )
}
