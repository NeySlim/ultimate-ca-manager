import { useTranslation } from 'react-i18next'
import { Icon, Pill } from '../../components/atelier'
import { effectiveDnsUpdatePort } from './dnsUpdatePort'

/**
 * Port of the DNS UPDATE (RFC 2136) listener, a field of the ACME client settings: its value lives
 * in the page's draft and is saved by the common save bar, with the other settings.
 */
export default function DnsUpdatePortField({ clientSettings = {}, canWrite, value, onChange, error, restartRequired }) {
  const { t } = useTranslation()
  const envPort = clientSettings.dns_update_port_env ?? null
  const overridden = envPort !== null && envPort !== undefined

  // The server value wins: an invalid environment value gives 0 (listener off).
  const hasEffective = clientSettings.dns_update_port_effective !== undefined
    && clientSettings.dns_update_port_effective !== null
  const effective = hasEffective
    ? effectiveDnsUpdatePort(clientSettings)
    : (overridden ? Number(envPort) : Number(clientSettings.dns_update_port ?? 0))
  const listening = !!clientSettings.dns_update_listening

  const state = listening
    ? <Pill label={t('acme.dnsUpdate.portListening')} tone="good" />
    : effective === 0 ? <Pill label={t('acme.dnsUpdate.portDisabled')} tone="muted" /> : <Pill label={t('acme.dnsUpdate.portNotListening')} tone="warn" />
  return (
    <div className="dns-update-port">
      <div className="field">
        <label htmlFor="acme-dns-update-port">{t('acme.dnsUpdate.portLabel')} {state}</label>
        <input id="acme-dns-update-port" data-setting="dns_update_port" aria-label={t('acme.dnsUpdate.portLabel')} type="number" min="0" max="65535"
          value={overridden ? String(envPort) : value ?? ''} onChange={(e) => onChange?.(e.target.value)} readOnly={overridden}
          disabled={!canWrite || undefined} aria-invalid={error ? 'true' : undefined} aria-describedby={overridden ? 'acme-dns-update-port-hint' : undefined} />
        {/* The card's description already says what the port does: the field adds only the environment's override */}
        {overridden && <small id="acme-dns-update-port-hint">{t('acme.dnsUpdate.portEnvOverride', { port: envPort })}</small>}
        {error && <p className="field-error"><Icon name="warning" /><span>{error}</span></p>}
      </div>
      {restartRequired && (
        <p className="notice warn" role="status"><Icon name="warning" /><span>{t('acme.dnsUpdate.portRestartRequired')}</span></p>
      )}
    </div>
  )
}
