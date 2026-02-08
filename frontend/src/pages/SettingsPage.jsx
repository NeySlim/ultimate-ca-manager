/**
 * Settings Page - Horizontal tabs for desktop, scrollable for mobile
 * Uses DetailCard design system
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { 
  Gear, EnvelopeSimple, ShieldCheck, Database, ListBullets, FloppyDisk, 
  Envelope, Download, Trash, HardDrives, Lock, Key, Palette, Sun, Moon, Desktop, Info,
  Timer, Clock, WarningCircle, UploadSimple, Certificate, Eye, ArrowsClockwise, Rocket
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  Button, Input, Select, Badge,
  LoadingSpinner, FileUpload, Modal, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent,
  UpdateChecker
} from '../components'
import { SmartImportModal } from '../components/SmartImport'
import LanguageSelector from '../components/ui/LanguageSelector'
import { settingsService, systemService, casService, certificatesService } from '../services'
import { useNotification, useMobile } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'
import { ERRORS, SUCCESS } from '../lib/messages'
import { useTheme } from '../contexts/ThemeContext'
import SSOSettingsSection from './settings/SSOSettingsSection'

// Settings categories with colors for visual distinction
const BASE_SETTINGS_CATEGORIES = [
  { id: 'general', labelKey: 'settings.tabs.general', icon: Gear, color: 'icon-bg-blue' },
  { id: 'appearance', labelKey: 'settings.tabs.appearance', icon: Palette, color: 'icon-bg-violet' },
  { id: 'email', labelKey: 'settings.tabs.email', icon: EnvelopeSimple, color: 'icon-bg-teal' },
  { id: 'security', labelKey: 'settings.tabs.security', icon: ShieldCheck, color: 'icon-bg-amber' },
  { id: 'sso', labelKey: 'settings.tabs.sso', icon: Key, color: 'icon-bg-purple', component: SSOSettingsSection },
  { id: 'backup', labelKey: 'settings.tabs.backup', icon: Database, color: 'icon-bg-emerald' },
  { id: 'audit', labelKey: 'settings.tabs.audit', icon: ListBullets, color: 'icon-bg-orange' },
  { id: 'database', labelKey: 'settings.tabs.database', icon: HardDrives, color: 'icon-bg-blue' },
  { id: 'https', labelKey: 'settings.tabs.https', icon: Lock, color: 'icon-bg-emerald' },
  { id: 'updates', labelKey: 'settings.tabs.updates', icon: Rocket, color: 'icon-bg-violet' },
]

// Appearance Settings Component
function AppearanceSettings() {
  const { t } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const { forceDesktop, setForceDesktop, screenWidth, breakpoints } = useMobile()
  
  const modeOptions = [
    { id: 'system', label: t('settings.followSystem'), icon: Desktop, description: t('settings.followSystemDesc') },
    { id: 'light', label: t('settings.light'), icon: Sun, description: t('settings.lightDesc') },
    { id: 'dark', label: t('settings.dark'), icon: Moon, description: t('settings.darkDesc') },
  ]
  
  return (
    <DetailContent>
      <DetailHeader compact
        icon={Palette}
        title={t('settings.appearance')}
        subtitle={t('settings.appearanceSubtitle')}
      />
      
      <DetailSection title={t('settings.colorTheme')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.colorThemeDesc')}
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {themes.map(theme => (
            <button
              key={theme.id}
              onClick={() => setThemeFamily(theme.id)}
              className={`
                p-4 rounded-lg border-2 transition-all text-left
                ${themeFamily === theme.id 
                  ? 'border-accent-primary bg-accent-primary/10' 
                  : 'border-border hover:border-text-tertiary bg-bg-tertiary/50'
                }
              `}
            >
              <div className="flex items-center gap-3 mb-2">
                <div 
                  className="w-5 h-5 rounded-full shadow-inner"
                  style={{ background: theme.accent }}
                />
                <span className="font-medium text-sm text-text-primary">{theme.name}</span>
              </div>
              <div className="flex gap-1">
                {/* Preview colors - show accent and distinct bg colors */}
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.accent }} />
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.dark['bg-tertiary'] }} />
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.light['bg-tertiary'] }} />
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.light['accent-primary'] || theme.accent }} />
              </div>
            </button>
          ))}
        </div>
      </DetailSection>
      
      <DetailSection title={t('settings.appearanceMode')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.appearanceModeDesc')}
        </p>
        <div className="space-y-2">
          {modeOptions.map(opt => {
            const Icon = opt.icon
            return (
              <button
                key={opt.id}
                onClick={() => setMode(opt.id)}
                className={`
                  w-full p-4 rounded-lg border-2 transition-all text-left flex items-center gap-4
                  ${mode === opt.id 
                    ? 'border-accent-primary bg-accent-primary/10' 
                    : 'border-border hover:border-text-tertiary bg-bg-tertiary/50'
                  }
                `}
              >
                <div className={`
                  w-10 h-10 rounded-lg flex items-center justify-center
                  ${mode === opt.id ? 'bg-accent-primary text-white' : 'bg-bg-secondary text-text-secondary'}
                `}>
                  <Icon size={20} weight={mode === opt.id ? 'fill' : 'regular'} />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-text-primary">{opt.label}</div>
                  <div className="text-xs text-text-tertiary">{opt.description}</div>
                </div>
                {mode === opt.id && (
                  <div className="w-5 h-5 rounded-full bg-accent-primary flex items-center justify-center">
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </DetailSection>
      
      <DetailSection title={t('settings.layoutMode')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.layoutModeDesc')}
        </p>
        <button
          onClick={() => setForceDesktop(!forceDesktop)}
          className={`
            w-full p-4 rounded-lg border-2 transition-all text-left flex items-center gap-4
            ${forceDesktop 
              ? 'border-accent-primary bg-accent-primary/10' 
              : 'border-border hover:border-text-tertiary bg-bg-tertiary/50'
            }
          `}
        >
          <div className={`
            w-10 h-10 rounded-lg flex items-center justify-center
            ${forceDesktop ? 'bg-accent-primary text-white' : 'bg-bg-secondary text-text-secondary'}
          `}>
            <Desktop size={20} weight={forceDesktop ? 'fill' : 'regular'} />
          </div>
          <div className="flex-1">
            <div className="font-medium text-text-primary">{t('settings.forceDesktopLayout')}</div>
            <div className="text-xs text-text-tertiary">
              {forceDesktop 
                ? t('settings.desktopLayoutEnabled') 
                : t('settings.mobileLayoutActivates', { breakpoint: breakpoints.lg, current: screenWidth })
              }
            </div>
          </div>
          <div className={`
            w-12 h-6 rounded-full transition-colors relative
            ${forceDesktop ? 'bg-accent-primary' : 'bg-bg-secondary border border-border'}
          `}>
            <div className={`
              absolute top-1 w-4 h-4 rounded-full transition-transform
              ${forceDesktop 
                ? 'bg-white translate-x-6' 
                : 'bg-text-tertiary translate-x-1'
              }
            `} />
          </div>
        </button>
        {forceDesktop && (
          <p className="text-xs text-text-tertiary mt-2 flex items-center gap-1">
            <Info size={12} />
            {t('settings.settingSavedInBrowser')}
          </p>
        )}
      </DetailSection>
      
      <DetailSection title={t('settings.language')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.languageDesc')}
        </p>
        <LanguageSelector />
      </DetailSection>
      
      <DetailSection title={t('settings.preview')}>
        <div className="p-4 rounded-lg bg-bg-tertiary border border-border">
          <p className="text-sm text-text-secondary mb-2">{t('settings.currentSettings')}:</p>
          <p className="text-text-primary">
            <span className="font-medium">{themes.find(th => th.id === themeFamily)?.name}</span>
            {' · '}
            <span className="text-text-secondary">
              {mode === 'system' ? t('settings.followingSystemPreference') : mode === 'dark' ? t('settings.darkMode') : t('settings.lightMode')}
            </span>
            {forceDesktop && (
              <>
                {' · '}
                <span className="text-accent-primary">{t('settings.desktopForced')}</span>
              </>
            )}
          </p>
        </div>
      </DetailSection>
    </DetailContent>
  )
}

export default function SettingsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm, showPrompt } = useNotification()
  const { canWrite, hasPermission } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState({})
  const [backups, setBackups] = useState([])
  const [dbStats, setDbStats] = useState(null)
  const [httpsInfo, setHttpsInfo] = useState(null)
  const [certificates, setCertificates] = useState([])
  const [selectedHttpsCert, setSelectedHttpsCert] = useState('')
  const [cas, setCas] = useState([])
  
  // Selected category - read from URL param or default to 'general'
  const [selectedCategory, setSelectedCategory] = useState(
    searchParams.get('tab') || 'general'
  )
  
  // Update URL when category changes
  const handleCategoryChange = (categoryId) => {
    setSelectedCategory(categoryId)
    if (categoryId === 'general') {
      searchParams.delete('tab')
    } else {
      searchParams.set('tab', categoryId)
    }
    setSearchParams(searchParams, { replace: true })
  }
  
  // Backup modal states
  const [showBackupModal, setShowBackupModal] = useState(false)
  const [showRestoreModal, setShowRestoreModal] = useState(false)
  const [backupPassword, setBackupPassword] = useState('')
  const [restorePassword, setRestorePassword] = useState('')
  const [restoreFile, setRestoreFile] = useState(null)
  const [backupLoading, setBackupLoading] = useState(false)
  
  // HTTPS import modal
  const [showHttpsImportModal, setShowHttpsImportModal] = useState(false)

  // All settings categories (SSO now integrated directly)
  const SETTINGS_CATEGORIES = BASE_SETTINGS_CATEGORIES

  useEffect(() => {
    loadSettings()
    loadBackups()
    loadHttpsInfo()
    loadCAs()
    loadCertificates()
    loadDbStats()
  }, [])

  const loadSettings = async () => {
    setLoading(true)
    try {
      const response = await settingsService.getAll()
      setSettings(response.data || response || {})
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.SETTINGS)
    } finally {
      setLoading(false)
    }
  }

  const loadCAs = async () => {
    try {
      const data = await casService.getAll()
      setCas(data.data || [])
    } catch (error) {
      console.error('Failed to load CAs:', error)
    }
  }

  const loadBackups = async () => {
    try {
      const data = await systemService.listBackups()
      setBackups(data.data || [])
    } catch (error) {
      console.error('Failed to load backups:', error)
    }
  }

  const loadHttpsInfo = async () => {
    try {
      const data = await systemService.getHttpsCertInfo()
      setHttpsInfo(data.data || {})
    } catch (error) {
      console.error('Failed to load HTTPS cert info:', error)
    }
  }

  const loadDbStats = async () => {
    try {
      const data = await systemService.getDatabaseStats()
      const stats = data.data || {}
      setDbStats({
        certificates: stats.counts?.certificates || 0,
        cas: stats.counts?.cas || 0,
        size: stats.size_mb ? `${stats.size_mb} MB` : '-',
        last_optimized: stats.last_vacuum || 'Never'
      })
    } catch (error) {
      console.error('Failed to load database stats:', error)
    }
  }

  const loadCertificates = async () => {
    try {
      const data = await certificatesService.getAll({ status: 'valid' })
      const validCerts = (data.data || []).filter(cert => 
        cert.has_private_key && 
        cert.status === 'valid' &&
        new Date(cert.valid_to) > new Date()
      )
      setCertificates(validCerts)
    } catch (error) {
      console.error('Failed to load certificates:', error)
    }
  }

  const handleSave = async (section) => {
    setSaving(true)
    try {
      await settingsService.updateBulk(settings)
      showSuccess(SUCCESS.UPDATE.SETTINGS)
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.SETTINGS)
    } finally {
      setSaving(false)
    }
  }

  const handleTestEmail = async () => {
    try {
      await settingsService.testEmail(settings.admin_email)
      showSuccess(SUCCESS.EMAIL.TEST_SENT)
    } catch (error) {
      showError(error.message || ERRORS.EMAIL.TEST_FAILED)
    }
  }

  const handleBackup = async () => {
    if (!backupPassword || backupPassword.length < 12) {
      showError(t('settings.passwordMinLength'))
      return
    }
    
    setBackupLoading(true)
    try {
      const response = await systemService.backup(backupPassword)
      if (response.data) {
        const blob = await systemService.downloadBackup(response.data.filename)
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = response.data.filename
        a.click()
        URL.revokeObjectURL(url)
        showSuccess(SUCCESS.BACKUP.CREATED)
        setShowBackupModal(false)
        setBackupPassword('')
        loadBackups()
      }
    } catch (error) {
      showError(error.message || ERRORS.BACKUP.CREATE_FAILED)
    } finally {
      setBackupLoading(false)
    }
  }

  const handleDownloadBackup = async (filename) => {
    try {
      const blob = await systemService.downloadBackup(filename)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(SUCCESS.BACKUP.DOWNLOADED)
    } catch (error) {
      showError(error.message || ERRORS.BACKUP.DOWNLOAD_FAILED)
    }
  }

  const handleDeleteBackup = async (filename) => {
    const confirmed = await showConfirm(t('settings.confirmDeleteBackup', { filename }), {
      title: t('settings.deleteBackup'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await systemService.deleteBackup(filename)
      showSuccess(SUCCESS.BACKUP.DELETED)
      loadBackups()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.BACKUP)
    }
  }

  const handleRestoreBackup = async () => {
    if (!restoreFile) {
      showError(t('settings.selectBackupFile'))
      return
    }
    if (!restorePassword || restorePassword.length < 12) {
      showError(t('settings.passwordMinLength'))
      return
    }
    
    setBackupLoading(true)
    try {
      const result = await systemService.restore(restoreFile, restorePassword)
      showSuccess(t('settings.backupRestored', { users: result.data?.users || 0, cas: result.data?.cas || 0, certs: result.data?.certificates || 0 }))
      setShowRestoreModal(false)
      setRestorePassword('')
      setRestoreFile(null)
      setTimeout(() => window.location.reload(), 2000)
    } catch (error) {
      showError(error.message || ERRORS.BACKUP.RESTORE_FAILED)
    } finally {
      setBackupLoading(false)
    }
  }

  const handleOptimizeDb = async () => {
    try {
      await systemService.optimizeDatabase()
      showSuccess(SUCCESS.DATABASE.OPTIMIZED)
    } catch (error) {
      showError(error.message || ERRORS.DATABASE.OPTIMIZE_FAILED)
    }
  }

  const handleIntegrityCheck = async () => {
    try {
      const result = await systemService.integrityCheck()
      if (result.passed) {
        showSuccess(SUCCESS.DATABASE.INTEGRITY_PASSED)
      } else {
        showError(t('settings.integrityErrors', { count: result.errors }))
      }
    } catch (error) {
      showError(error.message || ERRORS.DATABASE.INTEGRITY_FAILED)
    }
  }

  const handleExportDb = async () => {
    try {
      const blob = await systemService.exportDatabase()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ucm-database-${new Date().toISOString().split('T')[0]}.sql`
      a.click()
      showSuccess(SUCCESS.EXPORT.DATABASE)
    } catch (error) {
      showError(error.message || ERRORS.DATABASE.EXPORT_FAILED)
    }
  }

  const handleResetDb = async () => {
    const confirmed1 = await showConfirm(t('settings.resetDbWarning'), {
      title: t('settings.resetDatabase'),
      confirmText: t('common.next'),
      variant: 'danger'
    })
    if (!confirmed1) return

    const confirmation = await showPrompt(t('settings.typeYesToConfirm'), {
      title: t('settings.finalConfirmation'),
      placeholder: 'YES'
    })
    if (confirmation !== 'YES') {
      showError(t('settings.resetDbCancelled'))
      return
    }

    try {
      await systemService.resetDatabase()
      showSuccess(SUCCESS.DATABASE.RESET)
      setTimeout(() => window.location.reload(), 2000)
    } catch (error) {
      showError(error.message || ERRORS.DATABASE.RESET_FAILED)
    }
  }

  const handleApplyUcmCert = async () => {
    if (!selectedHttpsCert) {
      showError(t('settings.selectCertificate'))
      return
    }

    const confirmed = await showConfirm(t('settings.applyHttpsCertConfirm'), {
      title: t('settings.applyCertificate'),
      confirmText: t('settings.applyAndRestart')
    })
    if (!confirmed) return
    
    try {
      await systemService.applyHttpsCert({
        cert_id: selectedHttpsCert
      })
      showSuccess(SUCCESS.HTTPS.APPLIED)
      setTimeout(() => window.location.reload(), 3000)
    } catch (error) {
      showError(error.message || ERRORS.HTTPS.APPLY_FAILED)
    }
  }

  const handleRegenerateHttpsCert = async () => {
    const confirmed = await showConfirm(t('settings.regenerateCertConfirm'), {
      title: t('settings.regenerateCertificate'),
      confirmText: t('settings.regenerateAndRestart')
    })
    if (!confirmed) return
    
    try {
      await systemService.regenerateHttpsCert({
        common_name: window.location.hostname,
        validity_days: 365
      })
      showSuccess(SUCCESS.HTTPS.REGENERATED)
      setTimeout(() => window.location.reload(), 3000)
    } catch (error) {
      showError(error.message || ERRORS.HTTPS.REGENERATE_FAILED)
    }
  }

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  // Render content for each category
  const renderCategoryContent = () => {
    switch (selectedCategory) {
      case 'general':
        return (
          <DetailContent>
            <DetailHeader compact
              icon={Gear}
              title={t('settings.generalTitle')}
              subtitle={t('settings.generalSubtitle')}
              actions={canWrite('settings') ? [
                { label: t('settings.saveChanges'), icon: FloppyDisk, onClick: () => handleSave('general'), disabled: saving }
              ] : []}
            />
            <DetailSection title={t('settings.systemConfiguration')} icon={Gear} iconClass="icon-bg-blue">
              <div className="space-y-4">
                <Input
                  label={t('settings.systemName')}
                  value={settings.system_name || ''}
                  onChange={(e) => updateSetting('system_name', e.target.value)}
                  helperText={t('settings.systemNameHelper')}
                />
                <Input
                  label={t('settings.baseUrl')}
                  value={settings.base_url || ''}
                  onChange={(e) => updateSetting('base_url', e.target.value)}
                  placeholder={t('settings.baseUrlPlaceholder')}
                  helperText={t('settings.baseUrlHelper')}
                />
              </div>
            </DetailSection>
            <DetailSection title={t('settings.sessionTimezone')} icon={Clock} iconClass="icon-bg-teal">
              <div className="space-y-4">
                <Input
                  label={t('settings.sessionTimeout')}
                  type="number"
                  value={settings.session_timeout || 30}
                  onChange={(e) => updateSetting('session_timeout', parseInt(e.target.value))}
                  min="5"
                  max="1440"
                />
                <Select
                  label={t('settings.timezone')}
                  options={[
                    { value: 'UTC', label: 'UTC' },
                    { value: 'America/New_York', label: 'America/New York' },
                    { value: 'Europe/Paris', label: 'Europe/Paris' },
                    { value: 'Asia/Tokyo', label: 'Asia/Tokyo' },
                  ]}
                  value={settings.timezone || 'UTC'}
                  onChange={(val) => updateSetting('timezone', val)}
                />
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'appearance':
        return <AppearanceSettings />

      case 'email':
        return (
          <DetailContent>
            <DetailHeader compact
              icon={EnvelopeSimple}
              title={t('settings.emailTitle')}
              subtitle={t('settings.emailSubtitle')}
              actions={canWrite('settings') ? [
                { label: t('settings.testEmail'), icon: Envelope, onClick: handleTestEmail, variant: 'secondary' },
                { label: t('settings.saveChanges'), icon: FloppyDisk, onClick: () => handleSave('email'), disabled: saving }
              ] : []}
            />
            <DetailSection title={t('settings.smtpServer')} icon={Envelope} iconClass="icon-bg-violet">
              <DetailGrid>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label={t('settings.smtpHost')}
                    value={settings.smtp_host || ''}
                    onChange={(e) => updateSetting('smtp_host', e.target.value)}
                    placeholder={t('settings.smtpHostPlaceholder')}
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label={t('settings.smtpPort')}
                    type="number"
                    value={settings.smtp_port || 587}
                    onChange={(e) => updateSetting('smtp_port', parseInt(e.target.value))}
                  />
                </div>
              </DetailGrid>
            </DetailSection>
            <DetailSection title={t('settings.authentication')} icon={Key} iconClass="icon-bg-amber">
              <div className="space-y-4">
                <Input
                  label={t('settings.smtpUsername')}
                  value={settings.smtp_username || ''}
                  onChange={(e) => updateSetting('smtp_username', e.target.value)}
                />
                <Input
                  label={t('settings.smtpPassword')}
                  type="password"
                  value={settings.smtp_password || ''}
                  onChange={(e) => updateSetting('smtp_password', e.target.value)}
                  placeholder={t('settings.passwordPlaceholder')}
                />
              </div>
            </DetailSection>
            <DetailSection title={t('settings.emailOptions')} icon={EnvelopeSimple} iconClass="icon-bg-blue">
              <div className="space-y-4">
                <Input
                  label={t('settings.fromEmail')}
                  type="email"
                  value={settings.smtp_from_email || ''}
                  onChange={(e) => updateSetting('smtp_from_email', e.target.value)}
                  placeholder={t('settings.fromEmailPlaceholder')}
                />
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.smtp_use_tls || false}
                    onChange={(e) => updateSetting('smtp_use_tls', e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                  <span className="text-sm text-text-primary">{t('settings.useTls')}</span>
                </label>
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'security':
        return (
          <DetailContent>
            <DetailHeader compact
              icon={ShieldCheck}
              title={t('settings.securityTitle')}
              subtitle={t('settings.securitySubtitle')}
              actions={hasPermission('admin:system') ? [
                { label: t('settings.saveChanges'), icon: FloppyDisk, onClick: () => handleSave('security'), disabled: saving }
              ] : []}
            />
            <DetailSection title={t('settings.twoFactorAuth')} icon={ShieldCheck} iconClass="icon-bg-emerald">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.enforce_2fa || false}
                  onChange={(e) => updateSetting('enforce_2fa', e.target.checked)}
                  className="rounded border-border bg-bg-tertiary"
                />
                <div>
                  <p className="text-sm text-text-primary font-medium">{t('settings.enforce2fa')}</p>
                  <p className="text-xs text-text-secondary">{t('settings.enforce2faDesc')}</p>
                </div>
              </label>
            </DetailSection>
            <DetailSection title={t('settings.passwordPolicy')} icon={Lock} iconClass="icon-bg-violet">
              <div className="space-y-4">
                <Input
                  label={t('settings.minPasswordLength')}
                  type="number"
                  value={settings.min_password_length || 8}
                  onChange={(e) => updateSetting('min_password_length', parseInt(e.target.value))}
                  min="6"
                  max="32"
                />
                <div className="space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.password_require_uppercase || false}
                      onChange={(e) => updateSetting('password_require_uppercase', e.target.checked)}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{t('settings.requireUppercase')}</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.password_require_numbers || false}
                      onChange={(e) => updateSetting('password_require_numbers', e.target.checked)}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{t('settings.requireNumbers')}</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.password_require_special || false}
                      onChange={(e) => updateSetting('password_require_special', e.target.checked)}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{t('settings.requireSpecial')}</span>
                  </label>
                </div>
              </div>
            </DetailSection>
            <DetailSection title={t('settings.sessionRateLimits')} icon={Timer} iconClass="icon-bg-teal">
              <DetailGrid>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label={t('settings.sessionDuration')}
                    type="number"
                    value={settings.session_duration || 24}
                    onChange={(e) => updateSetting('session_duration', parseInt(e.target.value))}
                    min="1"
                    max="720"
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label={t('settings.apiRateLimit')}
                    type="number"
                    value={settings.api_rate_limit || 60}
                    onChange={(e) => updateSetting('api_rate_limit', parseInt(e.target.value))}
                    min="10"
                    max="1000"
                  />
                </div>
              </DetailGrid>
            </DetailSection>
          </DetailContent>
        )

      case 'backup':
        return (
          <DetailContent>
            <DetailHeader compact
              icon={Database}
              title={t('settings.backupTitle')}
              subtitle={t('settings.backupSubtitle')}
              actions={hasPermission('admin:system') ? [
                { label: t('settings.createBackup'), icon: Database, onClick: () => setShowBackupModal(true) }
              ] : []}
            />
            <DetailSection title={t('settings.automaticBackups')} icon={Database} iconClass="icon-bg-emerald">
              <div className="space-y-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.auto_backup_enabled || false}
                    onChange={(e) => updateSetting('auto_backup_enabled', e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                  <div>
                    <p className="text-sm text-text-primary font-medium">{t('settings.enableAutoBackups')}</p>
                    <p className="text-xs text-text-secondary">{t('settings.autoBackupsDesc')}</p>
                  </div>
                </label>

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
                  <Button size="sm" onClick={() => handleSave('backup')} disabled={saving}>
                    <FloppyDisk size={16} />
                    {t('settings.saveSettings')}
                  </Button>
                )}
              </div>
            </DetailSection>

            <DetailSection title={t('settings.availableBackups')} icon={Download} iconClass="icon-bg-blue">
              {backups.length === 0 ? (
                <div className="p-6 text-center">
                  <p className="text-sm text-text-secondary">{t('settings.noBackups')}</p>
                  <p className="text-xs text-text-tertiary mt-1">{t('settings.noBackupsHint')}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {backups.map((backup) => (
                    <div key={backup.filename} className="flex items-center justify-between p-3 bg-bg-tertiary/50 border border-white/5 rounded-lg">
                      <div>
                        <p className="text-sm font-medium text-text-primary">{backup.filename}</p>
                        <div className="flex gap-4 mt-1">
                          <p className="text-xs text-text-secondary">{backup.size}</p>
                          <p className="text-xs text-text-secondary">{backup.created_at}</p>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="secondary" onClick={() => handleDownloadBackup(backup.filename)}>
                          <Download size={14} />
                        </Button>
                        <Button size="sm" variant="danger" onClick={() => handleDeleteBackup(backup.filename)}>
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

      case 'audit':
        return (
          <DetailContent>
            <DetailHeader compact
              icon={ListBullets}
              title={t('settings.auditTitle')}
              subtitle={t('settings.auditSubtitle')}
              actions={hasPermission('admin:system') ? [
                { label: t('settings.saveChanges'), icon: FloppyDisk, onClick: () => handleSave('audit'), disabled: saving }
              ] : []}
            />
            <DetailSection title={t('settings.auditLogging')} icon={ListBullets} iconClass="icon-bg-orange">
              <div className="space-y-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.audit_enabled || true}
                    onChange={(e) => updateSetting('audit_enabled', e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                  <div>
                    <p className="text-sm text-text-primary font-medium">{t('settings.enableAuditLogging')}</p>
                    <p className="text-xs text-text-secondary">{t('settings.enableAuditLoggingDesc')}</p>
                  </div>
                </label>

                <Input
                  label={t('settings.logRetention')}
                  type="number"
                  value={settings.audit_retention_days || 90}
                  onChange={(e) => updateSetting('audit_retention_days', parseInt(e.target.value))}
                  min="7"
                  max="730"
                  disabled={!settings.audit_enabled}
                />
              </div>
            </DetailSection>
            <DetailSection title={t('settings.eventsToLog')} icon={Eye} iconClass="icon-bg-blue">
              <div className="space-y-2">
                {[
                  { key: 'userLoginLogout', label: t('settings.eventUserLoginLogout') },
                  { key: 'certIssueRevoke', label: t('settings.eventCertIssueRevoke') },
                  { key: 'caCreateDelete', label: t('settings.eventCaCreateDelete') },
                  { key: 'settingsChanges', label: t('settings.eventSettingsChanges') },
                  { key: 'userManagement', label: t('settings.eventUserManagement') },
                ].map(event => (
                  <label key={event.key} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={true}
                      disabled={!settings.audit_enabled}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{event.label}</span>
                  </label>
                ))}
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'database':
        return (
          <DetailContent>
            <DetailHeader compact
              icon={HardDrives}
              title={t('settings.databaseTitle')}
              subtitle={t('settings.databaseSubtitle')}
            />
            <DetailSection title={t('settings.databaseStatistics')} icon={HardDrives} iconClass="icon-bg-blue">
              <DetailGrid>
                <DetailField
                  label={t('settings.totalCertificates')}
                  value={dbStats?.certificates || '-'}
                />
                <DetailField
                  label={t('settings.certificateAuthorities')}
                  value={dbStats?.cas || '-'}
                />
                <DetailField
                  label={t('settings.databaseSize')}
                  value={dbStats?.size || '-'}
                />
                <DetailField
                  label={t('settings.lastOptimized')}
                  value={dbStats?.last_optimized || '-'}
                />
              </DetailGrid>
            </DetailSection>

            <DetailSection title={t('settings.maintenance')} icon={Gear} iconClass="icon-bg-teal">
              <div className="space-y-3">
                <div className="flex flex-wrap gap-3">
                  <Button size="sm" variant="secondary" onClick={handleOptimizeDb}>
                    <Database size={16} />
                    {t('settings.optimizeDatabase')}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={handleIntegrityCheck}>
                    <ShieldCheck size={16} />
                    {t('settings.integrityCheck')}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={handleExportDb}>
                    <Download size={16} />
                    {t('settings.exportDatabase')}
                  </Button>
                </div>
              </div>
            </DetailSection>

            <DetailSection title={t('settings.dangerZone')} icon={WarningCircle} iconClass="icon-bg-orange" className="mt-4">
              <div className="p-4 status-danger-bg status-danger-border border rounded-lg">
                <h4 className="text-sm font-semibold text-status-danger mb-2">⚠️ {t('settings.databaseReset')}</h4>
                <p className="text-xs text-text-secondary mb-3">
                  {t('settings.databaseResetDesc')}
                </p>
                <Button variant="danger" size="sm" onClick={handleResetDb}>
                  <Trash size={16} />
                  {t('settings.resetDatabase')}
                </Button>
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'https':
        return (
          <DetailContent>
            <DetailHeader compact
              icon={Lock}
              title={t('settings.httpsTitle')}
              subtitle={t('settings.httpsSubtitle')}
              badge={httpsInfo?.type && (
                <Badge variant={httpsInfo?.type === 'CA-Signed' ? 'success' : httpsInfo?.type === 'Self-Signed' ? 'warning' : 'secondary'}>
                  {httpsInfo?.type}
                </Badge>
              )}
            />
            <DetailSection title={t('settings.currentCertificate')} icon={Certificate} iconClass="icon-bg-blue">
              <DetailGrid>
                <DetailField
                  label={t('settings.commonName')}
                  value={httpsInfo?.common_name || window.location.hostname}
                />
                <DetailField
                  label={t('settings.issuer')}
                  value={httpsInfo?.issuer || '-'}
                />
                <DetailField
                  label={t('settings.validFrom')}
                  value={formatDate(httpsInfo?.valid_from)}
                />
                <DetailField
                  label={t('settings.validUntil')}
                  value={formatDate(httpsInfo?.valid_to)}
                />
                <DetailField
                  label={t('settings.fingerprintSha256')}
                  value={httpsInfo?.fingerprint || '-'}
                  mono
                  copyable
                  fullWidth
                />
              </DetailGrid>
            </DetailSection>

            <DetailSection title={t('settings.useUcmCertificate')} icon={Certificate} iconClass="icon-bg-violet">
              <div className="space-y-4">
                <p className="text-xs text-text-secondary">
                  {t('settings.useUcmCertificateDesc')}
                </p>
                <Select
                  label={t('settings.selectCertificate')}
                  value={selectedHttpsCert}
                  onChange={setSelectedHttpsCert}
                  placeholder={t('settings.chooseCertificate')}
                  options={certificates.map(cert => ({
                    value: cert.id,
                    label: `${cert.common_name || t('certificates.certificate')} (${t('settings.expires')} ${formatDate(cert.valid_to)})`
                  }))}
                />
                {certificates.length === 0 && (
                  <p className="text-xs text-text-secondary">
                    {t('settings.noValidCertificates')}
                  </p>
                )}
                <Button 
                  variant="secondary" 
                  size="sm"
                  onClick={handleApplyUcmCert}
                  disabled={!selectedHttpsCert}
                >
                  <ShieldCheck size={16} />
                  {t('settings.applySelectedCertificate')}
                </Button>
              </div>
            </DetailSection>

            <DetailSection title={t('settings.regenerateCertificate')} icon={ArrowsClockwise} iconClass="icon-bg-emerald">
              <div className="space-y-3">
                <p className="text-xs text-text-secondary">
                  {t('settings.regenerateCertificateDesc')}
                </p>
                <Button variant="secondary" size="sm" onClick={handleRegenerateHttpsCert}>
                  <Key size={16} />
                  {t('settings.regenerateSelfSigned')}
                </Button>
              </div>
            </DetailSection>

            <DetailSection title={t('settings.applyCustomCertificate')} icon={Lock} iconClass="icon-bg-amber">
              <div className="space-y-3">
                <p className="text-xs text-text-secondary">
                  {t('settings.applyCustomCertificateDesc')}
                </p>
                <Button
                  variant="secondary"
                  onClick={() => setShowHttpsImportModal(true)}
                >
                  <UploadSimple size={16} className="mr-2" />
                  {t('common.importCertificate')}
                </Button>
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'updates':
        return (
          <DetailContent>
            <DetailHeader compact
              icon={Rocket}
              title={t('settings.updatesTitle')}
              subtitle={t('settings.updatesSubtitle')}
            />
            <UpdateChecker />
          </DetailContent>
        )

      default:
        // Check if it's a Pro category with a custom component
        const proCategory = SETTINGS_CATEGORIES.find(c => c.id === selectedCategory && c.component)
        if (proCategory?.component) {
          const ProComponent = proCategory.component
          return <ProComponent />
        }
        return null
    }
  }

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      <HelpCard variant="info" title={t('settings.helpGeneral')}>
        Configure your UCM instance name, base URL, session timeout, and timezone.
        These settings affect all users and system behavior.
      </HelpCard>
      
      <HelpCard variant="tip" title={t('settings.helpEmail')}>
        Configure SMTP settings to enable email notifications for certificate
        expiration alerts and system events. Test your configuration before saving.
      </HelpCard>

      <HelpCard variant="warning" title={t('settings.helpSecurity')}>
        Security settings like 2FA enforcement and password policies affect all users.
        Changes take effect immediately - users may need to update their credentials.
      </HelpCard>

      <HelpCard variant="info" title={t('settings.helpBackup')}>
        Create encrypted backups of all data including certificates, CAs, users, 
        and settings. Store backup passwords securely - they cannot be recovered.
      </HelpCard>

      <HelpCard variant="tip" title={t('settings.helpDatabase')}>
        Optimize database performance, check integrity, or export data.
        The danger zone allows complete database reset - use with extreme caution.
      </HelpCard>

      <HelpCard variant="info" title={t('settings.helpHttps')}>
        Manage the SSL/TLS certificate used by UCM. You can use a certificate
        from your PKI or generate a self-signed certificate for testing.
      </HelpCard>
    </div>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message={t('settings.loadingSettings')} />
      </div>
    )
  }

  // Transform categories to tabs format with translations
  const tabs = SETTINGS_CATEGORIES.map(cat => ({
    id: cat.id,
    label: t(cat.labelKey),
    icon: cat.icon,
    color: cat.color,
    badge: undefined  // All features now community
  }))

  return (
    <>
      <ResponsiveLayout
        title={t('settings.title')}
        subtitle={t('settings.subtitle')}
        icon={Gear}
        tabs={tabs}
        activeTab={selectedCategory}
        onTabChange={handleCategoryChange}
        helpPageKey="settings"
      >
        <div className="max-w-4xl mx-auto p-4 md:p-6">
          {renderCategoryContent()}
        </div>
      </ResponsiveLayout>

      {/* Backup Password Modal */}
      <Modal
        open={showBackupModal}
        onClose={() => { setShowBackupModal(false); setBackupPassword('') }}
        title={t('settings.createEncryptedBackup')}
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            {t('settings.createBackupDesc')}
          </p>
          <Input
            label={t('settings.encryptionPassword')}
            type="password"
            value={backupPassword}
            onChange={(e) => setBackupPassword(e.target.value)}
            placeholder={t('settings.min12Characters')}
            helperText={t('settings.encryptionPasswordHelper')}
            autoFocus
            showStrength
          />
          <div className="flex gap-3 justify-end pt-4">
            <Button variant="secondary" onClick={() => { setShowBackupModal(false); setBackupPassword('') }}>
              {t('common.cancel')}
            </Button>
            <Button 
              onClick={handleBackup} 
              disabled={backupLoading || !backupPassword || backupPassword.length < 12}
            >
              {backupLoading ? t('settings.creating') : t('settings.createAndDownload')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Restore Password Modal */}
      <Modal
        open={showRestoreModal}
        onClose={() => { setShowRestoreModal(false); setRestorePassword(''); setRestoreFile(null) }}
        title={t('settings.restoreFromBackup')}
      >
        <div className="space-y-4">
          <div className="p-3 status-warning-bg status-warning-border border rounded-lg">
            <p className="text-sm status-warning-text font-medium">⚠️ {t('common.warning')}</p>
            <p className="text-xs status-warning-text opacity-80">
              {t('settings.restoreWarning')}
            </p>
          </div>
          {restoreFile && (
            <p className="text-sm text-text-primary">
              {t('settings.file')}: <strong>{restoreFile.name}</strong>
            </p>
          )}
          <Input
            label={t('settings.backupPassword')}
            type="password"
            value={restorePassword}
            onChange={(e) => setRestorePassword(e.target.value)}
            placeholder={t('settings.enterBackupPassword')}
            autoFocus
          />
          <div className="flex gap-3 justify-end pt-4">
            <Button variant="secondary" onClick={() => { setShowRestoreModal(false); setRestorePassword(''); setRestoreFile(null) }}>
              {t('common.cancel')}
            </Button>
            <Button 
              variant="danger"
              onClick={handleRestoreBackup} 
              disabled={backupLoading || !restorePassword || restorePassword.length < 12}
            >
              {backupLoading ? t('settings.restoring') : t('settings.restoreBackup')}
            </Button>
          </div>
        </div>
      </Modal>
      
      {/* Smart Import Modal for HTTPS certificate */}
      <SmartImportModal
        isOpen={showHttpsImportModal}
        onClose={() => setShowHttpsImportModal(false)}
        onImportComplete={async (imported) => {
          setShowHttpsImportModal(false)
          // If a certificate was imported with private key, offer to apply it
          if (imported?.id && imported?.has_private_key) {
            const apply = await showConfirm(t('settings.applyImportedCertConfirm'), {
              title: t('settings.applyCertificate'),
              confirmText: t('settings.applyAndRestart')
            })
            if (apply) {
              try {
                await systemService.applyHttpsCert({ cert_id: imported.id })
                showSuccess(SUCCESS.HTTPS.APPLIED)
                setTimeout(() => window.location.reload(), 3000)
              } catch (error) {
                showError(error.message || ERRORS.HTTPS.APPLY_FAILED)
              }
            }
          } else {
            // Refresh cert list
            loadCertificates()
            showSuccess(t('common.importSuccess'))
          }
        }}
        defaultType="certificate"
      />
    </>
  )
}
