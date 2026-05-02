import { useTranslation } from 'react-i18next'
import { Database, Download, Trash, UploadSimple, FloppyDisk } from '@phosphor-icons/react'
import { Button, Input, Select, FileUpload, DetailHeader, DetailSection, DetailContent } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'

export default function BackupSection({ settings, updateSetting, handleSave, saving, hasPermission, backups, setShowBackupModal, setShowRestoreModal, setRestoreFile, handleDownloadBackup, handleDeleteBackup }) {
  const { t } = useTranslation()
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
              />
              <Input
                label={t('settings.autoBackupPassword')}
                type="password"
                noAutofill
                value={settings.backup_password || ''}
                onChange={(e) => updateSetting('backup_password', e.target.value)}
                placeholder={t('settings.min12Characters')}
                helperText={t('settings.autoBackupPasswordHelper')}
                showStrength
              />
              <Input
                label={t('settings.retentionPeriod')}
                type="number"
                value={settings.backup_retention_days || 30}
                onChange={(e) => updateSetting('backup_retention_days', parseInt(e.target.value))}
                min="1"
                max="365"
              />
            </>
          )}

          {hasPermission('admin:system') && (
            <div className="flex gap-2">
              <Button type="button" onClick={() => handleSave('backup')} disabled={saving}>
                <FloppyDisk size={16} />
                {t('settings.saveSettings')}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setShowBackupModal(true)}>
                <Database size={16} />
                {t('settings.createBackup')}
              </Button>
            </div>
          )}
        </div>
      </DetailSection>

      <DetailSection title={t('settings.availableBackups')} icon={Download} iconClass="icon-bg-emerald">
        {backups.length === 0 ? (
          <div className="p-6 text-center">
            <p className="text-sm text-text-secondary">{t('settings.noBackups')}</p>
            <p className="text-xs text-text-tertiary mt-1">{t('settings.noBackupsHint')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {backups.map((backup) => (
              <div key={backup.filename} className="flex items-center justify-between p-3 bg-tertiary-50 border border-white/5 rounded-lg">
                <div>
                  <p className="text-sm font-medium text-text-primary">{backup.filename}</p>
                  <div className="flex gap-4 mt-1">
                    <p className="text-xs text-text-secondary">{backup.size}</p>
                    <p className="text-xs text-text-secondary">{backup.created_at}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button type="button" size="sm" variant="secondary" onClick={() => handleDownloadBackup(backup.filename)}>
                    <Download size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="danger" onClick={() => handleDeleteBackup(backup.filename)}>
                    <Trash size={14} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </DetailSection>

      <DetailSection title={t('settings.restoreFromBackup')} icon={UploadSimple} iconClass="icon-bg-orange">
        <div>
          <p className="text-xs text-text-secondary mb-4">{t('settings.restoreFromBackupDesc')}</p>
          <FileUpload
            accept=".ucmbkp,.tar.gz"
            onFileSelect={(file) => { setRestoreFile(file); setShowRestoreModal(true) }}
            helperText={t('settings.selectBackupFile')}
          />
        </div>
      </DetailSection>
    </DetailContent>
  )
}
