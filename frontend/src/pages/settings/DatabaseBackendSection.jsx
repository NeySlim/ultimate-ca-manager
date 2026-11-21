/**
 * Database Backend Section - manage SQLite ↔ PostgreSQL backend switching/migration.
 * Embedded in SettingsPage 'database' tab.
 */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, Pill, Notice, Props } from '../../components/atelier'
import { Input, ConfirmModal } from '../../components/atelier/Form'
import { SettingsGroup, SettingsTest } from '../../components/atelier/SettingsView'
import { useRefocusAfter } from '../../hooks/useRefocus'
import { useClipboard } from '../../hooks/useClipboard'
import { formatBytes } from '../../lib/fileSize'
import { databaseService } from '../../services'
import { useNotification } from '../../contexts'

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
  // Disabled while it runs: the focus goes back to the test button, as in the mockup
  useRefocusAfter(testing, testButton)

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
      <SettingsGroup legend={t('settings.backend.currentTitle')} grid={false}>
        <Props items={[
          [t('settings.backend.type'), isPg ? 'PostgreSQL' : 'SQLite'],
          [t('settings.backend.version'), status?.version || '—'],
          [t('settings.backend.tableCount'), status?.table_count ?? '—'],
          [t('settings.backend.size'), status ? formatBytes(status.size_bytes, i18n?.language) : '—'],
          [t('settings.backend.uri'), (
            <span className="copy-value">
              <span className="mono">{status?.uri_redacted || '—'}</span>
              {status?.uri_redacted && <IconBtn icon="copy" quiet label={t('common.copy')} onClick={copyUri} />}
            </span>
          )],
          [t('settings.backend.health'), (
            <Pill tone={status?.healthy ? 'good' : 'bad'} label={status?.healthy ? t('settings.backend.healthy') : t('settings.backend.unhealthy')} />
          )],
        ]} />
        {status?.error && <Notice tone="bad">{status.error}</Notice>}
      </SettingsGroup>

      <SettingsGroup legend={t('settings.backend.switchTitle')} hint={inDocker ? t('settings.backend.dockerHint') : t('settings.backend.switchHint')}>
        <Input id="set-db_target_url" full mono label={t('settings.backend.targetUrl')}
          placeholder="postgresql://user:password@host:5432/dbname" value={targetUrl}
          onChange={(e) => { setTargetUrl(e.target.value); setTestResult(null) }}
          hint={`${t('settings.backend.urlExample')}${t('work.sep')}postgresql://ucm:secret@db.example.com:5432/ucm`} />
        <Notice tone="warn"><strong>{t('settings.backend.warningTitle')}</strong>{' '}{t('settings.backend.warningBody')}</Notice>
        <div className="settings-actions">
          <Btn icon="upload" write onClick={() => setConfirmAction('migrate')} disabled={!testResult?.success || working}>
            {t('settings.backend.migrateData')}
          </Btn>
          {!inDocker && (
            <Btn icon="refresh" write onClick={() => setConfirmAction('switch')} disabled={!testResult?.success || working}>
              {t('settings.backend.switchOnly')}
            </Btn>
          )}
        </div>
      </SettingsGroup>
      {/* The test as the mockup's test zone: the button, then its result on the line */}
      <SettingsTest id="database" label={t('settings.backend.test')} icon="plug" onTest={handleTest} busy={testing || !targetUrl.trim()}
        buttonRef={testButton} write={false} result={testResult ? { ok: !!testResult.success, text: testResult.message } : null}
        hint={t('settings.backend.testHint')} />

      <ConfirmModal
        open={!!confirmAction}
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
    </>
  )
}
