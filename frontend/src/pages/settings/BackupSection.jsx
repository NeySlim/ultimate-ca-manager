/**
 * Sauvegarde, on the mockup's settings section: the « Planification » group (frequency with its
 * « off » entry, retention), then what the product holds beyond it: the key derivation and the
 * password of the scheduled archives, the size ceiling, the archives in the mockup's module table,
 * and the restore from a file.
 */
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, Pill, Notice, DataTable, TableFooter, Toolbar, SearchField, BatchBar } from '../../components/atelier'
import { Breakable } from '../../components/atelier/Breakable'
import { Field, NumberInput, Select } from '../../components/atelier/Form'
import { SettingsGroup, FieldError } from '../../components/atelier/SettingsView'
import { cardFacts, labelledFact } from '../../components/atelier/cardFacts'
import { PasswordMeter } from '../../components/auth/PasswordMeter'
import AdminLockLabel from './AdminLockLabel'
import { useClipboard } from '../../hooks/useClipboard'
import { formatSize, formatBytes, formatPercent, serverUtcToIso } from '../../lib/fileSize'
import { formatDate } from '../../lib/utils'
import { restoreMaxBytes, restoreLegacyCeilingExceeded } from './restoreLimits'
import { shownNumber, typedNumber } from './numberFields'

// The server's sort orders, by the column header that names them
const SORTS = { created: ['created_desc', 'created_asc'], size: ['size_desc', 'size_asc'], name: ['name_desc', 'name_asc'] }
const sortOf = (value = 'created_desc') => {
  const [key, dir] = value.split('_')
  return { key, asc: dir === 'asc' }
}

