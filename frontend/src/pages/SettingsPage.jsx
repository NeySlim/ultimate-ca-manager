/**
 * Settings Page - Uses PageLayout with FocusPanel for category navigation
 * Migrated to use DetailCard design system
 * 
 * Pro features (SSO) are dynamically added when Pro module is present
 */
import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  Gear, EnvelopeSimple, ShieldCheck, Database, ListBullets, FloppyDisk, 
  Envelope, Download, Trash, HardDrives, Lock, Key 
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, Input, Select, Badge, Card,
  LoadingSpinner, FileUpload, Modal, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent
} from '../components'
import { settingsService, systemService, casService, certificatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'

// Base settings categories (Community)
const BASE_SETTINGS_CATEGORIES = [
  { id: 'general', label: 'General', icon: Gear, description: 'System name, URL, timezone' },
  { id: 'email', label: 'Email', icon: EnvelopeSimple, description: 'SMTP configuration' },
  { id: 'security', label: 'Security', icon: ShieldCheck, description: 'Password, 2FA, sessions' },
  { id: 'backup', label: 'Backup', icon: Database, description: 'Backup & restore' },
  { id: 'audit', label: 'Audit Log', icon: ListBullets, description: 'Logging settings' },
  { id: 'database', label: 'Database', icon: HardDrives, description: 'Database management' },
  { id: 'https', label: 'HTTPS', icon: Lock, description: 'Certificate management' },
]

export default function SettingsPage() {
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
  
  // Pro settings categories (dynamically loaded)
  const [proCategories, setProCategories] = useState([])
  
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

  // Dynamically load Pro settings categories
  useEffect(() => {
    import('../pro/settings')
      .then(module => setProCategories(module.proSettingsCategories || []))
      .catch(() => {}) // Pro module not available - Community edition
  }, [])

  // Merge base + Pro categories
  const SETTINGS_CATEGORIES = useMemo(() => [
    ...BASE_SETTINGS_CATEGORIES.slice(0, 4), // general, email, security, backup
    ...proCategories,                         // SSO (Pro) - empty in Community
    ...BASE_SETTINGS_CATEGORIES.slice(4),     // audit, database, https
  ], [proCategories])

  useEffect(() => {
    loadSettings()
    loadBackups()
    loadHttpsInfo()
    loadCAs()
    loadCertificates()
  }, [])

  const loadSettings = async () => {
    setLoading(true)
    try {
      const response = await settingsService.getAll()
      setSettings(response.data || response || {})
    } catch (error) {
      showError(error.message || 'Failed to load settings')
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
      showSuccess('Settings saved successfully')
    } catch (error) {
      showError(error.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const handleTestEmail = async () => {
    try {
      await settingsService.testEmail(settings.admin_email)
      showSuccess('Test email sent successfully')
    } catch (error) {
      showError(error.message || 'Failed to send test email')
    }
  }

  const handleBackup = async () => {
    if (!backupPassword || backupPassword.length < 12) {
      showError('Password must be at least 12 characters')
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
        showSuccess('Backup created and downloaded successfully')
        setShowBackupModal(false)
        setBackupPassword('')
        loadBackups()
      }
    } catch (error) {
      showError(error.message || 'Failed to create backup')
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
      showSuccess('Backup downloaded successfully')
    } catch (error) {
      showError(error.message || 'Failed to download backup')
    }
  }

  const handleDeleteBackup = async (filename) => {
    const confirmed = await showConfirm(`Delete backup "${filename}"?`, {
      title: 'Delete Backup',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await systemService.deleteBackup(filename)
      showSuccess('Backup deleted successfully')
      loadBackups()
    } catch (error) {
      showError(error.message || 'Failed to delete backup')
    }
  }

  const handleRestoreBackup = async () => {
    if (!restoreFile) {
      showError('Please select a backup file')
      return
    }
    if (!restorePassword || restorePassword.length < 12) {
      showError('Password must be at least 12 characters')
      return
    }
    
    setBackupLoading(true)
    try {
      const result = await systemService.restore(restoreFile, restorePassword)
      showSuccess(`Backup restored successfully: ${result.data?.users || 0} users, ${result.data?.cas || 0} CAs, ${result.data?.certificates || 0} certificates`)
      setShowRestoreModal(false)
      setRestorePassword('')
      setRestoreFile(null)
      setTimeout(() => window.location.reload(), 2000)
    } catch (error) {
      showError(error.message || 'Failed to restore backup')
    } finally {
      setBackupLoading(false)
    }
  }

  const handleOptimizeDb = async () => {
    try {
      await systemService.optimizeDatabase()
      showSuccess('Database optimized successfully')
    } catch (error) {
      showError(error.message || 'Failed to optimize database')
    }
  }

  const handleIntegrityCheck = async () => {
    try {
      const result = await systemService.integrityCheck()
      if (result.passed) {
        showSuccess('Database integrity check passed')
      } else {
        showError(`Integrity check found ${result.errors} errors`)
      }
    } catch (error) {
      showError(error.message || 'Failed to check database integrity')
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
      showSuccess('Database exported successfully')
    } catch (error) {
      showError(error.message || 'Failed to export database')
    }
  }

  const handleResetDb = async () => {
    const confirmed1 = await showConfirm('⚠️ WARNING: This will DELETE ALL DATA and reset the database to initial state. Are you absolutely sure?', {
      title: 'Reset Database',
      confirmText: 'Continue',
      variant: 'danger'
    })
    if (!confirmed1) return

    const confirmation = await showPrompt('Type YES to confirm database reset:', {
      title: 'Final Confirmation',
      placeholder: 'YES'
    })
    if (confirmation !== 'YES') {
      showError('Database reset cancelled')
      return
    }

    try {
      await systemService.resetDatabase()
      showSuccess('Database reset successfully. Page will reload.')
      setTimeout(() => window.location.reload(), 2000)
    } catch (error) {
      showError(error.message || 'Failed to reset database')
    }
  }

  const handleApplyUcmCert = async () => {
    if (!selectedHttpsCert) {
      showError('Please select a certificate')
      return
    }

    const confirmed = await showConfirm('Apply selected certificate as HTTPS certificate? This will restart the server.', {
      title: 'Apply Certificate',
      confirmText: 'Apply & Restart'
    })
    if (!confirmed) return
    
    try {
      await systemService.applyHttpsCert({
        cert_id: selectedHttpsCert
      })
      showSuccess('HTTPS certificate applied. Server will restart.')
      setTimeout(() => window.location.reload(), 3000)
    } catch (error) {
      showError(error.message || 'Failed to apply certificate')
    }
  }

  const handleRegenerateHttpsCert = async () => {
    const confirmed = await showConfirm('Regenerate HTTPS certificate? This will restart the server.', {
      title: 'Regenerate Certificate',
      confirmText: 'Regenerate & Restart'
    })
    if (!confirmed) return
    
    try {
      await systemService.regenerateHttpsCert({
        common_name: window.location.hostname,
        validity_days: 365
      })
      showSuccess('HTTPS certificate regenerated. Server will restart.')
      setTimeout(() => window.location.reload(), 3000)
    } catch (error) {
      showError(error.message || 'Failed to regenerate HTTPS certificate')
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
            <DetailHeader
              icon={Gear}
              title="General Settings"
              subtitle="System name, URL, timezone configuration"
              actions={canWrite('settings') ? [
                { label: 'Save Changes', icon: FloppyDisk, onClick: () => handleSave('general'), disabled: saving }
              ] : []}
            />
            <DetailSection title="System Configuration">
              <div className="space-y-4">
                <Input
                  label="System Name"
                  value={settings.system_name || ''}
                  onChange={(e) => updateSetting('system_name', e.target.value)}
                  helperText="Display name for the UCM system"
                />
                <Input
                  label="Base URL"
                  value={settings.base_url || ''}
                  onChange={(e) => updateSetting('base_url', e.target.value)}
                  placeholder="https://ucm.example.com"
                  helperText="Public URL of this UCM instance"
                />
              </div>
            </DetailSection>
            <DetailSection title="Session & Timezone">
              <div className="space-y-4">
                <Input
                  label="Session Timeout (minutes)"
                  type="number"
                  value={settings.session_timeout || 30}
                  onChange={(e) => updateSetting('session_timeout', parseInt(e.target.value))}
                  min="5"
                  max="1440"
                />
                <Select
                  label="Timezone"
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

      case 'email':
        return (
          <DetailContent>
            <DetailHeader
              icon={EnvelopeSimple}
              title="Email Settings"
              subtitle="SMTP server configuration for notifications"
              actions={canWrite('settings') ? [
                { label: 'Test Email', icon: Envelope, onClick: handleTestEmail, variant: 'secondary' },
                { label: 'Save Changes', icon: FloppyDisk, onClick: () => handleSave('email'), disabled: saving }
              ] : []}
            />
            <DetailSection title="SMTP Server">
              <DetailGrid columns={2}>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label="SMTP Host"
                    value={settings.smtp_host || ''}
                    onChange={(e) => updateSetting('smtp_host', e.target.value)}
                    placeholder="smtp.example.com"
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label="SMTP Port"
                    type="number"
                    value={settings.smtp_port || 587}
                    onChange={(e) => updateSetting('smtp_port', parseInt(e.target.value))}
                  />
                </div>
              </DetailGrid>
            </DetailSection>
            <DetailSection title="Authentication">
              <div className="space-y-4">
                <Input
                  label="SMTP Username"
                  value={settings.smtp_username || ''}
                  onChange={(e) => updateSetting('smtp_username', e.target.value)}
                />
                <Input
                  label="SMTP Password"
                  type="password"
                  value={settings.smtp_password || ''}
                  onChange={(e) => updateSetting('smtp_password', e.target.value)}
                  placeholder="••••••••"
                />
              </div>
            </DetailSection>
            <DetailSection title="Email Options">
              <div className="space-y-4">
                <Input
                  label="From Email"
                  type="email"
                  value={settings.smtp_from_email || ''}
                  onChange={(e) => updateSetting('smtp_from_email', e.target.value)}
                  placeholder="noreply@example.com"
                />
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.smtp_use_tls || false}
                    onChange={(e) => updateSetting('smtp_use_tls', e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                  <span className="text-sm text-text-primary">Use TLS/STARTTLS</span>
                </label>
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'security':
        return (
          <DetailContent>
            <DetailHeader
              icon={ShieldCheck}
              title="Security Settings"
              subtitle="Password, 2FA, sessions configuration"
              actions={hasPermission('admin:system') ? [
                { label: 'Save Changes', icon: FloppyDisk, onClick: () => handleSave('security'), disabled: saving }
              ] : []}
            />
            <DetailSection title="Two-Factor Authentication">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.enforce_2fa || false}
                  onChange={(e) => updateSetting('enforce_2fa', e.target.checked)}
                  className="rounded border-border bg-bg-tertiary"
                />
                <div>
                  <p className="text-sm text-text-primary font-medium">Enforce Two-Factor Authentication</p>
                  <p className="text-xs text-text-secondary">Require all users to enable 2FA</p>
                </div>
              </label>
            </DetailSection>
            <DetailSection title="Password Policy">
              <div className="space-y-4">
                <Input
                  label="Minimum Password Length"
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
                    <span className="text-sm text-text-primary">Require uppercase letters</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.password_require_numbers || false}
                      onChange={(e) => updateSetting('password_require_numbers', e.target.checked)}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">Require numbers</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.password_require_special || false}
                      onChange={(e) => updateSetting('password_require_special', e.target.checked)}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">Require special characters</span>
                  </label>
                </div>
              </div>
            </DetailSection>
            <DetailSection title="Session & Rate Limits">
              <DetailGrid columns={2}>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label="Session Duration (hours)"
                    type="number"
                    value={settings.session_duration || 24}
                    onChange={(e) => updateSetting('session_duration', parseInt(e.target.value))}
                    min="1"
                    max="720"
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label="API Rate Limit (requests/minute)"
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
            <DetailHeader
              icon={Database}
              title="Backup & Restore"
              subtitle="Data backup and recovery options"
              actions={hasPermission('admin:system') ? [
                { label: 'Create Backup', icon: Database, onClick: () => setShowBackupModal(true) }
              ] : []}
            />
            <DetailSection title="Automatic Backups">
              <div className="space-y-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.auto_backup_enabled || false}
                    onChange={(e) => updateSetting('auto_backup_enabled', e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                  <div>
                    <p className="text-sm text-text-primary font-medium">Enable Automatic Backups</p>
                    <p className="text-xs text-text-secondary">Daily encrypted backups saved to /opt/ucm/data/backups</p>
                  </div>
                </label>

                {settings.auto_backup_enabled && (
                  <>
                    <Select
                      label="Backup Frequency"
                      options={[
                        { value: 'daily', label: 'Daily' },
                        { value: 'weekly', label: 'Weekly' },
                        { value: 'monthly', label: 'Monthly' },
                      ]}
                      value={settings.backup_frequency || 'daily'}
                      onChange={(val) => updateSetting('backup_frequency', val)}
                    />
                    <Input
                      label="Auto-Backup Password"
                      type="password"
                      value={settings.backup_password || ''}
                      onChange={(e) => updateSetting('backup_password', e.target.value)}
                      placeholder="Min 12 characters"
                      helperText="Password used to encrypt automatic backups"
                    />
                    <Input
                      label="Retention Period (days)"
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
                    Save Settings
                  </Button>
                )}
              </div>
            </DetailSection>

            <DetailSection title="Available Backups">
              {backups.length === 0 ? (
                <div className="p-6 text-center">
                  <p className="text-sm text-text-secondary">No backups found</p>
                  <p className="text-xs text-text-tertiary mt-1">Create a backup to protect your data</p>
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

            <DetailSection title="Restore from Backup">
              <div>
                <p className="text-xs text-text-secondary mb-4">Upload a .ucmbkp file to restore all data</p>
                <FileUpload
                  accept=".ucmbkp,.tar.gz"
                  onFileSelect={(file) => { setRestoreFile(file); setShowRestoreModal(true) }}
                  helperText="Select backup file (encrypted .ucmbkp)"
                />
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'audit':
        return (
          <DetailContent>
            <DetailHeader
              icon={ListBullets}
              title="Audit Log Settings"
              subtitle="Logging configuration and retention"
              actions={hasPermission('admin:system') ? [
                { label: 'Save Changes', icon: FloppyDisk, onClick: () => handleSave('audit'), disabled: saving }
              ] : []}
            />
            <DetailSection title="Audit Logging">
              <div className="space-y-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.audit_enabled || true}
                    onChange={(e) => updateSetting('audit_enabled', e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                  <div>
                    <p className="text-sm text-text-primary font-medium">Enable Audit Logging</p>
                    <p className="text-xs text-text-secondary">Log all system activities</p>
                  </div>
                </label>

                <Input
                  label="Log Retention (days)"
                  type="number"
                  value={settings.audit_retention_days || 90}
                  onChange={(e) => updateSetting('audit_retention_days', parseInt(e.target.value))}
                  min="7"
                  max="730"
                  disabled={!settings.audit_enabled}
                />
              </div>
            </DetailSection>
            <DetailSection title="Events to Log">
              <div className="space-y-2">
                {[
                  'User Login/Logout',
                  'Certificate Issue/Revoke',
                  'CA Create/Delete',
                  'Settings Changes',
                  'User Management',
                ].map(event => (
                  <label key={event} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={true}
                      disabled={!settings.audit_enabled}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{event}</span>
                  </label>
                ))}
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'database':
        return (
          <DetailContent>
            <DetailHeader
              icon={HardDrives}
              title="Database Management"
              subtitle="Database statistics and maintenance"
            />
            <DetailSection title="Database Statistics">
              <DetailGrid columns={2}>
                <DetailField
                  label="Total Certificates"
                  value={dbStats?.certificates || '-'}
                />
                <DetailField
                  label="Certificate Authorities"
                  value={dbStats?.cas || '-'}
                />
                <DetailField
                  label="Database Size"
                  value={dbStats?.size || '-'}
                />
                <DetailField
                  label="Last Optimized"
                  value={dbStats?.last_optimized || '-'}
                />
              </DetailGrid>
            </DetailSection>

            <DetailSection title="Maintenance">
              <div className="space-y-3">
                <div className="flex flex-wrap gap-3">
                  <Button size="sm" variant="secondary" onClick={handleOptimizeDb}>
                    <Database size={16} />
                    Optimize Database
                  </Button>
                  <Button size="sm" variant="secondary" onClick={handleIntegrityCheck}>
                    <ShieldCheck size={16} />
                    Integrity Check
                  </Button>
                  <Button size="sm" variant="secondary" onClick={handleExportDb}>
                    <Download size={16} />
                    Export Database
                  </Button>
                </div>
              </div>
            </DetailSection>

            <DetailSection title="Danger Zone" className="mt-4">
              <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                <h4 className="text-sm font-semibold text-red-400 mb-2">⚠️ Database Reset</h4>
                <p className="text-xs text-text-secondary mb-3">
                  Reset database to initial state. This will DELETE ALL certificates, CAs, users, and settings.
                </p>
                <Button variant="danger" size="sm" onClick={handleResetDb}>
                  <Trash size={16} />
                  Reset Database
                </Button>
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'https':
        return (
          <DetailContent>
            <DetailHeader
              icon={Lock}
              title="HTTPS Certificate Management"
              subtitle="SSL/TLS certificate for secure connections"
              badge={httpsInfo?.type && (
                <Badge variant={httpsInfo?.type === 'CA-Signed' ? 'success' : httpsInfo?.type === 'Self-Signed' ? 'warning' : 'secondary'}>
                  {httpsInfo?.type}
                </Badge>
              )}
            />
            <DetailSection title="Current Certificate">
              <DetailGrid columns={2}>
                <DetailField
                  label="Common Name"
                  value={httpsInfo?.common_name || window.location.hostname}
                />
                <DetailField
                  label="Issuer"
                  value={httpsInfo?.issuer || '-'}
                />
                <DetailField
                  label="Valid From"
                  value={formatDate(httpsInfo?.valid_from)}
                />
                <DetailField
                  label="Valid Until"
                  value={formatDate(httpsInfo?.valid_to)}
                />
                <DetailField
                  label="Fingerprint (SHA256)"
                  value={httpsInfo?.fingerprint || '-'}
                  mono
                  copyable
                  fullWidth
                />
              </DetailGrid>
            </DetailSection>

            <DetailSection title="Use UCM Certificate">
              <div className="space-y-4">
                <p className="text-xs text-text-secondary">
                  Apply an existing certificate from UCM as the HTTPS certificate. Only valid certificates with private keys are shown.
                </p>
                <Select
                  label="Select Certificate"
                  value={selectedHttpsCert}
                  onChange={setSelectedHttpsCert}
                  placeholder="Choose a certificate..."
                  options={certificates.map(cert => ({
                    value: cert.id,
                    label: `${cert.common_name || 'Certificate'} (expires ${formatDate(cert.valid_to)})`
                  }))}
                />
                {certificates.length === 0 && (
                  <p className="text-xs text-text-secondary">
                    No valid certificates with private keys found. Issue a certificate first.
                  </p>
                )}
                <Button 
                  variant="secondary" 
                  size="sm"
                  onClick={handleApplyUcmCert}
                  disabled={!selectedHttpsCert}
                >
                  <ShieldCheck size={16} />
                  Apply Selected Certificate
                </Button>
              </div>
            </DetailSection>

            <DetailSection title="Regenerate Certificate">
              <div className="space-y-3">
                <p className="text-xs text-text-secondary">
                  Generate a new self-signed HTTPS certificate. The server will restart automatically.
                </p>
                <Button variant="secondary" size="sm" onClick={handleRegenerateHttpsCert}>
                  <Key size={16} />
                  Regenerate Self-Signed Certificate
                </Button>
              </div>
            </DetailSection>

            <DetailSection title="Apply Custom Certificate">
              <div className="space-y-3">
                <p className="text-xs text-text-secondary">
                  Upload your own certificate and private key (PEM format).
                </p>
                <FileUpload
                  accept=".pem,.crt,.key"
                  onFileSelect={(file) => {
                    showError('Feature coming soon: Upload custom HTTPS certificate')
                  }}
                  helperText="Select certificate or key file (PEM format)"
                />
              </div>
            </DetailSection>
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
      <HelpCard variant="info" title="General Settings">
        Configure your UCM instance name, base URL, session timeout, and timezone.
        These settings affect all users and system behavior.
      </HelpCard>
      
      <HelpCard variant="tip" title="Email Configuration">
        Configure SMTP settings to enable email notifications for certificate
        expiration alerts and system events. Test your configuration before saving.
      </HelpCard>

      <HelpCard variant="warning" title="Security Settings">
        Security settings like 2FA enforcement and password policies affect all users.
        Changes take effect immediately - users may need to update their credentials.
      </HelpCard>

      <HelpCard variant="info" title="Backup & Restore">
        Create encrypted backups of all data including certificates, CAs, users, 
        and settings. Store backup passwords securely - they cannot be recovered.
      </HelpCard>

      <HelpCard variant="tip" title="Database Management">
        Optimize database performance, check integrity, or export data.
        The danger zone allows complete database reset - use with extreme caution.
      </HelpCard>

      <HelpCard variant="info" title="HTTPS Certificate">
        Manage the SSL/TLS certificate used by UCM. You can use a certificate
        from your PKI or generate a self-signed certificate for testing.
      </HelpCard>
    </div>
  )

  // Focus panel content (category list)
  const focusContent = (
    <div className="p-2 space-y-1.5">
      {SETTINGS_CATEGORIES.map((category) => (
        <FocusItem
          key={category.id}
          icon={category.icon}
          title={category.label}
          subtitle={category.description}
          selected={selectedCategory === category.id}
          onClick={() => handleCategoryChange(category.id)}
          badge={category.pro ? <Badge variant="info" size="sm">Pro</Badge> : null}
        />
      ))}
    </div>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message="Loading settings..." />
      </div>
    )
  }

  return (
    <>
      <PageLayout
        title="Settings"
        focusTitle="Settings"
        focusContent={focusContent}
        focusActions={null}
        focusFooter={null}
        helpContent={helpContent}
        helpTitle="Settings - Help"
      >
        {renderCategoryContent()}
      </PageLayout>

      {/* Backup Password Modal */}
      <Modal
        open={showBackupModal}
        onClose={() => { setShowBackupModal(false); setBackupPassword('') }}
        title="Create Encrypted Backup"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Create a backup containing all data (database, certificates, CAs, users, configuration).
            The backup will be encrypted with your password.
          </p>
          <Input
            label="Encryption Password"
            type="password"
            value={backupPassword}
            onChange={(e) => setBackupPassword(e.target.value)}
            placeholder="Minimum 12 characters"
            helperText="Use a strong password - you'll need it to restore the backup"
            autoFocus
          />
          <div className="flex gap-3 justify-end pt-4">
            <Button variant="secondary" onClick={() => { setShowBackupModal(false); setBackupPassword('') }}>
              Cancel
            </Button>
            <Button 
              onClick={handleBackup} 
              disabled={backupLoading || !backupPassword || backupPassword.length < 12}
            >
              {backupLoading ? 'Creating...' : 'Create & Download'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Restore Password Modal */}
      <Modal
        open={showRestoreModal}
        onClose={() => { setShowRestoreModal(false); setRestorePassword(''); setRestoreFile(null) }}
        title="Restore from Backup"
      >
        <div className="space-y-4">
          <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
            <p className="text-sm text-yellow-500 font-medium">⚠️ Warning</p>
            <p className="text-xs text-yellow-500/80">
              This will REPLACE ALL current data with the backup contents.
              This action cannot be undone.
            </p>
          </div>
          {restoreFile && (
            <p className="text-sm text-text-primary">
              File: <strong>{restoreFile.name}</strong>
            </p>
          )}
          <Input
            label="Backup Password"
            type="password"
            value={restorePassword}
            onChange={(e) => setRestorePassword(e.target.value)}
            placeholder="Enter the password used to create the backup"
            autoFocus
          />
          <div className="flex gap-3 justify-end pt-4">
            <Button variant="secondary" onClick={() => { setShowRestoreModal(false); setRestorePassword(''); setRestoreFile(null) }}>
              Cancel
            </Button>
            <Button 
              variant="danger"
              onClick={handleRestoreBackup} 
              disabled={backupLoading || !restorePassword || restorePassword.length < 12}
            >
              {backupLoading ? 'Restoring...' : 'Restore Backup'}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
