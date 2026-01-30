/**
 * Settings Page - Uses PageLayout with FocusPanel for category navigation
 */
import { useState, useEffect } from 'react'
import { 
  Gear, EnvelopeSimple, ShieldCheck, Database, ListBullets, FloppyDisk, 
  Envelope, Download, Trash, HardDrives, Lock, Key 
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, Input, Select, Badge, Card,
  LoadingSpinner, FileUpload, Modal, HelpCard
} from '../components'
import { settingsService, systemService, casService, certificatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'

// Settings categories with icons
const SETTINGS_CATEGORIES = [
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
  
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState({})
  const [backups, setBackups] = useState([])
  const [dbStats, setDbStats] = useState(null)
  const [httpsInfo, setHttpsInfo] = useState(null)
  const [certificates, setCertificates] = useState([])
  const [selectedHttpsCert, setSelectedHttpsCert] = useState('')
  const [cas, setCas] = useState([])
  
  // Selected category
  const [selectedCategory, setSelectedCategory] = useState('general')
  
  // Backup modal states
  const [showBackupModal, setShowBackupModal] = useState(false)
  const [showRestoreModal, setShowRestoreModal] = useState(false)
  const [backupPassword, setBackupPassword] = useState('')
  const [restorePassword, setRestorePassword] = useState('')
  const [restoreFile, setRestoreFile] = useState(null)
  const [backupLoading, setBackupLoading] = useState(false)

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
          <div className="space-y-6 max-w-2xl">
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">General Settings</h3>
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
            </div>
            <div className="flex gap-3 pt-4 border-t border-border">
              {canWrite('settings') && (
                <Button size="sm" onClick={() => handleSave('general')} disabled={saving}>
                  <FloppyDisk size={16} />
                  Save Changes
                </Button>
              )}
            </div>
          </div>
        )

      case 'email':
        return (
          <div className="space-y-6 max-w-2xl">
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Email Settings</h3>
              <div className="space-y-4">
                <Input
                  label="SMTP Host"
                  value={settings.smtp_host || ''}
                  onChange={(e) => updateSetting('smtp_host', e.target.value)}
                  placeholder="smtp.example.com"
                />
                <Input
                  label="SMTP Port"
                  type="number"
                  value={settings.smtp_port || 587}
                  onChange={(e) => updateSetting('smtp_port', parseInt(e.target.value))}
                />
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
            </div>
            <div className="flex gap-3 pt-4 border-t border-border">
              {canWrite('settings') && (
                <>
                  <Button size="sm" onClick={() => handleSave('email')} disabled={saving}>
                    <FloppyDisk size={16} />
                    Save Changes
                  </Button>
                  <Button size="sm" variant="secondary" onClick={handleTestEmail}>
                    <Envelope size={16} />
                    Send Test Email
                  </Button>
                </>
              )}
            </div>
          </div>
        )

      case 'security':
        return (
          <div className="space-y-6 max-w-2xl">
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Security Settings</h3>
              <div className="space-y-4">
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

                <div>
                  <p className="text-sm font-medium text-text-primary mb-2">Password Policy</p>
                  <div className="space-y-2">
                    <Input
                      label="Minimum Password Length"
                      type="number"
                      value={settings.min_password_length || 8}
                      onChange={(e) => updateSetting('min_password_length', parseInt(e.target.value))}
                      min="6"
                      max="32"
                    />
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

                <Input
                  label="Session Duration (hours)"
                  type="number"
                  value={settings.session_duration || 24}
                  onChange={(e) => updateSetting('session_duration', parseInt(e.target.value))}
                  min="1"
                  max="720"
                />

                <Input
                  label="API Rate Limit (requests/minute)"
                  type="number"
                  value={settings.api_rate_limit || 60}
                  onChange={(e) => updateSetting('api_rate_limit', parseInt(e.target.value))}
                  min="10"
                  max="1000"
                />
              </div>
            </div>
            <div className="flex gap-3 pt-4 border-t border-border">
              {hasPermission('admin:system') && (
                <Button size="sm" onClick={() => handleSave('security')} disabled={saving}>
                  <FloppyDisk size={16} />
                  Save Changes
                </Button>
              )}
            </div>
          </div>
        )

      case 'backup':
        return (
          <div className="space-y-6 max-w-2xl">
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Automatic Backups</h3>
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
                  <Button size="sm" onClick={() => handleSave('backup')} disabled={saving} className="mt-4">
                    <FloppyDisk size={16} />
                    Save Settings
                  </Button>
                )}
              </div>
            </div>

            <div className="border-t border-border pt-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Manual Backup</h3>
                  <p className="text-xs text-text-secondary">Create an encrypted backup file containing all data</p>
                </div>
                {hasPermission('admin:system') && (
                  <Button size="sm" onClick={() => setShowBackupModal(true)}>
                    <Database size={16} />
                    Create Backup
                  </Button>
                )}
              </div>

              {backups.length === 0 ? (
                <div className="p-8 bg-bg-tertiary border border-border rounded-lg text-center">
                  <p className="text-sm text-text-secondary">No backups found</p>
                  <p className="text-xs text-text-tertiary mt-1">Create a backup to protect your data</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {backups.map((backup) => (
                    <div key={backup.filename} className="flex items-center justify-between p-3 bg-bg-tertiary border border-border rounded-sm">
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
            </div>

            <div className="border-t border-border pt-6">
              <h3 className="text-sm font-semibold text-text-primary mb-2">Restore from Backup</h3>
              <p className="text-xs text-text-secondary mb-4">Upload a .ucmbkp file to restore all data</p>
              <FileUpload
                accept=".ucmbkp,.tar.gz"
                onFileSelect={(file) => { setRestoreFile(file); setShowRestoreModal(true) }}
                helperText="Select backup file (encrypted .ucmbkp)"
              />
            </div>
          </div>
        )

      case 'audit':
        return (
          <div className="space-y-6 max-w-2xl">
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Audit Log Settings</h3>
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

                <div>
                  <p className="text-sm font-medium text-text-primary mb-2">Events to Log</p>
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
                </div>
              </div>
            </div>
            <div className="flex gap-3 pt-4 border-t border-border">
              {hasPermission('admin:system') && (
                <Button size="sm" onClick={() => handleSave('audit')} disabled={saving}>
                  <FloppyDisk size={16} />
                  Save Changes
                </Button>
              )}
            </div>
          </div>
        )

      case 'database':
        return (
          <div className="space-y-6 max-w-2xl">
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Database Management</h3>
              
              <div className="p-4 bg-bg-tertiary border border-border rounded-sm mb-4">
                <h4 className="text-xs font-semibold text-text-primary uppercase mb-3">Database Statistics</h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-text-secondary text-xs">Total Certificates</p>
                    <p className="text-text-primary font-semibold">{dbStats?.certificates || '-'}</p>
                  </div>
                  <div>
                    <p className="text-text-secondary text-xs">Certificate Authorities</p>
                    <p className="text-text-primary font-semibold">{dbStats?.cas || '-'}</p>
                  </div>
                  <div>
                    <p className="text-text-secondary text-xs">Database Size</p>
                    <p className="text-text-primary font-semibold">{dbStats?.size || '-'}</p>
                  </div>
                  <div>
                    <p className="text-text-secondary text-xs">Last Optimized</p>
                    <p className="text-text-primary font-semibold">{dbStats?.last_optimized || '-'}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex gap-3">
                  <Button size="sm" variant="secondary" onClick={handleOptimizeDb}>
                    <Database size={16} />
                    Optimize Database
                  </Button>
                  <Button variant="secondary" onClick={handleIntegrityCheck}>
                    <ShieldCheck size={16} />
                    Integrity Check
                  </Button>
                </div>

                <div className="flex gap-3">
                  <Button variant="secondary" onClick={handleExportDb}>
                    <Download size={16} />
                    Export Database
                  </Button>
                </div>

                <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-sm">
                  <h4 className="text-sm font-semibold text-red-400 mb-2">⚠️ Danger Zone</h4>
                  <p className="text-xs text-text-secondary mb-3">
                    Reset database to initial state. This will DELETE ALL certificates, CAs, users, and settings.
                  </p>
                  <Button variant="danger" onClick={handleResetDb}>
                    <Trash size={16} />
                    Reset Database
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )

      case 'https':
        return (
          <div className="space-y-6 max-w-2xl">
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">HTTPS Certificate Management</h3>
              
              <div className="p-4 bg-bg-tertiary border border-border rounded-sm mb-4">
                <h4 className="text-xs font-semibold text-text-primary uppercase mb-3">Current Certificate</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Common Name:</span>
                    <span className="text-text-primary font-medium">{httpsInfo?.common_name || window.location.hostname}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Issuer:</span>
                    <span className="text-text-primary font-medium">{httpsInfo?.issuer || '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Type:</span>
                    <Badge variant={httpsInfo?.type === 'CA-Signed' ? 'success' : httpsInfo?.type === 'Self-Signed' ? 'warning' : 'secondary'}>
                      {httpsInfo?.type || '-'}
                    </Badge>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Valid From:</span>
                    <span className="text-text-primary font-medium">{formatDate(httpsInfo?.valid_from)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Valid Until:</span>
                    <span className="text-text-primary font-medium">{formatDate(httpsInfo?.valid_to)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Fingerprint (SHA256):</span>
                    <span className="text-text-primary font-mono text-xs">{httpsInfo?.fingerprint || '-'}</span>
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <div className="p-4 bg-bg-tertiary border border-border rounded-sm">
                  <h4 className="text-sm font-medium text-text-primary mb-2">Use UCM Certificate</h4>
                  <p className="text-xs text-text-secondary mb-3">
                    Apply an existing certificate from UCM as the HTTPS certificate. Only valid certificates with private keys are shown.
                  </p>
                  <div className="space-y-3">
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
                      onClick={handleApplyUcmCert}
                      disabled={!selectedHttpsCert}
                    >
                      <ShieldCheck size={16} />
                      Apply Selected Certificate
                    </Button>
                  </div>
                </div>

                <div>
                  <h4 className="text-sm font-medium text-text-primary mb-2">Regenerate Certificate</h4>
                  <p className="text-xs text-text-secondary mb-3">
                    Generate a new self-signed HTTPS certificate. The server will restart automatically.
                  </p>
                  <Button variant="secondary" onClick={handleRegenerateHttpsCert}>
                    <Key size={16} />
                    Regenerate Self-Signed Certificate
                  </Button>
                </div>

                <div className="p-4 bg-bg-tertiary border border-border rounded-sm">
                  <h4 className="text-sm font-medium text-text-primary mb-2">Apply Custom Certificate</h4>
                  <p className="text-xs text-text-secondary mb-3">
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
              </div>
            </div>
          </div>
        )

      default:
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
          onClick={() => setSelectedCategory(category.id)}
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
        <div className="p-6">
          {renderCategoryContent()}
        </div>
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