export default function BackupSection({
  settings, fieldErrors = {}, updateSetting, saving, hasPermission,
  backups, backupMeta = {}, backupSchedule = {}, backupQuery = {}, updateBackupQuery,
  selectedBackups = [], toggleSelectBackup, toggleSelectAllBackups,
  handleBulkDeleteBackups, handleRunRetention, backupBusy,
  setShowBackupModal, setShowRestoreModal, setRestoreFile, backupRunning = false,
  handleDownloadBackup, handleDeleteBackup, handleClearBackupPassword, clearBackupSelection,
}) {
  const { t, i18n } = useTranslation()
  const { copy, isCopied } = useClipboard()
  const [fileError, setFileError] = useState(null)
  const fileInput = useRef(null)
  const isAdmin = hasPermission('admin:system')
  // The whole schedule needs admin:settings: the API drops these keys otherwise.
  const canAdminSettings = Boolean(hasPermission('admin:settings'))
  const canWriteSettings = Boolean(hasPermission('write:settings'))
  const locked = !canAdminSettings
  const lockedLabel = (key) => <AdminLockLabel text={t(key)} locked={locked} mockup />
  const enabled = Boolean(settings.auto_backup_enabled)
  const diskHigh = typeof backupMeta.disk_used_pct === 'number' && backupMeta.disk_used_pct >= 85
  // HA: the archives live in the shared database, listed the same from every node
  const sharedStore = backupMeta.storage === 'database'
  // The server's figures, read after each save: the saved ceiling, not the field being typed
  const overCeiling = backupSchedule.over_ceiling === true
  const size = (bytes) => formatBytes(bytes, i18n?.language)
  const storedMiB = typeof backupSchedule.stored_bytes === 'number' ? size(backupSchedule.stored_bytes) : null
  const selected = new Set(selectedBackups)

  // The mockup's frequency carries the off switch: « Désactivée » stops the scheduled archives
  const pickFrequency = (value) => {
    if (value === 'off') { updateSetting('auto_backup_enabled', false); return }
    if (!enabled) updateSetting('auto_backup_enabled', true)
    updateSetting('backup_frequency', value)
  }

  const pickFile = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const max = restoreMaxBytes(backupMeta.restore_limits)
    if (max && file.size > max) { setFileError(t('settings.restoreTooLarge', { size: formatSize(max) })); return }
    const ceiling = await restoreLegacyCeilingExceeded(file, backupMeta.restore_limits)
    if (ceiling) { setFileError(t('settings.restoreTooLargeLegacy', { size: formatSize(ceiling) })); return }
    setFileError(null)
    setRestoreFile(file)
    setShowRestoreModal(true)
  }

  const created = (b) => formatDate(serverUtcToIso(b.created_at), { time: true })
  const shownSize = (b) => (typeof b.size_bytes === 'number' ? size(b.size_bytes) : b.size)
  const digest = (b) => b.sha256 && (
    <span className="rl-meta backup-digest">
      <span className="mono">{b.sha256.slice(0, 12)}</span>
      <IconBtn icon="copy" quiet label={t('settings.backupCopySha256')} onClick={() => copy(b.sha256, `sha256:${b.filename}`)} />
      {isCopied(`sha256:${b.filename}`) && <span role="status">{t('common.copied')}</span>}
    </span>
  )
  // The row's own buttons, named with the archive: the mockup's table hides its first action under 1250 px
  const actions = (b) => (
    <span className="row-actions">
      <IconBtn icon="download" label={`${t('common.download')} ${b.filename}`} title={t('common.download')} onClick={() => handleDownloadBackup(b.filename)} />
      {isAdmin && <IconBtn icon="close" label={`${t('common.delete')} ${b.filename}`} title={t('common.delete')} write onClick={() => handleDeleteBackup(b.filename)} />}
    </span>
  )
  // The archive's name takes the room left (nothing opens it: its row names it), its digest beside it
  const columns = [
    { id: 'name', label: t('common.name'), sort: 'name', kind: 'entity', priority: 1, cell: (b) => b.filename, extra: digest },
    { id: 'size', label: t('settings.backupSize'), sort: 'size', kind: 'number', priority: 3, tone: 'muted', cell: shownSize },
    { id: 'created', label: t('common.created'), labelFull: t('table.fullCreated'), sort: 'created', kind: 'fit', priority: 2, labelled: true, tone: 'muted', cell: created },
    ...(sharedStore || backups.some((b) => b.node) ? [{ id: 'node', label: t('settings.backupNode'), kind: 'fit', priority: 4, labelled: true, tone: 'muted', cell: (b) => b.node || '—' }] : []),
    { id: 'actions', label: <span className="sr-only">{t('common.actions')}</span>, kind: 'fit', priority: 1, cell: actions },
  ]
  // The headers are the one sort control (T3: a new column ascending, the sorted one reversed); the server sorts
  const sort = sortOf(backupQuery.sort)
  const onSort = (key) => {
    const asc = sort.key === key ? !sort.asc : true
    updateBackupQuery({ sort: SORTS[key][asc ? 1 : 0] })
  }

  return (
    <>
      <SettingsGroup legend={t('settings.backupScheduleGroup')}>
        <Select id="set-backup_frequency" label={t('settings.backupFrequency')} disabled={locked}
          value={enabled ? (settings.backup_frequency || 'daily') : 'off'} onChange={pickFrequency} hint={t('settings.backupCadenceNote')}
          options={[
            { value: 'daily', label: t('settings.daily') },
            { value: 'weekly', label: t('settings.weekly') },
            { value: 'monthly', label: t('settings.monthly') },
            { value: 'off', label: t('settings.backupFrequencyOff') },
          ]} />
        <NumberInput id="set-backup_retention_days" label={lockedLabel('settings.retentionPeriod')} disabled={locked}
          value={shownNumber(settings.backup_retention_days ?? 30)} onChange={(e) => updateSetting('backup_retention_days', typedNumber(e))}
          hint={t('settings.retentionHelper')} error={fieldErrors.backup_retention_days} />
        <NumberInput id="set-backup_max_total_mb" label={lockedLabel('settings.backupMaxTotalMb')} disabled={locked}
          value={shownNumber(settings.backup_max_total_mb ?? 0)} onChange={(e) => updateSetting('backup_max_total_mb', typedNumber(e))}
          hint={t('settings.backupMaxTotalMbHelper')} error={fieldErrors.backup_max_total_mb} />
        {enabled && (
          <>
            <Select id="set-backup_kdf" label={t('settings.backupKdf')} disabled={locked} value={settings.backup_kdf || 'auto'}
              onChange={(val) => updateSetting('backup_kdf', val)} hint={t('settings.backupKdfHelper')}
              options={[
                { value: 'auto', label: t('settings.backupKdfAuto') },
                { value: 'pbkdf2', label: 'PBKDF2-HMAC-SHA256' },
                { value: 'argon2id', label: 'Argon2id' },
              ]} />
            <Field id="set-backup_password" label={lockedLabel('settings.autoBackupPassword')}
              hint={settings.backup_password_set ? t('settings.backupPasswordKeepHelper') : t('settings.autoBackupPasswordHelper')}>
              <input id="set-backup_password" type="password" autoComplete="new-password" spellCheck={false} disabled={locked}
                value={settings.backup_password || ''} placeholder={t('settings.min12Characters')} aria-describedby="hint-set-backup_password"
                onChange={(e) => updateSetting('backup_password', e.target.value)} />
              <PasswordMeter password={settings.backup_password || ''} />
            </Field>
            {/* Status only: the stored password is never sent to the browser */}
            <div className="settings-actions">
              <Pill tone={settings.backup_password_set ? 'good' : 'warn'}
                label={settings.backup_password_set ? t('settings.backupPasswordSet') : t('settings.backupPasswordNotSet')} />
              {settings.backup_password_set && canAdminSettings && handleClearBackupPassword && (
                <Btn tone="danger" icon="close" onClick={handleClearBackupPassword} disabled={saving}>{t('settings.clearBackupPassword')}</Btn>
              )}
            </div>
          </>
        )}
        {storedMiB && (
          <p className="group-hint" data-testid="backup-space-used">
            {t('settings.backupSpaceUsed', { size: storedMiB, count: backupSchedule.stored_count ?? 0 })}
          </p>
        )}
        {backupSchedule.uncounted_count > 0 && (
          <p className="group-hint" data-testid="backup-uncounted">
            {t('settings.backupUncountedFiles', { count: backupSchedule.uncounted_count })}
          </p>
        )}
        {overCeiling && (
          <Notice tone="bad">{t('settings.backupOverCeiling', { ceiling: backupSchedule.max_total_mb ?? 0 })}</Notice>
        )}
        {(canWriteSettings || isAdmin) && (
          <div className="settings-actions">
            {canWriteSettings && (
              <Btn icon="archive" write onClick={() => setShowBackupModal(true)}>
                {backupRunning ? t('settings.backupInProgress') : t('settings.createBackup')}
              </Btn>
            )}
            {isAdmin && (
              <Btn icon="refresh" write onClick={handleRunRetention} disabled={backupBusy}>{t('settings.backupCleanupNow')}</Btn>
            )}
          </div>
        )}
      </SettingsGroup>

      <SettingsGroup legend={t('settings.availableBackups')} grid={false}>
        {/* Summary: count, total size and free disk, on one muted line */}
        <p className="group-hint backup-summary">
          <span>{t('settings.backupCount', { count: backupMeta.total ?? backups.length })}</span>
          {typeof backupMeta.total_size_bytes === 'number' && (
            <span>{t('settings.backupTotalSize')}{t('work.sep')}{size(backupMeta.total_size_bytes)}</span>
          )}
          {typeof backupMeta.disk_free_bytes === 'number' && (
            <span>
              {diskHigh && <Pill tone="warn" label={t('settings.diskHigh')} />}
              {t('settings.diskFree')}{t('work.sep')}{size(backupMeta.disk_free_bytes)}
              {typeof backupMeta.disk_used_pct === 'number' ? ` (${formatPercent(backupMeta.disk_used_pct, i18n?.language)})` : ''}
            </span>
          )}
        </p>
        {sharedStore && <Notice>{t('settings.backupSharedStoreNote')}</Notice>}
        {(backups.length > 0 || backupQuery.search) && (
          <Toolbar>
            <SearchField id="backup-search" label={t('settings.backupSearchPlaceholder')} placeholder={t('settings.backupSearchPlaceholder')}
              value={backupQuery.search || ''} onChange={(search) => updateBackupQuery({ search })} />
          </Toolbar>
        )}
        {isAdmin && selectedBackups.length > 0 && (
          <BatchBar count={t('table.selectedCount', { count: selectedBackups.length })} onClear={clearBackupSelection}>
            <Btn tone="danger" icon="close" onClick={handleBulkDeleteBackups} disabled={backupBusy}>
              {t('settings.backupDeleteSelected', { count: selectedBackups.length })}
            </Btn>
          </BatchBar>
        )}
        <DataTable kind="module" scrollId="backup-scroll" recordsId="backup-records" label={t('settings.availableBackups')}
          columns={columns} rows={backups} rowKey={(b) => b.filename} rowLabel={(b) => b.filename}
          sort={{ key: sort.key, asc: sort.asc }} onSort={onSort}
          selection={isAdmin ? {
            selected,
            onToggle: (name) => toggleSelectBackup(name),
            onTogglePage: () => toggleSelectAllBackups(),
          } : undefined}
          card={(b) => ({
            // On a phone the name wraps after its separators, never inside its extension
            title: <Breakable text={b.filename} />,
            description: digest(b),
            // Each fact after its column's label, as every list's records
            meta: [...cardFacts(columns, b), b.node && labelledFact(t('settings.backupNode'), b.node)],
            end: actions(b),
          })}
          empty={(
            <div className="empty">
              <p>{backupQuery.search ? t('settings.backupNoMatch') : t('settings.noBackups')}</p>
              {!backupQuery.search && <p className="muted small">{t('settings.noBackupsHint')}</p>}
            </div>
          )}
          footer={backupMeta.pages > 1 && (
            <TableFooter range={t('settings.backupPageOf', { page: backupMeta.page, pages: backupMeta.pages })}
              pagination={{ page: backupMeta.page, pages: backupMeta.pages, onPage: (page) => updateBackupQuery({ page }) }} />
          )} />
      </SettingsGroup>

      {/* The archive is picked by a button of the mockup; the file input it opens stays out of sight */}
      <SettingsGroup legend={t('settings.restoreFromBackup')} hint={t('settings.restoreFromBackupDesc')} grid={false}>
        <div className="settings-actions">
          <input ref={fileInput} id="set-restore_file" type="file" accept=".ucmbkp,.tar.gz" hidden onChange={pickFile} />
          <Btn icon="upload" write onClick={() => fileInput.current?.click()} aria-describedby={fileError ? 'err-set-restore_file' : undefined}>
            {t('settings.restoreChooseFile')}
          </Btn>
        </div>
        {fileError && <FieldError id="err-set-restore_file" message={fileError} />}
      </SettingsGroup>
    </>
  )
}
