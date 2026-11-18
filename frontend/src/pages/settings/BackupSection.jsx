import { useTranslation } from 'react-i18next'
import { Copy, Database, Download, Trash, UploadSimple, FloppyDisk, MagnifyingGlass, CaretLeft, CaretRight, Broom, HardDrives, WarningCircle } from '@phosphor-icons/react'
import { Button, Input, Select, FileUpload, Badge, DetailHeader, DetailSection, DetailContent } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import AdminLockLabel from './AdminLockLabel'
import { useClipboard } from '../../hooks/useClipboard'
import { formatSize } from '../../lib/fileSize'
import { restoreMaxBytes, restoreLegacyCeilingExceeded } from './restoreLimits'

export default function BackupSection({
  settings, updateSetting, handleSave, saving, hasPermission,
  backups, backupMeta = {}, backupSchedule = {}, backupQuery = {}, updateBackupQuery,
  selectedBackups = [], toggleSelectBackup, toggleSelectAllBackups,
  handleBulkDeleteBackups, handleRunRetention, backupBusy,
  setShowBackupModal, setShowRestoreModal, setRestoreFile, backupRunning = false,
  handleDownloadBackup, handleDeleteBackup, handleClearBackupPassword,
}) {
  const { t } = useTranslation()
  const { copy, isCopied } = useClipboard()
  const isAdmin = hasPermission('admin:system')
  // The KDF and the password need admin:settings; the schedule is refused by the API.
  const canAdminSettings = Boolean(hasPermission('admin:settings'))
  const canWriteSettings = Boolean(hasPermission('write:settings'))
  const allSelected = backups.length > 0 && selectedBackups.length === backups.length
  const diskHigh = typeof backupMeta.disk_used_pct === 'number' && backupMeta.disk_used_pct >= 85
  // HA: the archives live in the shared database, listed the same from every node
  const sharedStore = backupMeta.storage === 'database'
  // The server's figures, read after each save: the saved ceiling, not the field being typed,
  // and only the archives retention counts
  const overCeiling = backupSchedule.over_ceiling === true
  const storedMiB = typeof backupSchedule.stored_bytes === 'number'
    ? `${(backupSchedule.stored_bytes / (1024 * 1024)).toFixed(1)} MiB` : null

  const sortOptions = [
    { value: 'created_desc', label: t('settings.backupSortNewest') },
    { value: 'created_asc', label: t('settings.backupSortOldest') },
    { value: 'size_desc', label: t('settings.backupSortLargest') },
    { value: 'size_asc', label: t('settings.backupSortSmallest') },
    { value: 'name_asc', label: t('settings.backupSortNameAsc') },
    { value: 'name_desc', label: t('settings.backupSortNameDesc') },
  ]

  return (
    <DetailContent>
      <DetailHeader
        icon={Database}
        title={t('settings.helpBackup')}
        subtitle={t('settings.backupSubtitle')}
      />

      <DetailSection title={t('settings.automaticBackups')} icon={Database} iconClass="icon-bg-emerald">
        <div className="space-y-4">
          <ToggleSwitch
            checked={settings.auto_backup_enabled || false}
            onChange={(val) => updateSetting('auto_backup_enabled', val)}
            label={t('settings.enableAutoBackups')}
            description={t('settings.autoBackupsDesc')}
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
              <Button type="button" onClick={() => handleSave('backup')} disabled={saving}>
                <FloppyDisk size={16} />
                {t('settings.saveSettings')}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setShowBackupModal(true)}>
                <Database size={16} />
                {backupRunning ? t('settings.backupInProgress') : t('settings.createBackup')}
              </Button>
            </div>
          )}
        </div>
      </DetailSection>

      {/* Retention — applies to ALL backups, enforced daily (decoupled from auto-backup) */}
      <DetailSection title={t('settings.retentionPeriod')} icon={Broom} iconClass="icon-bg-amber">
        <div className="space-y-3">
          <Input
            label={t('settings.retentionPeriod')}
            type="number"
            value={settings.backup_retention_days || 30}
            onChange={(e) => updateSetting('backup_retention_days', parseInt(e.target.value))}
            min="1"
            max="3650"
            helperText={t('settings.retentionHelper')}
          />
          <Input
            label={t('settings.backupMaxTotalMb')}
            type="number"
            value={settings.backup_max_total_mb ?? 0}
            onChange={(e) => updateSetting('backup_max_total_mb', parseInt(e.target.value, 10) || 0)}
            min="0"
            max="1048576"
            helperText={t('settings.backupMaxTotalMbHelper')}
          />
          {storedMiB && (
            <p className="text-xs text-text-secondary" data-testid="backup-space-used">
              {t('settings.backupSpaceUsed', { size: storedMiB, count: backupSchedule.stored_count ?? 0 })}
            </p>
          )}
          {backupSchedule.uncounted_count > 0 && (
            <p className="text-xs text-text-secondary" data-testid="backup-uncounted">
              {t('settings.backupUncountedFiles', { count: backupSchedule.uncounted_count })}
            </p>
          )}
          {overCeiling && (
            <p className="flex items-start gap-2 text-xs text-status-warning" role="alert">
              <WarningCircle size={14} className="flex-shrink-0 mt-0.5" />
              <span>{t('settings.backupOverCeiling', { ceiling: backupSchedule.max_total_mb ?? 0 })}</span>
            </p>
          )}
          {(canWriteSettings || isAdmin) && (
            <div className="flex gap-2">
              {canWriteSettings && (
                <Button type="button" onClick={() => handleSave('backup')} disabled={saving}>
                  <FloppyDisk size={16} />
                  {t('settings.saveSettings')}
                </Button>
              )}
              {isAdmin && (
                <Button type="button" variant="secondary" onClick={handleRunRetention} disabled={backupBusy}>
                  <Broom size={16} />
                  {t('settings.backupCleanupNow')}
                </Button>
              )}
            </div>
          )}
        </div>
      </DetailSection>

      <DetailSection title={t('settings.availableBackups')} icon={Download} iconClass="icon-bg-emerald">
        {/* Summary */}
        <div className="flex flex-wrap items-center gap-2 mb-4 text-xs">
          <Badge variant="secondary">{t('settings.backupCount', { count: backupMeta.total ?? backups.length })}</Badge>
          {backupMeta.total_size && <Badge variant="secondary">{t('settings.backupTotalSize')}: {backupMeta.total_size}</Badge>}
          {backupMeta.disk_free && (
            <Badge variant={diskHigh ? 'warning' : 'secondary'} icon={diskHigh ? WarningCircle : HardDrives}>
              {t('settings.diskFree')}: {backupMeta.disk_free}
              {typeof backupMeta.disk_used_pct === 'number' ? ` (${backupMeta.disk_used_pct}%)` : ''}
            </Badge>
          )}
        </div>
        {sharedStore && (
          <p className="flex items-start gap-2 mb-4 text-xs text-text-secondary">
            <WarningCircle size={14} className="flex-shrink-0 mt-0.5" />
            <span>{t('settings.backupSharedStoreNote')}</span>
          </p>
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
          <div className="p-6 text-center">
            <p className="text-sm text-text-secondary">{backupQuery.search ? t('settings.backupNoMatch') : t('settings.noBackups')}</p>
            {!backupQuery.search && <p className="text-xs text-text-tertiary mt-1">{t('settings.noBackupsHint')}</p>}
          </div>
        ) : (
          <>
            {isAdmin && (
              <label className="flex items-center gap-2 px-3 py-2 text-xs text-text-secondary cursor-pointer select-none">
                <input type="checkbox" checked={allSelected} onChange={toggleSelectAllBackups} />
                {t('settings.backupSelectAll')}
              </label>
            )}
            <div className="space-y-2">
              {backups.map((backup) => (
                <div key={backup.filename} className="flex items-center justify-between p-3 bg-tertiary-50 border border-border-op30 rounded-lg">
                  <div className="flex items-center gap-3 min-w-0">
                    {isAdmin && (
                      <input
                        type="checkbox"
                        checked={selectedBackups.includes(backup.filename)}
                        onChange={() => toggleSelectBackup(backup.filename)}
                      />
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">{backup.filename}</p>
                      <div className="flex gap-4 mt-1">
                        <p className="text-xs text-text-secondary">{backup.size}</p>
                        <p className="text-xs text-text-secondary">{backup.created_at}</p>
                        {backup.node && (
                          <p className="text-xs text-text-secondary truncate">
                            {t('settings.backupNode')}: {backup.node}
                          </p>
                        )}
                        {backup.sha256 && (
                          <p className="text-xs text-text-secondary flex items-center gap-1">
                            {t('settings.backupSha256')}: <code className="font-mono">{backup.sha256.slice(0, 12)}</code>
                            <button
                              type="button"
                              className="text-text-tertiary hover:text-text-primary"
                              aria-label={t('settings.backupCopySha256')}
                              title={t('settings.backupCopySha256')}
                              onClick={() => copy(backup.sha256, `sha256:${backup.filename}`)}
                            >
                              <Copy size={12} />
                            </button>
                            {isCopied(`sha256:${backup.filename}`) && <span>{t('common.copied')}</span>}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <Button type="button" size="sm" variant="secondary" onClick={() => handleDownloadBackup(backup.filename)}>
                      <Download size={14} />
                    </Button>
                    {isAdmin && (
                      <Button type="button" size="sm" variant="danger" onClick={() => handleDeleteBackup(backup.filename)}>
                        <Trash size={14} />
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>

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
      </DetailSection>

      <DetailSection title={t('settings.restoreFromBackup')} icon={UploadSimple} iconClass="icon-bg-orange">
        <div>
          <p className="text-xs text-text-secondary mb-4">{t('settings.restoreFromBackupDesc')}</p>
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
      </DetailSection>
    </DetailContent>
  )
}
