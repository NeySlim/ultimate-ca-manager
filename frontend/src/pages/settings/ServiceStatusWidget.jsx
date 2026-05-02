import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Power, ArrowClockwise } from '@phosphor-icons/react'
import {
  Button, LoadingSpinner, DetailSection, DetailGrid, DetailField,
  ServiceReconnectOverlay
} from '../../components'
import { systemService } from '../../services'
import { useNotification } from '../../contexts'
import { useServiceReconnect } from '../../hooks'
import { usePermission } from '../../hooks'

export default function ServiceStatusWidget() {
  const { t } = useTranslation()
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

  const formatUptime = (seconds) => {
    if (!seconds) return '-'
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    if (days > 0) return `${days}d ${hours}h ${mins}m`
    if (hours > 0) return `${hours}h ${mins}m`
    return `${mins}m`
  }

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
        <ServiceReconnectOverlay status={reconnectStatus} attempt={attempt} countdown={countdown} onCancel={cancel} />
      )}
      <DetailSection title={t('settings.serviceStatus')} icon={Power} iconClass="icon-bg-orange" className="mt-4">
      {loading ? (
        <LoadingSpinner size="sm" />
      ) : status ? (
        <div className="space-y-3">
          <DetailGrid columns={2}>
            <DetailField label={t('settings.version')} value={`v${status.version}`} />
            <DetailField label="PID" value={status.pid} />
            <DetailField label={t('settings.uptime')} value={formatUptime(status.uptime_seconds)} />
            <DetailField label={t('settings.memory')} value={`${status.memory_mb} MB`} />
            <DetailField label="Python" value={status.python_version} />
            <DetailField label={t('settings.environment')} value={status.is_docker ? 'Docker' : 'System'} />
          </DetailGrid>
          {canWrite('settings') && !status.is_docker && (
            <div className="pt-2">
              <Button type="button" variant="outline" onClick={handleRestart} disabled={restarting}>
                <ArrowClockwise size={16} className={restarting ? 'spin' : ''} />
                {restarting ? t('settings.restarting') : t('settings.restartService')}
              </Button>
            </div>
          )}
          {status.is_docker && (
            <p className="text-xs text-text-tertiary pt-2">{t('settings.dockerRestartNotice')}</p>
          )}
        </div>
      ) : (
        <p className="text-secondary">{t('settings.serviceStatusUnavailable')}</p>
      )}
    </DetailSection>
    </>
  )
}
