import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Icon, Pill } from '../../components/atelier'
import { parseDnsUpdatePort, effectiveDnsUpdatePort } from './dnsUpdatePort'

/**
 * Port of the DNS UPDATE (RFC 2136) listener, in the ACME proxy section.
 * `onSave(port)` returns the API response: data.restart_required asks for a restart.
 */
export default function DnsUpdatePortField({ clientSettings = {}, canWrite, onSave }) {
  const { t } = useTranslation()
  const stored = clientSettings.dns_update_port ?? 0
  const envPort = clientSettings.dns_update_port_env ?? null
  const overridden = envPort !== null && envPort !== undefined

  const [value, setValue] = useState(String(stored))
  const [error, setError] = useState('')
  const [restartRequired, setRestartRequired] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => { setValue(String(stored)) }, [stored])

  // The server value wins: an invalid environment value gives 0 (listener off).
  const hasEffective = clientSettings.dns_update_port_effective !== undefined
    && clientSettings.dns_update_port_effective !== null
  const effective = hasEffective
    ? effectiveDnsUpdatePort(clientSettings)
    : (overridden ? Number(envPort) : Number(stored))
  const listening = !!clientSettings.dns_update_listening

  const save = async () => {
    const port = parseDnsUpdatePort(value)
    if (port === null) {
      setError(t('acme.dnsUpdate.portInvalid'))
      return
    }
    setError('')
    setBusy(true)
    try {
      const res = await onSave(port)
      setRestartRequired(!!res?.data?.restart_required)
    } finally {
      setBusy(false)
    }
  }

  // The mockup's field: label and state, the port, its hint or error, then Enregistrer
  const state = listening
    ? <Pill label={t('acme.dnsUpdate.portListening')} tone="good" />
    : effective === 0 ? <Pill label={t('acme.dnsUpdate.portDisabled')} tone="muted" /> : <Pill label={t('acme.dnsUpdate.portNotListening')} tone="warn" />
  return (
    <div className="dns-update-port">
      <div className="field">
        <label htmlFor="acme-dns-update-port">{t('acme.dnsUpdate.portLabel')} {state}</label>
        <input id="acme-dns-update-port" aria-label={t('acme.dnsUpdate.portLabel')} type="number" min="0" max="65535" value={overridden ? String(envPort) : value}
          onChange={(e) => { setValue(e.target.value); setError('') }} readOnly={overridden} disabled={!canWrite || undefined}
          aria-invalid={error ? 'true' : undefined} aria-describedby="acme-dns-update-port-hint" />
        <small id="acme-dns-update-port-hint">{overridden ? t('acme.dnsUpdate.portEnvOverride', { port: envPort }) : t('acme.dnsUpdate.portHelper')}</small>
        {error && <p className="field-error"><Icon name="warning" /><span>{error}</span></p>}
      </div>
      {canWrite && !overridden && (
        <div className="copy-url"><Btn icon="check" write onClick={save} disabled={busy || undefined}>{t('common.save')}</Btn></div>
      )}
      {restartRequired && (
        <p className="notice warn" role="status"><Icon name="warning" /><span>{t('acme.dnsUpdate.portRestartRequired')}</span></p>
      )}
    </div>
  )
}
