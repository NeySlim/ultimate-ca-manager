/**
 * Public endpoints panel — effective URLs, preflight, host-role status.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MagnifyingGlass, CheckCircle, XCircle, WarningCircle } from '@phosphor-icons/react'
import { Button, Badge } from '../../components'
import { HelpCard } from '../../components/HelpCard'
import { useNotification } from '../../contexts'
import { settingsService } from '../../services'
import CopyableUrl from './CopyableUrl'
import { FormGroup } from '../../components/sectioned'

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

export default function PublicEndpointsPanel({ settings, updateSetting, refreshKey = 0, adminLocked = false }) {
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
    <FormGroup title={t('settings.publicEndpoints.title')} description={t('settings.publicEndpoints.subtitle')}>
      <div className="sf-stack">
        <div className="sf-actions-row">
          <Button type="button" variant="secondary" onClick={detectFromBrowser} disabled={adminLocked}>
            {t('settings.publicEndpoints.detectFromBrowser')}
          </Button>
          <Button type="button" variant="secondary" onClick={runPreflight} disabled={checking}>
            <MagnifyingGlass size={16} />
            {checking ? t('common.loading') : t('settings.publicEndpoints.runPreflight')}
          </Button>
          <Button type="button" variant="ghost" onClick={loadEffective} disabled={loading}>
            {t('settings.publicEndpoints.refresh')}
          </Button>
        </div>

        {eff.env_locked?.fqdn_env && (
          <HelpCard variant="warning">{t('settings.publicEndpoints.fqdnEnvLocked')}</HelpCard>
        )}

        {eff.host_role_ok === false && (
          <HelpCard variant="warning">
            {t('settings.publicEndpoints.wrongHost', { host: eff.request_host, admin: eff.admin?.host })}
          </HelpCard>
        )}

        <div>
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
        </div>
        {eff.acme?.split_topology && (
          <p className="sf-hint"><Badge variant="info" size="sm">{t('settings.publicEndpoints.splitTopology')}</Badge></p>
        )}

        {preflight?.checks?.length > 0 && (
          <div>
            <h4>{t('settings.publicEndpoints.preflightResults')}</h4>
            {preflight.corporate_dns_servers?.length > 0 && (
              <p className="sf-hint">
                {t('settings.publicEndpoints.corporateDnsServers', {
                  servers: preflight.corporate_dns_servers.join(', '),
                })}
              </p>
            )}
            <ul className="sf-records">
              {preflight.checks.map((c) => (
                <li key={c.label}>
                  <div className="sf-record-main">
                    <strong>{c.label}</strong>
                    <span className="sf-record-meta">{[c.host || '—', c.detail].filter(Boolean).join(' · ')}</span>
                  </div>
                  <div className="sf-record-actions">
                    {c.dns_local != null && c.dns_local !== 'skip' ? (
                      <>
                        <span className="sf-record-meta">{t('settings.publicEndpoints.dnsLocal')}</span>
                        <StatusBadge status={c.dns_local} />
                      </>
                    ) : null}
                    {c.dns_internal != null && c.dns_internal !== 'skip' ? (
                      <>
                        <span className="sf-record-meta">{t('settings.publicEndpoints.dnsInternal')}</span>
                        <StatusBadge status={c.dns_internal} />
                      </>
                    ) : null}
                    {c.dns_public != null && c.dns_public !== 'skip' ? (
                      <>
                        <span className="sf-record-meta">{t('settings.publicEndpoints.dnsPublic')}</span>
                        <StatusBadge status={c.dns_public} />
                      </>
                    ) : (
                      <StatusBadge status={c.dns} />
                    )}
                    {c.tls !== 'skip' && <StatusBadge status={c.tls} />}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </FormGroup>
  )
}
