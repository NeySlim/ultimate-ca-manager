import { useTranslation } from 'react-i18next'
import {
  Plus, Trash, CheckCircle, ArrowsClockwise, Key, Warning,
  Copy, CaretRight, LockKey, PlugsConnected, ClockCounterClockwise, Gear, ShieldCheck
} from '@phosphor-icons/react'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { HelpCard, Button, Badge, CompactSection, Select, Input } from '../../components'
import { useClipboard } from '../../hooks'
import { cn, publicBaseUrl } from '../../lib/utils'

export default function LetsEncryptTab({
  clientSettings,
  localContactEmail,
  onLocalContactEmailChange,
  localProxyUpstreamUrl,
  onLocalProxyUpstreamUrlChange,
  localProxyEabKid,
  onLocalProxyEabKidChange,
  proxyEabHmacInput,
  onProxyEabHmacInputChange,
  proxyEmail,
  onProxyEmailChange,
  testingConnection,
  connectionResult,
  onBlurSave,
  onBlurSaveInt,
  localDnsTimeout,
  onLocalDnsTimeoutChange,
  localDnsDelay,
  onLocalDnsDelayChange,
  localDnsNameservers,
  onLocalDnsNameserversChange,
  onUpdateClientSetting,
  onRegisterProxy,
  onUnregisterProxy,
  onProxyAccountChange,
  caAccounts = [],
  onResetProxyAccount,
  onTestConnection,
  onRequestCertificate,
  onRefresh,
  canWrite,
}) {
  const { t } = useTranslation()
  const { copy } = useClipboard()

  const proxyAccountId = clientSettings.proxy_acme_account_id ?? null
  const selectedProxyAccount = caAccounts.find(a => a.id === proxyAccountId)
  const publicProxyBase = publicBaseUrl(clientSettings.acme_proxy_public_base_url, '/acme/proxy')
  const proxyServerBase = selectedProxyAccount?.proxy_enabled && selectedProxyAccount?.proxy_slug
    ? `${publicProxyBase}/${selectedProxyAccount.proxy_slug}`
    : publicProxyBase
  const proxyDirectoryUrl = `${proxyServerBase}/directory`
  const enabledProxyAccounts = caAccounts.filter(a => a.proxy_enabled && a.proxy_slug)
  const proxyAccountOptions = caAccounts.map(a => ({
    value: String(a.id),
    label: `${a.label}${a.is_default ? ` (${t('common.default')})` : ''}${a.is_registered ? '' : `: ${t('acme.notRegistered')}`}`,
  }))

  return (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('acme.letsEncryptAbout')} compact>
        {t('acme.letsEncryptAboutDesc')}
      </HelpCard>

      {/* Request Certificate Button */}
      <div className="flex flex-wrap items-center gap-2">
        {canWrite && (
          <Button type="button" onClick={onRequestCertificate}>
            <Plus size={14} />
            {t('acme.requestCertificate')}
          </Button>
        )}
        <Button type="button" variant="secondary" onClick={onRefresh}>
          <ArrowsClockwise size={14} />
          {t('common.refresh')}
        </Button>
      </div>

      {/* Info about History tab */}
      <HelpCard variant="info" compact>
        <span className="flex items-center gap-2">
          <ClockCounterClockwise size={16} />
          {t('acme.viewHistoryForCertificates')}
        </span>
      </HelpCard>

      {/* Client Settings */}
      <CompactSection title={t('acme.clientSettings')} icon={Gear}>
        <div className="space-y-3">
          <Select
            label={t('acme.defaultEnvironment')}
            value={clientSettings.environment || 'staging'}
            onChange={(val) => onUpdateClientSetting('environment', val)}
            disabled={!canWrite}
            options={[
              { value: 'staging', label: t('acme.staging') + ' (Test)' },
              { value: 'production', label: t('acme.production') + ' (Live)' }
            ]}
            helperText={t('acme.environmentHelper')}
          />

          <Input
            label={t('acme.contactEmail')}
            type="email"
            value={localContactEmail}
            onChange={(e) => onLocalContactEmailChange(e.target.value)}
            onBlur={() => onBlurSave('email', localContactEmail, onLocalContactEmailChange)}
            disabled={!canWrite}
            helperText={t('acme.contactEmailHelper')}
          />

          <ToggleSwitch
            checked={clientSettings.renewal_enabled ?? true}
            onChange={(val) => onUpdateClientSetting('renewal_enabled', val)}
            disabled={!canWrite}
            label={t('acme.autoRenewal')}
            description={t('acme.autoRenewalDesc')}
          />

          <ToggleSwitch
            checked={clientSettings.verify_ssl ?? true}
            onChange={(val) => onUpdateClientSetting('verify_ssl', val)}
            disabled={!canWrite}
            label={t('sso.verifySsl')}
          />

          {clientSettings.verify_ssl === false && (
            <div className="p-3 rounded-lg status-warning-bg status-warning-border border">
              <p className="text-xs status-warning-text">{t('sso.sslWarning')}</p>
            </div>
          )}

          <Input
            label={t('acme.dnsPropagationTimeout')}
            type="number"
            min="0"
            max="3600"
            value={localDnsTimeout}
            onChange={(e) => onLocalDnsTimeoutChange(e.target.value)}
            onBlur={() => onBlurSaveInt('dns_propagation_timeout', localDnsTimeout, onLocalDnsTimeoutChange, { min: 0, max: 3600, fallback: 120 })}
            disabled={!canWrite}
            helperText={t('acme.dnsPropagationTimeoutHelper')}
          />

          <Input
            label={t('acme.dnsPropagationDelay')}
            type="number"
            min="0"
            max="300"
            value={localDnsDelay}
            onChange={(e) => onLocalDnsDelayChange(e.target.value)}
            onBlur={() => onBlurSaveInt('dns_propagation_delay', localDnsDelay, onLocalDnsDelayChange, { min: 0, max: 300, fallback: 10 })}
            disabled={!canWrite}
            helperText={t('acme.dnsPropagationDelayHelper')}
          />

          <Select
            label={t('acme.dnsResolverMode')}
            value={clientSettings.dns01_resolver_mode || 'auto'}
            onChange={(val) => onUpdateClientSetting('dns01_resolver_mode', val)}
            disabled={!canWrite}
            options={[
              { value: 'auto', label: t('acme.dnsResolverModeAuto') },
              { value: 'system', label: t('acme.dnsResolverModeSystem') },
              { value: 'custom', label: t('acme.dnsResolverModeCustom') },
            ]}
            helperText={t('acme.dnsResolverModeHelper')}
          />

          {(clientSettings.dns01_resolver_mode || 'auto') !== 'system' && (
            <Input
              label={t('acme.dnsResolvers')}
              value={localDnsNameservers}
              onChange={(e) => onLocalDnsNameserversChange(e.target.value)}
              onBlur={() => onBlurSave('dns01_nameservers', localDnsNameservers, onLocalDnsNameserversChange)}
              placeholder="10.0.0.53, 127.0.0.1:5353"
              disabled={!canWrite}
              helperText={t('acme.dnsResolversHelper')}
            />
          )}

          <ToggleSwitch
            checked={clientSettings.debug_logging ?? false}
            onChange={(val) => onUpdateClientSetting('debug_logging', val)}
            disabled={!canWrite}
            label={t('acme.debugLogging')}
            description={t('acme.debugLoggingDesc')}
          />

          <ToggleSwitch
            checked={clientSettings.allow_loopback_upstream ?? false}
            onChange={(val) => onUpdateClientSetting('allow_loopback_upstream', val)}
            disabled={!canWrite}
            label={t('acme.allowLoopbackUpstream')}
            description={t('acme.allowLoopbackUpstreamDesc')}
          />

          <Input
            label={t('acme.tlsAlpnPort')}
            type="number"
            value={clientSettings.tls_alpn_port ?? 443}
            onChange={(e) => onUpdateClientSetting('tls_alpn_port', parseInt(e.target.value) || 443)}
            min="1"
            max="65535"
            disabled={!canWrite}
            helperText={t('acme.tlsAlpnPortHelper')}
          />

          <Select
            label={t('acme.keyType')}
            value={clientSettings.key_type || 'RSA-2048'}
            onChange={(val) => onUpdateClientSetting('key_type', val)}
            disabled={!canWrite}
            options={[
              { value: 'RSA-2048', label: 'RSA 2048' },
              { value: 'RSA-4096', label: 'RSA 4096' },
              { value: 'EC-P256', label: 'ECDSA P-256' },
              { value: 'EC-P384', label: 'ECDSA P-384' },
            ]}
            helperText={t('acme.keyTypeHelper')}
          />

          <Select
            label={t('acme.accountKeyType')}
            value={clientSettings.account_key_type || 'ES256'}
            onChange={(val) => onUpdateClientSetting('account_key_type', val)}
            disabled={!canWrite}
            options={[
              { value: 'ES256', label: 'ECDSA P-256 (ES256)' },
              { value: 'ES384', label: 'ECDSA P-384 (ES384)' },
              { value: 'RS256', label: 'RSA 2048 (RS256)' },
            ]}
            helperText={t('acme.accountKeyTypeHelper')}
          />
        </div>
      </CompactSection>

      {/* ACME Proxy */}
      <CompactSection title={t('acme.acmeProxy')} icon={ShieldCheck}>
        <div className="space-y-3">
          <ToggleSwitch
            checked={clientSettings.proxy_enabled || false}
            onChange={(val) => onUpdateClientSetting('proxy_enabled', val)}
            disabled={!canWrite}
            label={t('acme.enableAcmeProxy')}
            description={t('acme.enableAcmeProxyDesc')}
          />

          {clientSettings.proxy_enabled && (
            <>
              <Select
                label={t('acme.proxyUpstreamCAAccount')}
                value={proxyAccountId != null ? String(proxyAccountId) : ''}
                onChange={(val) => onProxyAccountChange(val ? parseInt(val, 10) : null)}
                disabled={!canWrite || caAccounts.length === 0}
                options={[
                  { value: '', label: t('acme.proxySelectCaAccount') },
                  ...proxyAccountOptions,
                ]}
                helperText={
                  caAccounts.length === 0
                    ? t('acme.proxyNoCaAccounts')
                    : t('acme.proxyUpstreamCAAccountHelper')
                }
              />

              {selectedProxyAccount && (
                <p className="text-xs text-text-tertiary font-mono break-all">
                  {selectedProxyAccount.directory_url}
                </p>
              )}

              <ToggleSwitch
                checked={clientSettings.proxy_verify_ssl ?? true}
                onChange={(val) => onUpdateClientSetting('proxy_verify_ssl', val)}
                disabled={!canWrite}
                label={t('sso.verifySsl')}
              />

              {clientSettings.proxy_verify_ssl === false && (
                <div className="p-3 rounded-lg status-warning-bg status-warning-border border">
                  <p className="text-xs status-warning-text">{t('sso.sslWarning')}</p>
                </div>
              )}

              <ToggleSwitch
                checked={clientSettings.proxy_prune_replaced_certificates ?? false}
                onChange={(val) => onUpdateClientSetting('proxy_prune_replaced_certificates', val)}
                disabled={!canWrite}
                label={t('acme.proxyPruneReplacedCertificates')}
                description={t('acme.proxyPruneReplacedCertificatesDesc')}
              />

              {selectedProxyAccount && (
                <p className="text-xs text-text-tertiary">{t('acme.proxyManageCaAccountsHint')}</p>
              )}

              {/* Account Registration Status */}
              {proxyAccountId && selectedProxyAccount?.is_registered ? (() => {
                const accountUrl = clientSettings.proxy_account_url || selectedProxyAccount.account_url || ''

                return (
                  <div className="p-3 rounded-lg border status-success-bg status-success-border">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <CheckCircle size={18} className="status-success-text" weight="fill" />
                        <div>
                          <p className="text-sm font-medium text-text-primary">
                            {t('acme.upstreamAccountRegistered')}
                          </p>
                          <p className="text-xs text-text-secondary font-mono">
                            {accountUrl ? `...${accountUrl.slice(-30)}` : t('acme.accountRegistered')}
                          </p>
                          <p className="text-xs text-text-tertiary mt-1">{selectedProxyAccount.label}</p>
                        </div>
                      </div>
                      {canWrite && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={onResetProxyAccount}
                          title={t('acme.resetAccount')}
                          className="status-danger-text hover:status-danger-bg"
                        >
                          <ArrowsClockwise size={14} />
                        </Button>
                      )}
                    </div>
                  </div>
                )
              })() : proxyAccountId ? (
                <div className="p-3 rounded-lg bg-tertiary-op30 border border-border">
                  <div className="flex items-center gap-2">
                    <Warning size={18} className="text-text-tertiary" />
                    <div>
                      <p className="text-sm text-text-secondary">{t('acme.upstreamAccountNotRegistered')}</p>
                      <p className="text-xs text-text-tertiary">{t('acme.willAutoRegister')}</p>
                    </div>
                  </div>
                </div>
              ) : null}

              {/* Connection Test */}
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={onTestConnection}
                  disabled={testingConnection || !proxyAccountId}
                >
                  {testingConnection ? <ArrowsClockwise size={14} className="animate-spin" /> : <PlugsConnected size={14} />}
                  {t('acme.testConnection')}
                </Button>
                {connectionResult && (
                  <span className={cn('text-xs', connectionResult.connected ? 'status-success-text' : 'status-danger-text')}>
                    {connectionResult.connected
                      ? `✓ ${connectionResult.ca_name || t('common.connected')}${connectionResult.eab_required ? ` (${t('acme.eabRequired')})` : ''}`
                      : `✗ ${connectionResult.error || t('acme.connectionFailed')}`}
                  </span>
                )}
              </div>

              {/* Proxy Endpoint & Usage */}
              <div className="p-3 bg-tertiary-op50 rounded-lg space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium text-text-secondary">{t('acme.proxyPathUrl')}</p>
                  <Button type="button" variant="ghost" size="sm" onClick={() => copy(proxyDirectoryUrl)}>
                    <Copy size={12} />
                  </Button>
                </div>
                <code className="block text-xs text-accent-primary font-mono bg-bg-secondary p-2 rounded break-all">
                  {proxyDirectoryUrl}
                </code>
                {!selectedProxyAccount?.proxy_enabled && (
                  <>
                    <p className="text-xs text-text-tertiary">{t('acme.proxyDefaultUrl')}</p>
                    <code className="block text-xs text-text-secondary font-mono bg-bg-secondary p-2 rounded break-all">
                      {publicProxyBase}/directory
                    </code>
                  </>
                )}
                {enabledProxyAccounts.length > 0 && (
                  <div className="space-y-1 pt-1">
                    <p className="text-xs font-medium text-text-secondary">{t('acme.proxyEnabledEndpoints')}</p>
                    {enabledProxyAccounts.map((acct) => (
                      <div key={acct.id} className="flex items-center justify-between gap-2">
                        <code className="text-xs text-text-secondary font-mono break-all">
                          {publicProxyBase}/{acct.proxy_slug}/directory
                        </code>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => copy(`${publicProxyBase}/${acct.proxy_slug}/directory`)}
                        >
                          <Copy size={12} />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-xs font-medium text-text-secondary mt-3">{t('acme.proxyUsage')}</p>
                <pre className="text-xs text-text-primary bg-bg-secondary p-2 rounded overflow-x-auto font-mono whitespace-pre-wrap break-all">
{`certbot certonly \\
  --server ${proxyDirectoryUrl} \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com`}
                </pre>
                <p className="text-xs text-text-tertiary whitespace-pre-line">{t('acme.proxyUsageNote')}</p>
              </div>

              {/* Proxy Registration */}
              {proxyAccountId && selectedProxyAccount?.is_registered ? (
                <div className="p-3 rounded-lg status-success-bg status-success-border border">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle size={18} className="status-success-text" weight="fill" />
                      <div>
                        <p className="text-sm font-medium text-text-primary">{t('acme.proxyRegistered')}</p>
                        <p className="text-xs text-text-secondary">{selectedProxyAccount.email}</p>
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={onUnregisterProxy}
                      className="status-danger-text hover:status-danger-bg"
                    >
                      <Trash size={14} />
                    </Button>
                  </div>
                </div>
              ) : proxyAccountId ? (
                <div className="space-y-3 p-3 bg-tertiary-op30 rounded-lg">
                  <Input
                    label={t('common.emailAddress')}
                    type="email"
                    value={proxyEmail || selectedProxyAccount?.email || ''}
                    onChange={(e) => onProxyEmailChange(e.target.value)}
                    placeholder={t('acme.emailPlaceholder')}
                    helperText={t('common.emailRequired')}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={onRegisterProxy}
                    disabled={!proxyEmail && !selectedProxyAccount?.email}
                  >
                    <Key size={14} />
                    {t('acme.registerAccount')}
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </div>
      </CompactSection>
    </div>
  )
}
