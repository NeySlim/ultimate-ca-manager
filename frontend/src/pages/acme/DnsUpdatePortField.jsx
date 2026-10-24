import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'
import { Button, Badge, Input } from '../../components'
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

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium text-text-primary">{t('acme.dnsUpdate.portLabel')}</span>
        {listening
          ? <Badge variant="success" size="sm">{t('acme.dnsUpdate.portListening')}</Badge>
          : effective === 0
            ? <Badge variant="secondary" size="sm">{t('acme.dnsUpdate.portDisabled')}</Badge>
            : <Badge variant="warning" size="sm">{t('acme.dnsUpdate.portNotListening')}</Badge>}
      </div>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Input
            aria-label={t('acme.dnsUpdate.portLabel')}
            type="number"
            min="0"
            max="65535"
            value={overridden ? String(envPort) : value}
            onChange={(e) => { setValue(e.target.value); setError('') }}
            readOnly={overridden}
            disabled={!canWrite}
            error={error}
            helperText={overridden
              ? t('acme.dnsUpdate.portEnvOverride', { port: envPort })
              : t('acme.dnsUpdate.portHelper')}
          />
        </div>
        {canWrite && !overridden && (
          <Button type="button" size="sm" onClick={save} disabled={busy}>{t('common.save')}</Button>
        )}
      </div>
      {restartRequired && (
        <p className="text-xs status-warning-text flex items-center gap-1" role="status">
          <Warning size={14} /> {t('acme.dnsUpdate.portRestartRequired')}
        </p>
      )}
    </div>
  )
}
