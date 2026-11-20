/**
 * Database Backend Section - manage SQLite ↔ PostgreSQL backend switching/migration.
 * Embedded in SettingsPage 'database' tab.
 */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  CheckCircle, WarningCircle, Question, Copy, Lightning, ArrowsClockwise, FloppyDisk
} from '@phosphor-icons/react'
import { Button, Input, Badge, ConfirmModal } from '../../components'
import { HelpCard } from '../../components/HelpCard'
import { useClipboard } from '../../hooks/useClipboard'
import { formatBytes } from '../../lib/fileSize'
import { databaseService } from '../../services'
import { useNotification } from '../../contexts'
import { FormGroup, FormProps } from '../../components/sectioned'

export default function DatabaseBackendSection() {
  const { t, i18n } = useTranslation()
  const { showError, showSuccess, showWarning, showInfo } = useNotification()
  const { copy } = useClipboard()
  const testButton = useRef(null)
  const copyUri = async () => {
    if (await copy(status.uri_redacted)) showInfo(t('common.copiedToClipboard'))
  }

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
      // The button was disabled during the test: the focus goes back to it, as in the mockup
      requestAnimationFrame(() => testButton.current?.focus())
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
      // The proof is what makes the manual Docker restart a decision rather
      // than a leap: the operator sees the same verified figures the native
      // path acted on before it restarted itself.
      const verified = `${stats.tables_migrated} tables, ${stats.rows_migrated} rows verified`
      const msg = res.data?.docker
        ? `${res.data?.next_step || res.message} (${verified})`
        : `${res.message} (${verified})`
      showSuccess(msg)
      // What the migration knowingly left behind. Carried all the way to the
      // API and then shown to nobody is the same as never having measured it.
      const dropped = Object.entries(stats.dropped_columns || {})
        .flatMap(([table, columns]) =>
          Object.entries(columns)
            .filter(([, entry]) => entry?.values)
            .map(([column, entry]) => `${table}.${column} (${entry.values})`))
      if (dropped.length) {
        showWarning(t('settings.backend.droppedColumns', {
          columns: dropped.join(', '),
        }))
      }
      const drift = Object.keys(stats.source_drift || {}).length
      if (drift) {
        showWarning(t('settings.backend.sourceDrift', { tables: drift }))
      }
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
      <FormGroup title={t('settings.backend.currentTitle')}>
        <FormProps items={[
          [t('settings.backend.type'), isPg ? 'PostgreSQL' : 'SQLite'],
          [t('settings.backend.version'), status?.version || '—'],
          [t('settings.backend.tableCount'), status?.table_count ?? '—'],
          [t('settings.backend.size'), status ? formatBytes(status.size_bytes, i18n?.language) : '—'],
          [t('settings.backend.uri'), (
            <span className="sf-record-digest">
              <span>{status?.uri_redacted || '—'}</span>
              {status?.uri_redacted && (
                <button type="button" className="sf-inline-icon" onClick={copyUri}
                  title={t('common.copy')} aria-label={t('common.copy')}>
                  <Copy size={14} aria-hidden="true" />
                </button>
              )}
            </span>
          )],
          [t('settings.backend.health'), (
            <Badge variant={status?.healthy ? 'success' : 'danger'}>
              {status?.healthy ? t('settings.backend.healthy') : t('settings.backend.unhealthy')}
            </Badge>
          )],
        ]} />
        {status?.error && <p className="ui-error sf-under" role="alert">{status.error}</p>}
      </FormGroup>

      <FormGroup
        title={t('settings.backend.switchTitle')}
        description={inDocker ? t('settings.backend.dockerHint') : t('settings.backend.switchHint')}
      >
        <div className="sf-stack">
          <Input
            label={t('settings.backend.targetUrl')}
            type="text"
            placeholder="postgresql://user:password@host:5432/dbname"
            value={targetUrl}
            onChange={(e) => { setTargetUrl(e.target.value); setTestResult(null) }}
            autoComplete="off"
            spellCheck={false}
            helperText={`${t('settings.backend.urlExample')}${t('work.sep')}postgresql://ucm:secret@db.example.com:5432/ucm`}
          />

          {/* The test as the mockup's test zone: the button, then its result on the line */}
          <div className="sf-test">
            <Button ref={testButton} type="button" variant="secondary" onClick={handleTest} disabled={testing || !targetUrl.trim()}>
              <Lightning size={16} className={testing ? 'animate-pulse' : undefined} />
              {t('settings.backend.test')}
            </Button>
            {testResult ? (
              <p className={testResult.success ? 'sf-test-result is-good' : 'sf-test-result is-bad'} role="status">
                {testResult.success ? <CheckCircle aria-hidden="true" /> : <WarningCircle aria-hidden="true" />}
                <span>{testResult.message}</span>
              </p>
            ) : (
              <p className="sf-test-result">
                <Question aria-hidden="true" />
                <span>{t('settings.backend.testHint')}</span>
              </p>
            )}
          </div>

          <div className="sf-actions-row">
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

          <HelpCard variant="warning" title={t('settings.backend.warningTitle')}>
            {t('settings.backend.warningBody')}
          </HelpCard>
        </div>
      </FormGroup>

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
