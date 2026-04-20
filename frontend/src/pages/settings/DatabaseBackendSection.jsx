/**
 * Database Backend Section - manage SQLite ↔ PostgreSQL backend switching/migration.
 * Embedded in SettingsPage 'database' tab.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Database, CheckCircle, XCircle, Warning, Lightning, ArrowsClockwise, FloppyDisk
} from '@phosphor-icons/react'
import {
  Button, Input, Badge, DetailSection, DetailGrid, DetailField, ConfirmModal
} from '../../components'
import { databaseService } from '../../services'
import { useNotification } from '../../contexts'

export default function DatabaseBackendSection() {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()

  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  const [targetUrl, setTargetUrl] = useState('')
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)

  const [confirmAction, setConfirmAction] = useState(null) // 'switch' | 'migrate' | null
  const [working, setWorking] = useState(false)

  const loadStatus = async () => {
    try {
      const res = await databaseService.getStatus()
      setStatus(res.data)
    } catch (e) {
      showError(e.message || t('settings.backend.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadStatus() }, [])

  const handleTest = async () => {
    if (!targetUrl.trim()) {
      showError(t('settings.backend.urlRequired'))
      return
    }
    setTesting(true)
    setTestResult(null)
    try {
      const res = await databaseService.testConnection(targetUrl.trim())
      setTestResult(res.data)
    } catch (e) {
      setTestResult({ success: false, message: e.message })
    } finally {
      setTesting(false)
    }
  }

  const handleSwitch = async () => {
    setWorking(true)
    try {
      const res = await databaseService.switchBackend(targetUrl.trim())
      showSuccess(res.message || t('settings.backend.switchInitiated'))
      setConfirmAction(null)
    } catch (e) {
      showError(e.message || t('settings.backend.switchFailed'))
    } finally {
      setWorking(false)
    }
  }

  const handleMigrate = async () => {
    setWorking(true)
    try {
      const res = await databaseService.migrateData(targetUrl.trim())
      const stats = res.data?.stats || {}
      const msg = res.data?.docker
        ? res.data?.next_step || res.message
        : `${res.message} (${stats.tables_migrated} tables, ${stats.rows_migrated} rows)`
      showSuccess(msg)
      setConfirmAction(null)
    } catch (e) {
      showError(e.message || t('settings.backend.migrateFailed'))
    } finally {
      setWorking(false)
    }
  }

  if (loading) return null

  const isPg = status?.backend === 'postgresql'
  const inDocker = status?.is_docker

  return (
    <>
      <DetailSection
        title={t('settings.backend.currentTitle')}
        icon={Database}
        iconClass="icon-bg-blue"
      >
        <DetailGrid>
          <DetailField
            label={t('settings.backend.type')}
            value={
              <Badge variant={isPg ? 'success' : 'secondary'}>
                {isPg ? 'PostgreSQL' : 'SQLite'}
              </Badge>
            }
          />
          <DetailField label={t('settings.backend.version')} value={status?.version || '-'} />
          <DetailField label={t('settings.backend.tableCount')} value={status?.table_count} />
          <DetailField label={t('settings.backend.size')} value={status?.size_human || '-'} />
          <DetailField
            label={t('settings.backend.uri')}
            value={status?.uri_redacted || '-'}
            mono fullWidth copyable
          />
          <DetailField
            label={t('settings.backend.health')}
            value={
              <Badge variant={status?.healthy ? 'success' : 'danger'}>
                {status?.healthy ? t('settings.backend.healthy') : t('settings.backend.unhealthy')}
              </Badge>
            }
          />
        </DetailGrid>
        {status?.error && (
          <p className="mt-3 text-xs text-status-danger">{status.error}</p>
        )}
      </DetailSection>

      <DetailSection
        title={t('settings.backend.switchTitle')}
        icon={ArrowsClockwise}
        iconClass="icon-bg-violet"
        className="mt-4"
      >
        <div className="space-y-4">
          <p className="text-xs text-text-secondary">
            {inDocker
              ? t('settings.backend.dockerHint')
              : t('settings.backend.switchHint')}
          </p>

          <div className="space-y-2">
            <label className="text-xs font-medium text-text-secondary">
              {t('settings.backend.targetUrl')}
            </label>
            <div className="flex gap-2">
              <Input
                type="text"
                placeholder="postgresql://user:password@host:5432/dbname"
                value={targetUrl}
                onChange={(e) => { setTargetUrl(e.target.value); setTestResult(null) }}
                className="flex-1"
                autoComplete="off"
              />
              <Button type="button" variant="secondary" onClick={handleTest} disabled={testing || !targetUrl.trim()}>
                {testing ? <Lightning size={16} className="animate-pulse" /> : <Lightning size={16} />}
                {t('settings.backend.test')}
              </Button>
            </div>
            <p className="text-[10px] text-text-tertiary">
              {t('settings.backend.urlExample')}: <span className="font-mono">postgresql://ucm:secret@db.example.com:5432/ucm</span>
            </p>
          </div>

          {testResult && (
            <div className={`flex items-start gap-2 p-3 rounded-md text-xs ${
              testResult.success
                ? 'status-success-bg status-success-border border'
                : 'status-danger-bg status-danger-border border'
            }`}>
              {testResult.success
                ? <CheckCircle size={16} className="text-status-success shrink-0 mt-0.5" />
                : <XCircle size={16} className="text-status-danger shrink-0 mt-0.5" />}
              <span>{testResult.message}</span>
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setConfirmAction('migrate')}
              disabled={!testResult?.success || working}
            >
              <FloppyDisk size={16} />
              {t('settings.backend.migrateData')}
            </Button>
            {!inDocker && (
              <Button
                type="button"
                variant="secondary"
                onClick={() => setConfirmAction('switch')}
                disabled={!testResult?.success || working}
              >
                <ArrowsClockwise size={16} />
                {t('settings.backend.switchOnly')}
              </Button>
            )}
          </div>

          <div className="p-3 status-warning-bg status-warning-border border rounded-md">
            <div className="flex items-start gap-2 text-xs">
              <Warning size={16} className="text-status-warning shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="font-semibold text-status-warning">{t('settings.backend.warningTitle')}</p>
                <p className="text-text-secondary">{t('settings.backend.warningBody')}</p>
              </div>
            </div>
          </div>
        </div>
      </DetailSection>

      {confirmAction && (
        <ConfirmModal
          open={true}
          onClose={() => setConfirmAction(null)}
          onConfirm={confirmAction === 'migrate' ? handleMigrate : handleSwitch}
          title={confirmAction === 'migrate'
            ? t('settings.backend.confirmMigrateTitle')
            : t('settings.backend.confirmSwitchTitle')}
          message={confirmAction === 'migrate'
            ? t('settings.backend.confirmMigrateMessage')
            : t('settings.backend.confirmSwitchMessage')}
          confirmLabel={confirmAction === 'migrate'
            ? t('settings.backend.confirmMigrateButton')
            : t('settings.backend.confirmSwitchButton')}
          variant="danger"
          loading={working}
        />
      )}
    </>
  )
}
