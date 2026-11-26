/**
 * The ACME client settings and its proxy, drawn as the mockup's settingsView(): a draft saved in
 * one request (only what changed), the bounds the server applies checked before, and the proxy's
 * own actions (test, register, unregister, reset) in their section.
 */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, SettingsView, Facts } from '../../components/atelier'
import { acmeService } from '../../services'
import { useNotification } from '../../contexts'
import { publicBaseUrl } from '../../lib/utils'
import { ACME_CLIENT_LABELS, groupedOptions, listAlgorithms, isBrainpool } from '../../lib/keyAlgorithms'
import { useKeyPlatform } from '../../lib/policyAlgorithms'
import DnsUpdatePortField from './DnsUpdatePortField'
import { parseDnsUpdatePort } from './dnsUpdatePort'
import { Field, Notice, soleLegendsOff } from '../protocols/atelierParts'
import { copyRow } from '../../components/atelier/facts'

// Bounds of the integer settings, as the server checks them
const BOUNDS = { renewal_days: [1, 60, 30], dns_propagation_timeout: [0, 3600, 120], dns_propagation_delay: [0, 300, 10], tls_alpn_port: [1, 65535, 443] }
const BOOLS = { renewal_enabled: true, verify_ssl: true, debug_logging: false, allow_loopback_upstream: false, proxy_verify_ssl: true, proxy_prune_replaced_certificates: false }
const TEXTS = { environment: 'staging', email: '', dns01_resolver_mode: 'auto', dns01_nameservers: '', key_type: ACME_CLIENT_LABELS[0], account_key_type: 'ES256' }

const clientDraft = (s) => ({
  ...Object.fromEntries(Object.entries(TEXTS).map(([k, d]) => [k, s[k] || d])),
  ...Object.fromEntries(Object.entries(BOOLS).map(([k, d]) => [k, s[k] ?? d])),
  ...Object.fromEntries(Object.entries(BOUNDS).map(([k, [, , d]]) => [k, String(s[k] ?? d)])),
  proxy_acme_account_id: s.proxy_acme_account_id != null ? String(s.proxy_acme_account_id) : '',
  // Set by the environment, the port is read-only and never part of the draft
  ...(s.dns_update_port_env == null ? { dns_update_port: String(s.dns_update_port ?? 0) } : {}),
})

