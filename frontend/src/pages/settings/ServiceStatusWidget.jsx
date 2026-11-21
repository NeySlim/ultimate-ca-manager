import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { ServiceReconnectOverlay } from '../../components'
import { Btn, Props, SkeletonPanel } from '../../components/atelier'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { formatBytes } from '../../lib/fileSize'
import { compactAgo } from '../../lib/relativeTime'
import { systemService } from '../../services'
import { useNotification } from '../../contexts'
import { useServiceReconnect } from '../../hooks'
import { usePermission } from '../../hooks'

export default function ServiceStatusWidget() {
  const { t, i18n } = useTranslation()
  const { showError, showConfirm } = useNotification()
  const { canWrite } = usePermission()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [restarting, setRestarting] = useState(false)
  const { reconnecting, status: reconnectStatus, attempt, countdown, waitForRestart, cancel } = useServiceReconnect()

  const fetchStatus = async () => {
    try {
      const response = await systemService.getServiceStatus()
      setStatus(response.data)
    } catch {
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleRestart = async () => {
    const confirmed = await showConfirm(t('settings.restartConfirmMessage'), {
      title: t('settings.restartService'),
      confirmText: t('settings.restartNow'),
      variant: 'danger'
    })
    if (!confirmed) return

    setRestarting(true)
    try {
      await systemService.restartService()
      waitForRestart()
    } catch {
      showError(t('settings.restartFailed'))
      setRestarting(false)
    }
  }

  return (
    <>
      {reconnecting && (
        <div className="atl-out">
          <ServiceReconnectOverlay status={reconnectStatus} attempt={attempt} countdown={countdown} onCancel={cancel} />
        </div>
      )}
      <SettingsGroup legend={t('settings.serviceStatus')} grid={false}>
        {loading ? (
          <SkeletonPanel label={t('common.loading')} />
        ) : status ? (
          <>
            <Props items={[
              [t('settings.version'), `v${status.version}`],
              ['PID', status.pid],
              [t('settings.about.started'), status.uptime_seconds ? compactAgo(new Date(Date.now() - status.uptime_seconds * 1000), t) : '—'],
              [t('settings.memory'), status.memory_mb ? formatBytes(status.memory_mb * 1024 * 1024, i18n?.language) : '—'],
              ['Python', status.python_version],
              [t('settings.environment'), status.is_docker ? 'Docker' : t('settings.about.envNative')],
            ]} />
            {canWrite('settings') && !status.is_docker && (
              <div className="settings-actions">
                <Btn icon="refresh" onClick={handleRestart} disabled={restarting}>
                  {restarting ? t('settings.restarting') : t('settings.restartService')}
                </Btn>
              </div>
            )}
            {status.is_docker && <p className="group-hint">{t('settings.dockerRestartNotice')}</p>}
          </>
        ) : (
          <p className="group-hint">{t('settings.serviceStatusUnavailable')}</p>
        )}
      </SettingsGroup>
    </>
  )
}
