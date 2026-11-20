import { useTranslation } from 'react-i18next'
import { Copy, Database, Download, Trash, MagnifyingGlass, CaretLeft, CaretRight, Broom, HardDrives, WarningCircle } from '@phosphor-icons/react'
import { Button, Input, Select, FileUpload, Badge } from '../../components'
import { HelpCard } from '../../components/HelpCard'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import AdminLockLabel from './AdminLockLabel'
import { useClipboard } from '../../hooks/useClipboard'
import { formatSize, formatBytes, formatPercent, serverUtcToIso } from '../../lib/fileSize'
import { formatDate } from '../../lib/utils'
import { restoreMaxBytes, restoreLegacyCeilingExceeded } from './restoreLimits'
import { fieldBounds } from './fieldChecks'
import { FormGroup } from '../../components/sectioned'

export default function BackupSection({
  settings, fieldErrors = {}, updateSetting, saving, hasPermission,
  backups, backupMeta = {}, backupSchedule = {}, backupQuery = {}, updateBackupQuery,
  selectedBackups = [], toggleSelectBackup, toggleSelectAllBackups,
  handleBulkDeleteBackups, handleRunRetention, backupBusy,
  setShowBackupModal, setShowRestoreModal, setRestoreFile, backupRunning = false,
  handleDownloadBackup, handleDeleteBackup, handleClearBackupPassword,
}) {
  const { t, i18n } = useTranslation()
  const { copy, isCopied } = useClipboard()
  const isAdmin = hasPermission('admin:system')
  // The whole schedule needs admin:settings: the API drops these keys otherwise.
  const canAdminSettings = Boolean(hasPermission('admin:settings'))
  const canWriteSettings = Boolean(hasPermission('write:settings'))
  const allSelected = backups.length > 0 && selectedBackups.length === backups.length
  const diskHigh = typeof backupMeta.disk_used_pct === 'number' && backupMeta.disk_used_pct >= 85
  // HA: the archives live in the shared database, listed the same from every node
  const sharedStore = backupMeta.storage === 'database'
  // The server's figures, read after each save: the saved ceiling, not the field being typed,
  // and only the archives retention counts
  const overCeiling = backupSchedule.over_ceiling === true
  const size = (bytes) => formatBytes(bytes, i18n?.language)
  const storedMiB = typeof backupSchedule.stored_bytes === 'number' ? size(backupSchedule.stored_bytes) : null

  const sortOptions = [
    { value: 'created_desc', label: t('settings.backupSortNewest') },
    { value: 'created_asc', label: t('settings.backupSortOldest') },
    { value: 'size_desc', label: t('settings.backupSortLargest') },
    { value: 'size_asc', label: t('settings.backupSortSmallest') },
    { value: 'name_asc', label: t('settings.backupSortNameAsc') },
    { value: 'name_desc', label: t('settings.backupSortNameDesc') },
  ]

  return (
    <>

      <FormGroup title={t('settings.automaticBackups')}>
        <div className="space-y-4">
          <ToggleSwitch
            checked={settings.auto_backup_enabled || false}
            onChange={(val) => updateSetting('auto_backup_enabled', val)}
            label={t('settings.enableAutoBackups')}
            description={t('settings.autoBackupsDesc')}
            disabled={!canAdminSettings}
          />

          {settings.auto_backup_enabled && (
            <>
              <Select
                label={t('settings.backupFrequency')}
                options={[
                  { value: 'daily', label: t('settings.daily') },
                  { value: 'weekly', label: t('settings.weekly') },
                  { value: 'monthly', label: t('settings.monthly') },
                ]}
                value={settings.backup_frequency || 'daily'}
                onChange={(val) => updateSetting('backup_frequency', val)}
                helperText={t('settings.backupCadenceNote')}
                disabled={!canAdminSettings}
              />
              <Select
                label={t('settings.backupKdf')}
                options={[
                  { value: 'auto', label: t('settings.backupKdfAuto') },
                  { value: 'pbkdf2', label: 'PBKDF2-HMAC-SHA256' },
                  { value: 'argon2id', label: 'Argon2id' },
                ]}
                value={settings.backup_kdf || 'auto'}
                onChange={(val) => updateSetting('backup_kdf', val)}
                helperText={t('settings.backupKdfHelper')}
                disabled={canAdminSettings === false}
              />
              <Input
                label={<AdminLockLabel text={t('settings.autoBackupPassword')} locked={!canAdminSettings} />}
                disabled={!canAdminSettings}
                type="password"
                noAutofill
                value={settings.backup_password || ''}
                onChange={(e) => updateSetting('backup_password', e.target.value)}
                placeholder={t('settings.min12Characters')}
                helperText={settings.backup_password_set
                  ? t('settings.backupPasswordKeepHelper')
                  : t('settings.autoBackupPasswordHelper')}
                showStrength
              />
              {/* Status only: the stored password is never sent to the browser */}
              <div className="flex items-center gap-2">
                <Badge variant={settings.backup_password_set ? 'success' : 'warning'}>
                  {settings.backup_password_set
                    ? t('settings.backupPasswordSet')
                    : t('settings.backupPasswordNotSet')}
                </Badge>
                {settings.backup_password_set && canAdminSettings && handleClearBackupPassword && (
                  <Button type="button" variant="danger-soft" size="sm" onClick={handleClearBackupPassword} disabled={saving}>
                    <Trash size={14} />
                    {t('settings.clearBackupPassword')}
                  </Button>
                )}
              </div>
            </>
          )}

          {canWriteSettings && (
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={() => setShowBackupModal(true)} data-write>
                <Database size={16} />
                {backupRunning ? t('settings.backupInProgress') : t('settings.createBackup')}
              </Button>
            </div>
          )}
        </div>
      </FormGroup>

      {/* Retention — applies to ALL backups, enforced daily (decoupled from auto-backup) */}
      <FormGroup title={t('settings.backupRetentionGroup')}>
        <div className="space-y-3">
          <Input
            className="sf-short"
            label={<AdminLockLabel text={t('settings.retentionPeriod')} locked={!canAdminSettings} />}
            disabled={!canAdminSettings}
            type="number"
            value={settings.backup_retention_days || 30}
            onChange={(e) => updateSetting('backup_retention_days', parseInt(e.target.value))}
            helperText={t('settings.retentionHelper')}
            {...fieldBounds('backup_retention_days')}
            error={fieldErrors['backup_retention_days']}
          />
          <Input
            className="sf-short"
            label={<AdminLockLabel text={t('settings.backupMaxTotalMb')} locked={!canAdminSettings} />}
            disabled={!canAdminSettings}
            type="number"
            value={settings.backup_max_total_mb ?? 0}
            onChange={(e) => updateSetting('backup_max_total_mb', parseInt(e.target.value, 10) || 0)}
            helperText={t('settings.backupMaxTotalMbHelper')}
            {...fieldBounds('backup_max_total_mb')}
            error={fieldErrors['backup_max_total_mb']}
          />
          {storedMiB && (
            <p className="sf-hint" data-testid="backup-space-used">
              {t('settings.backupSpaceUsed', { size: storedMiB, count: backupSchedule.stored_count ?? 0 })}
            </p>
          )}
          {backupSchedule.uncounted_count > 0 && (
            <p className="sf-hint" data-testid="backup-uncounted">
              {t('settings.backupUncountedFiles', { count: backupSchedule.uncounted_count })}
            </p>
          )}
          {overCeiling && (
            <div role="alert">
              <HelpCard variant="warning">{t('settings.backupOverCeiling', { ceiling: backupSchedule.max_total_mb ?? 0 })}</HelpCard>
            </div>
          )}
          {(canWriteSettings || isAdmin) && (
            <div className="flex gap-2">
              {isAdmin && (
                <Button type="button" variant="secondary" onClick={handleRunRetention} disabled={backupBusy} data-write>
                  <Broom size={16} />
                  {t('settings.backupCleanupNow')}
                </Button>
              )}
            </div>
          )}
        </div>
      </FormGroup>

      <FormGroup title={t('settings.availableBackups')}>
        {/* Summary: count, total size and free disk, on one muted line */}
        <p className="sf-records-summary">
          <span>{t('settings.backupCount', { count: backupMeta.total ?? backups.length })}</span>
          {typeof backupMeta.total_size_bytes === 'number' && (
            <span>{t('settings.backupTotalSize')}{t('work.sep')}{size(backupMeta.total_size_bytes)}</span>
          )}
          {typeof backupMeta.disk_free_bytes === 'number' && (
            <span className={diskHigh ? 'is-warn' : undefined}>
              {diskHigh ? <WarningCircle aria-hidden="true" /> : <HardDrives aria-hidden="true" />}
              {t('settings.diskFree')}{t('work.sep')}{size(backupMeta.disk_free_bytes)}
              {typeof backupMeta.disk_used_pct === 'number' ? ` (${formatPercent(backupMeta.disk_used_pct, i18n?.language)})` : ''}
            </span>
          )}
        </p>
        {sharedStore && (
          <HelpCard className="sf-records-lead">{t('settings.backupSharedStoreNote')}</HelpCard>
        )}

        {/* Toolbar */}
        {(backups.length > 0 || backupQuery.search) && (
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <div className="flex-1 min-w-[180px]">
              <Input
                icon={<MagnifyingGlass size={16} />}
                placeholder={t('settings.backupSearchPlaceholder')}
                value={backupQuery.search || ''}
                onChange={(e) => updateBackupQuery({ search: e.target.value })}
              />
            </div>
            <Select
              value={backupQuery.sort || 'created_desc'}
              onChange={(val) => updateBackupQuery({ sort: val })}
              options={sortOptions}
            />
            {isAdmin && selectedBackups.length > 0 && (
              <Button type="button" variant="danger" onClick={handleBulkDeleteBackups} disabled={backupBusy}>
                <Trash size={16} />
                {t('settings.backupDeleteSelected', { count: selectedBackups.length })}
              </Button>
            )}
          </div>
        )}

        {backups.length === 0 ? (
          <p className="sf-records-empty">
            {backupQuery.search ? t('settings.backupNoMatch') : t('settings.noBackups')}
            {!backupQuery.search && <span className="block">{t('settings.noBackupsHint')}</span>}
          </p>
        ) : (
          <>
            {isAdmin && (
              <label className="ui-check-line">
                <input type="checkbox" checked={allSelected} onChange={toggleSelectAllBackups} />
                {t('settings.backupSelectAll')}
              </label>
            )}
            {/* The mockup's record list: name, then size, date, node and digest, then the actions */}
            <ul className="sf-records">
              {backups.map((backup) => (
                <li key={backup.filename}>
                  {isAdmin && (
                    <input
                      type="checkbox"
                      aria-label={backup.filename}
                      checked={selectedBackups.includes(backup.filename)}
                      onChange={() => toggleSelectBackup(backup.filename)}
                    />
                  )}
                  <div className="sf-record-main">
                    <strong>{backup.filename}</strong>
                    <span className="sf-record-meta">
                      {typeof backup.size_bytes === 'number' ? size(backup.size_bytes) : backup.size}
                      {' · '}
                      {formatDate(serverUtcToIso(backup.created_at), { time: true })}
                      {backup.node && <>{' · '}{t('settings.backupNode')}{t('work.sep')}{backup.node}</>}
                    </span>
                    {backup.sha256 && (
                      <span className="sf-record-meta sf-record-digest">
                        {t('settings.backupSha256')}{t('work.sep')}<span>{backup.sha256.slice(0, 12)}</span>
                        <button
                          type="button"
                          className="sf-inline-icon"
                          aria-label={t('settings.backupCopySha256')}
                          title={t('settings.backupCopySha256')}
                          onClick={() => copy(backup.sha256, `sha256:${backup.filename}`)}
                        >
                          <Copy size={12} />
                        </button>
                        {isCopied(`sha256:${backup.filename}`) && <span>{t('common.copied')}</span>}
                      </span>
                    )}
                  </div>
                  <div className="sf-record-actions">
                    <Button type="button" variant="secondary" onClick={() => handleDownloadBackup(backup.filename)}
                      aria-label={t('common.download')} title={t('common.download')}>
                      <Download size={16} />
                    </Button>
                    {isAdmin && (
                      <Button type="button" variant="danger" onClick={() => handleDeleteBackup(backup.filename)}
                        aria-label={t('common.delete')} title={t('common.delete')}>
                        <Trash size={16} />
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>

            {/* Pagination */}
            {backupMeta.pages > 1 && (
              <div className="flex items-center justify-center gap-3 mt-4">
                <Button type="button" size="sm" variant="secondary"
                  disabled={backupMeta.page <= 1}
                  onClick={() => updateBackupQuery({ page: backupMeta.page - 1 })}>
                  <CaretLeft size={14} />
                </Button>
                <span className="text-xs text-text-secondary">
                  {t('settings.backupPageOf', { page: backupMeta.page, pages: backupMeta.pages })}
                </span>
                <Button type="button" size="sm" variant="secondary"
                  disabled={backupMeta.page >= backupMeta.pages}
                  onClick={() => updateBackupQuery({ page: backupMeta.page + 1 })}>
                  <CaretRight size={14} />
                </Button>
              </div>
            )}
          </>
        )}
      </FormGroup>

      <FormGroup title={t('settings.restoreFromBackup')} description={t('settings.restoreFromBackupDesc')}>
        <div>
          <FileUpload
            accept=".ucmbkp,.tar.gz"
            maxSize={restoreMaxBytes(backupMeta.restore_limits)}
            validate={async (file) => {
              const ceiling = await restoreLegacyCeilingExceeded(file, backupMeta.restore_limits)
              return ceiling ? t('settings.restoreTooLargeLegacy', { size: formatSize(ceiling) }) : null
            }}
            onFileSelect={(file) => { setRestoreFile(file); setShowRestoreModal(true) }}
            helperText={t('settings.selectBackupFile')}
          />
        </div>
      </FormGroup>
    </>
  )
}
