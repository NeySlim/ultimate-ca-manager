/**
 * Public endpoints panel — effective URLs, preflight, host-role status.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, Pill, Notice, RecordList, RecordRow, Section } from '../../components/atelier'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks/useClipboard'
import { settingsService } from '../../services'

// The state of one check as the mockup's badge: tone and icon, so the colour is never the only signal
const STATUS = { ok: ['good', 'statusOk'], fail: ['bad', 'statusFail'], warn: ['warn', 'statusWarn'] }
function StatusBadge({ status }) {
  const { t } = useTranslation()
  const [tone, key] = STATUS[status] || ['muted', 'statusSkip']
  return <Pill tone={tone} label={t(`settings.publicEndpoints.${key}`)} />
}

/** A URL to copy, as a record of the mockup's list: its name, the URL, its description, copy at the right. */
function UrlRecord({ label, value, description }) {
  const { showInfo } = useNotification()
  const { t } = useTranslation()
  const { copy } = useClipboard()
  // Only confirm a copy that actually reached the clipboard: over plain HTTP the async clipboard API is not there
  const handleCopy = async () => {
    if (await copy(value)) showInfo(t('common.copiedToClipboard'))
  }
  return (
    <RecordRow title={label} meta={<span className="mono url">{value}</span>}
      extra={description && <span className="rl-meta">{description}</span>}
      action={<IconBtn icon="copy" label={t('common.copy')} onClick={handleCopy} />} />
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

  const checks = (c) => [
    ['dns_local', 'dnsLocal'], ['dns_internal', 'dnsInternal'],
  ].filter(([k]) => c[k] != null && c[k] !== 'skip').map(([k, word]) => (
    <span key={k} className="rl-meta">{t(`settings.publicEndpoints.${word}`)} <StatusBadge status={c[k]} /></span>
  ))

  return (
    <SettingsGroup legend={t('settings.publicEndpoints.title')} hint={t('settings.publicEndpoints.subtitle')} grid={false}>
      <div className="settings-actions">
        <Btn onClick={detectFromBrowser} disabled={adminLocked}>{t('settings.publicEndpoints.detectFromBrowser')}</Btn>
        <Btn icon="search" onClick={runPreflight} disabled={checking}>
          {checking ? t('common.loading') : t('settings.publicEndpoints.runPreflight')}
        </Btn>
        <Btn tone="quiet" icon="refresh" onClick={loadEffective} disabled={loading}>{t('settings.publicEndpoints.refresh')}</Btn>
      </div>
      {eff.env_locked?.fqdn_env && <Notice tone="warn">{t('settings.publicEndpoints.fqdnEnvLocked')}</Notice>}
      {eff.host_role_ok === false && (
        <Notice tone="warn">{t('settings.publicEndpoints.wrongHost', { host: eff.request_host, admin: eff.admin?.host })}</Notice>
      )}
      <ul className="record-list">
        {eff.admin?.canonical_origin && (
          <UrlRecord label={t('settings.publicEndpoints.adminCanonical')} value={eff.admin.canonical_origin}
            description={t('settings.publicEndpoints.adminCanonicalDesc')} />
        )}
        {eff.protocol?.effective_url && (
          <UrlRecord label={t('settings.publicEndpoints.protocolEffective')} value={eff.protocol.effective_url}
            description={t('settings.publicEndpoints.protocolEffectiveDesc')} />
        )}
        {eff.acme?.directory_url && <UrlRecord label={t('settings.publicEndpoints.acmeDirectory')} value={eff.acme.directory_url} />}
        {eff.acme?.proxy_url && <UrlRecord label={t('settings.publicEndpoints.acmeProxy')} value={eff.acme.proxy_url} />}
      </ul>
      {eff.acme?.split_topology && <p className="group-hint"><Pill tone="muted" icon="help" label={t('settings.publicEndpoints.splitTopology')} /></p>}
      {preflight?.checks?.length > 0 && (
        <Section title={t('settings.publicEndpoints.preflightResults')}>
          {preflight.corporate_dns_servers?.length > 0 && (
            <p className="group-hint">{t('settings.publicEndpoints.corporateDnsServers', { servers: preflight.corporate_dns_servers.join(', ') })}</p>
          )}
          <RecordList>
            {preflight.checks.map((c) => (
              <RecordRow key={c.label} title={c.label} meta={[c.host || '—', c.detail].filter(Boolean).join(' · ')}
                action={<>
                  {checks(c)}
                  {c.dns_public != null && c.dns_public !== 'skip'
                    ? <span className="rl-meta">{t('settings.publicEndpoints.dnsPublic')} <StatusBadge status={c.dns_public} /></span>
                    : <StatusBadge status={c.dns} />}
                  {c.tls !== 'skip' && <StatusBadge status={c.tls} />}
                </>} />
            ))}
          </RecordList>
        </Section>
      )}
    </SettingsGroup>
  )
}