export default function LetsEncryptTab({ clientSettings, caAccounts = [], canWrite, onSaved, restartRequired = false, onRegisterProxy, onUnregisterProxy,
  onResetProxyAccount, onTestConnection, testingConnection, connectionResult }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const platform = useKeyPlatform()
  const [draft, setDraft] = useState(() => clientDraft(clientSettings))
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [announce, setAnnounce] = useState('')
  const [proxyEmail, setProxyEmail] = useState('')
  const stateRef = useRef(null)
  const saved = clientDraft(clientSettings)
  useEffect(() => { setDraft(clientDraft(clientSettings)) }, [clientSettings])

  const clientKeys = listAlgorithms({ labels: ACME_CLIENT_LABELS, ...platform })
  // A saved key this server no longer offers (FIPS mode, build without ML-DSA) fails every order
  const savedKeyUnavailable = !!clientSettings.key_type && !clientKeys.some((a) => a.label === clientSettings.key_type)
  const changed = Object.keys(saved).filter((k) => String(draft[k]) !== String(saved[k]))
  const off = !canWrite

  const proxyAccountId = clientSettings.proxy_acme_account_id ?? null
  const selected = caAccounts.find((a) => a.id === proxyAccountId)
  const publicProxyBase = publicBaseUrl(clientSettings.acme_proxy_public_base_url, '/acme/proxy')
  const proxyBase = selected?.proxy_enabled && selected?.proxy_slug ? `${publicProxyBase}/${selected.proxy_slug}` : publicProxyBase
  const proxyDirectoryUrl = `${proxyBase}/directory`
  const enabledProxyAccounts = caAccounts.filter((a) => a.proxy_enabled && a.proxy_slug)

  const validate = () => {
    const e = {}
    for (const [k, [min, max]] of Object.entries(BOUNDS)) {
      const n = Number(draft[k])
      if (!Number.isInteger(n) || n < min || n > max) e[k] = t('acme.boundsError', { min, max })
    }
    if ('dns_update_port' in draft && parseDnsUpdatePort(draft.dns_update_port) === null) e.dns_update_port = t('acme.dnsUpdate.portInvalid')
    return e
  }

  const save = async () => {
    const e = validate()
    setErrors(e)
    if (Object.keys(e).length) {
      setAnnounce(t('scep.fixBeforeSaving', { count: Object.keys(e).length }))
      requestAnimationFrame(() => document.querySelector('#settings-form [aria-invalid="true"]')?.focus())
      return
    }
    const patch = Object.fromEntries(changed.map((k) => [k, k in BOUNDS || k === 'dns_update_port' ? Number(draft[k]) : k === 'proxy_acme_account_id' ? (draft[k] ? Number(draft[k]) : null) : draft[k]]))
    setSaving(true)
    try {
      const res = await acmeService.updateClientSettings(patch)
      showSuccess(t('messages.success.update.settings'))
      setAnnounce(t('messages.success.update.settings'))
      // The page reloads its settings: a new port's restart notice is kept by the page, past the reload
      await onSaved?.('dns_update_port' in patch ? { restartRequired: !!res?.data?.restart_required } : {})
      stateRef.current?.focus()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const change = (k, v) => { setDraft((d) => ({ ...d, [k]: v })); if (errors[k]) setErrors((e) => { const n = { ...e }; delete n[k]; return n }) }

  const sections = [
    {
      id: 'client', label: t('acme.clientSettings'), icon: 'refresh', desc: t('acme.letsEncryptAboutDesc'),
      groups: [
        { legend: t('acme.clientSettings'), fields: [
          { key: 'environment', label: t('acme.defaultEnvironment'), hint: t('acme.environmentHelper'), disabled: off,
            options: [['staging', `${t('acme.staging')} (Test)`], ['production', `${t('acme.production')} (Live)`]] },
          { key: 'email', label: t('acme.contactEmail'), hint: t('acme.contactEmailHelper'), type: 'email', disabled: off },
          { key: 'renewal_enabled', label: t('acme.autoRenewal'), hint: t('acme.autoRenewalDesc'), checkbox: true, disabled: off },
          { key: 'renewal_days', label: t('acme.renewalDays'), hint: t('acme.renewalDaysHelper'), numeric: true, short: true, disabled: off || !draft.renewal_enabled },
          { key: 'verify_ssl', label: t('sso.verifySsl'), checkbox: true, disabled: off },
        ] },
        { legend: t('acme.dnsSettings'), fields: [
          { key: 'dns_propagation_timeout', label: t('acme.dnsPropagationTimeout'), hint: t('acme.dnsPropagationTimeoutHelper'), numeric: true, short: true, disabled: off },
          { key: 'dns_propagation_delay', label: t('acme.dnsPropagationDelay'), hint: t('acme.dnsPropagationDelayHelper'), numeric: true, short: true, disabled: off },
          { key: 'dns01_resolver_mode', label: t('acme.dnsResolverMode'), hint: t('acme.dnsResolverModeHelper'), disabled: off,
            options: [['auto', t('acme.dnsResolverModeAuto')], ['system', t('acme.dnsResolverModeSystem')], ['custom', t('acme.dnsResolverModeCustom')]] },
          ...(draft.dns01_resolver_mode !== 'system' ? [{ key: 'dns01_nameservers', label: t('acme.dnsResolvers'), hint: t('acme.dnsResolversHelper'), placeholder: '10.0.0.53, 127.0.0.1:5353', disabled: off }] : []),
        ] },
        { legend: t('acme.keysAndTransport'), fields: [
          { key: 'key_type', label: t('acme.keyType'), hint: t('acme.keyTypeHelper'), disabled: off,
            options: groupedOptions(clientKeys, t).map((o) => [o.value, o.label, o.group]) },
          { key: 'account_key_type', label: t('acme.accountKeyType'), hint: t('acme.accountKeyTypeHelper'), disabled: off,
            options: [['ES256', 'ECDSA P-256 (ES256)'], ['ES384', 'ECDSA P-384 (ES384)'], ['RS256', 'RSA 2048 (RS256)']] },
          { key: 'tls_alpn_port', label: t('acme.tlsAlpnPort'), hint: t('acme.tlsAlpnPortHelper'), numeric: true, short: true, disabled: off },
          { key: 'debug_logging', label: t('acme.debugLogging'), hint: t('acme.debugLoggingDesc'), checkbox: true, disabled: off },
          { key: 'allow_loopback_upstream', label: t('acme.allowLoopbackUpstream'), hint: t('acme.allowLoopbackUpstreamDesc'), checkbox: true, disabled: off },
        ] },
      ],
      children: <>
        {draft.verify_ssl === false && <Notice tone="warn">{t('sso.sslWarning')}</Notice>}
        {savedKeyUnavailable && <Notice tone="bad" role="alert">{t('acme.keyTypeUnavailable', { keyType: clientSettings.key_type })}</Notice>}
        {isBrainpool(draft.key_type) && <Notice tone="warn" role="note">{t('common.keyGroups.brainpoolWarning')}</Notice>}
      </>,
    },
    {
      id: 'proxy', label: t('acme.acmeProxy'), icon: 'server', desc: t('acme.proxyUpstreamCAAccountHelper'),
      groups: [{ legend: t('acme.acmeProxy'), fields: [
        { key: 'proxy_acme_account_id', label: t('acme.proxyUpstreamCAAccount'), disabled: off || caAccounts.length === 0,
          hint: caAccounts.length === 0 ? t('acme.proxyNoCaAccounts') : selected?.directory_url,
          options: [['', t('acme.proxySelectCaAccount')], ...caAccounts.map((a) => [String(a.id),
            `${a.label}${a.is_default ? ` (${t('common.default')})` : ''}${a.is_registered ? '' : `: ${t('acme.notRegistered')}`}`])] },
        { key: 'proxy_verify_ssl', label: t('sso.verifySsl'), checkbox: true, disabled: off },
        { key: 'proxy_prune_replaced_certificates', label: t('acme.proxyPruneReplacedCertificates'), hint: t('acme.proxyPruneReplacedCertificatesDesc'), checkbox: true, disabled: off },
      ] }],
      children: (
        <div className="acme-proxy">
          {draft.proxy_verify_ssl === false && <Notice tone="warn">{t('sso.sslWarning')}</Notice>}
          {selected && <p className="muted small">{t('acme.proxyManageCaAccountsHint')}</p>}
          {proxyAccountId && selected?.is_registered ? (
            <Notice icon="check">
              <strong>{t('acme.upstreamAccountRegistered')}</strong>{' '}
              <span className="mono">{clientSettings.proxy_account_url || selected.account_url || t('acme.accountRegistered')}</span>{' '}
              ({selected.label}, {selected.email})
            </Notice>
          ) : proxyAccountId ? <Notice>{t('acme.upstreamAccountNotRegistered')} {t('acme.willAutoRegister')}</Notice> : null}
          <div className="settings-test">
            <Btn icon="send" id="acme-proxy-test" disabled={testingConnection || !proxyAccountId || !canWrite || undefined} onClick={onTestConnection}>{t('acme.testConnection')}</Btn>
            {connectionResult && (
              <p className={`test-result ${connectionResult.connected ? 'good' : 'bad'}`} role="status">
                <span>{connectionResult.connected
                  ? `${connectionResult.ca_name || t('common.connected')}${connectionResult.eab_required ? ` (${t('acme.eabRequired')})` : ''}`
                  : connectionResult.error || t('acme.connectionFailed')}</span>
              </p>
            )}
          </div>
          {canWrite && proxyAccountId && selected?.is_registered && (
            <div className="copy-url">
              <Btn icon="refresh" write onClick={onResetProxyAccount}>{t('acme.resetAccount')}</Btn>{' '}
              <Btn icon="block" write onClick={onUnregisterProxy}>{t('acme.unregisterProxy')}</Btn>
            </div>
          )}
          {canWrite && proxyAccountId && !selected?.is_registered && (
            <div className="settings-grid">
              <Field label={t('common.emailAddress')} hint={t('common.emailRequired')} id="acme-proxy-email">
                {(p) => <input {...p} type="email" value={proxyEmail || selected?.email || ''} placeholder={t('acme.emailPlaceholder')} onChange={(e) => setProxyEmail(e.target.value)} />}
              </Field>
              <div className="copy-url"><Btn icon="key" write disabled={(!proxyEmail && !selected?.email) || undefined} onClick={() => onRegisterProxy(proxyEmail)}>{t('acme.registerAccount')}</Btn></div>
            </div>
          )}
          <Facts items={[
            copyRow(t('acme.proxyPathUrl'), proxyDirectoryUrl, 'url'),
            !selected?.proxy_enabled && copyRow(t('acme.proxyDefaultUrl'), `${publicProxyBase}/directory`, 'url'),
            ...enabledProxyAccounts.map((a) => copyRow(a.label, `${publicProxyBase}/${a.proxy_slug}/directory`, 'url', { key: a.id })),
          ]} />
          <h3 className="section-title acme-usage-title">{t('acme.proxyUsage')}</h3>
          <pre className="code-preview">{`certbot certonly \\
  --server ${proxyDirectoryUrl} \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com`}</pre>
          <p className="muted small acme-usage-note">{t('acme.proxyUsageNote')}</p>
        </div>
      ),
    },
    {
      id: 'dnsupdate', label: t('acme.dnsUpdate.portLabel'), icon: 'plug', desc: t('acme.dnsUpdate.portHelper'),
      groups: [],
      children: (
        <fieldset className="settings-group" aria-label={t('acme.dnsUpdate.portLabel')}>
          <DnsUpdatePortField clientSettings={clientSettings} canWrite={canWrite} value={draft.dns_update_port} error={errors.dns_update_port}
            restartRequired={restartRequired} onChange={(v) => change('dns_update_port', v)} />
        </fieldset>
      ),
    },
  ]

  return (
    <SettingsView sections={soleLegendsOff(sections)} values={draft} errors={errors} changed={changed}
      onChange={change}
      onSave={canWrite ? save : undefined} onReset={() => { setDraft(saved); setErrors({}) }} saving={saving} announce={announce} stateRef={stateRef}
      tocLabel={t('protocols.sectionsOf', { name: t('acme.views.client') })} />
  )
}
