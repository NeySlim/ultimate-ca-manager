/**
 * Settings Page
 */
import { useState, useEffect } from 'react'
import { Gear, EnvelopeSimple, ShieldCheck, Database, ListBullets, FloppyDisk, Envelope, Download, Trash, UploadSimple, HardDrives, Lock } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Button, Input, Select,
  Textarea, Tabs, LoadingSpinner, FileUpload, Table
} from '../components'
import { settingsService, systemService, casService, certificatesService } from '../services'
import { useNotification } from '../contexts'

export default function SettingsPage() {
  const { showSuccess, showError } = useNotification()
  
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState({})
  const [backups, setBackups] = useState([])
  const [dbStats, setDbStats] = useState(null)
  const [httpsInfo, setHttpsInfo] = useState(null)
  const [certificates, setCertificates] = useState([])
  const [selectedHttpsCert, setSelectedHttpsCert] = useState('')
  const [cas, setCas] = useState([])

  useEffect(() => {
    loadSettings()
    // loadBackups() // TODO: Activer quand endpoint backend existe
    // loadDbStats() // TODO: Activer quand endpoint backend existe
    // loadHttpsInfo() // TODO: Activer quand endpoint backend existe
    loadCAs()
    loadCertificates()
  }, [])

  const loadSettings = async () => {
    setLoading(true)
    try {
      const data = await settingsService.getAll()
      setSettings(data)
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

  const loadDbStats = async () => {
    try {
      const data = await systemService.getDatabaseStats()
      setDbStats(data.data || {})
    } catch (error) {
      console.error('Failed to load database stats:', error)
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
      // Filter only certs with private keys (suitable for HTTPS)
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
    try {
      const blob = await systemService.backup()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ucm-backup-${new Date().toISOString().split('T')[0]}.tar.gz`
      a.click()
      showSuccess('Backup downloaded successfully')
      // await loadBackups() // TODO: Activer quand endpoint backend existe
    } catch (error) {
      showError(error.message || 'Failed to create backup')
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
      showSuccess('Backup downloaded successfully')
    } catch (error) {
      showError(error.message || 'Failed to download backup')
    }
  }

  const handleDeleteBackup = async (filename) => {
    if (!confirm(`Delete backup "${filename}"?`)) return
    
    try {
      await systemService.deleteBackup(filename)
      showSuccess('Backup deleted successfully')
      // await loadBackups() // TODO: Activer quand endpoint backend existe
    } catch (error) {
      showError(error.message || 'Failed to delete backup')
    }
  }

  const handleRestoreBackup = async (file) => {
    if (!confirm('Restore from backup? This will replace all current data!')) return
    
    try {
      await systemService.restore(file)
      showSuccess('Backup restored successfully. Page will reload.')
      setTimeout(() => window.location.reload(), 2000)
    } catch (error) {
      showError(error.message || 'Failed to restore backup')
    }
  }

  // Database Management Handlers
  const handleOptimizeDb = async () => {
    try {
      await systemService.optimizeDatabase()
      showSuccess('Database optimized successfully')
      // await loadDbStats() // Refresh stats
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
    if (!confirm('⚠️ WARNING: This will DELETE ALL DATA and reset the database to initial state. Are you absolutely sure?')) return
    if (!confirm('Last chance! Type YES in the next dialog to confirm')) return
    
    const confirmation = prompt('Type YES to confirm database reset:')
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

  // HTTPS Certificate Management Handlers
  const handleApplyUcmCert = async () => {
    if (!selectedHttpsCert) {
      showError('Please select a certificate')
      return
    }

    // TODO: Backend endpoint not implemented yet
    showError('HTTPS certificate management not yet implemented in backend')
    return

    /* Will be enabled when backend endpoint exists
    if (!confirm('Apply selected certificate as HTTPS certificate? This will restart the server.')) return
    
    try {
      await systemService.applyHttpsCert({
        certificate_id: selectedHttpsCert
      })
      showSuccess('HTTPS certificate applied. Server will restart.')
      setTimeout(() => window.location.reload(), 3000)
    } catch (error) {
      showError(error.message || 'Failed to apply certificate')
    }
    */
  }

  const handleRegenerateHttpsCert = async () => {
    // TODO: Backend endpoint not implemented yet
    showError('HTTPS certificate management not yet implemented in backend')
    return

    /* Will be enabled when backend endpoint exists
    if (!confirm('Regenerate HTTPS certificate? This will restart the server.')) return
    
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
    */
  }

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  const tabs = [
    {
      id: 'general',
      label: 'General',
      icon: <Gear size={16} />,
      content: (
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
            <Button onClick={() => handleSave('general')} disabled={saving}>
              <FloppyDisk size={16} />
              Save Changes
            </Button>
          </div>
        </div>
      )
    },
    {
      id: 'email',
      label: 'Email',
      icon: <EnvelopeSimple size={16} />,
      content: (
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
            <Button onClick={() => handleSave('email')} disabled={saving}>
              <FloppyDisk size={16} />
              Save Changes
            </Button>
            <Button variant="secondary" onClick={handleTestEmail}>
              <Envelope size={16} />
              Send Test Email
            </Button>
          </div>
        </div>
      )
    },
    {
      id: 'security',
      label: 'Security',
      icon: <ShieldCheck size={16} />,
      content: (
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
            <Button onClick={() => handleSave('security')} disabled={saving}>
              <FloppyDisk size={16} />
              Save Changes
            </Button>
          </div>
        </div>
      )
    },
    {
      id: 'backup',
      label: 'Backup',
      icon: <Database size={16} />,
      content: (
        <div className="space-y-6 max-w-2xl">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">Backup Settings</h3>
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
                  <p className="text-xs text-text-secondary">Automatically backup database and certificates</p>
                </div>
              </label>

              <Select
                label="Backup Frequency"
                options={[
                  { value: 'daily', label: 'Daily' },
                  { value: 'weekly', label: 'Weekly' },
                  { value: 'monthly', label: 'Monthly' },
                ]}
                value={settings.backup_frequency || 'daily'}
                onChange={(val) => updateSetting('backup_frequency', val)}
                disabled={!settings.auto_backup_enabled}
              />

              <Input
                label="Retention Period (days)"
                type="number"
                value={settings.backup_retention_days || 30}
                onChange={(e) => updateSetting('backup_retention_days', parseInt(e.target.value))}
                min="1"
                max="365"
                disabled={!settings.auto_backup_enabled}
              />
            </div>
          </div>

          <div className="border-t border-border pt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-text-primary">Backup Files</h3>
              <Button onClick={handleBackup}>
                <Database size={16} />
                Create Backup
              </Button>
            </div>

            {backups.length === 0 ? (
              <div className="p-8 bg-bg-tertiary border border-border rounded-lg text-center">
                <p className="text-sm text-text-secondary">No backups found</p>
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
                      <Button 
                        size="sm" 
                        variant="secondary" 
                        onClick={() => handleDownloadBackup(backup.filename)}
                      >
                        <Download size={14} />
                        Download
                      </Button>
                      <Button 
                        size="sm" 
                        variant="danger" 
                        onClick={() => handleDeleteBackup(backup.filename)}
                      >
                        <Trash size={14} />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-border pt-6">
            <h3 className="text-sm font-semibold text-text-primary mb-4">Restore from Backup</h3>
            <FileUpload
              accept=".tar.gz,.zip"
              onFileSelect={(file) => handleRestoreBackup(file)}
              helperText="Upload a backup file to restore the system. WARNING: This will replace all current data!"
            />
          </div>

          <div className="flex gap-3 pt-4 border-t border-border">
            <Button onClick={() => handleSave('backup')} disabled={saving}>
              <FloppyDisk size={16} />
              Save Changes
            </Button>
          </div>
        </div>
      )
    },
    {
      id: 'audit',
      label: 'Audit Log',
      icon: <ListBullets size={16} />,
      content: (
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
            <Button onClick={() => handleSave('audit')} disabled={saving}>
              <FloppyDisk size={16} />
              Save Changes
            </Button>
          </div>
        </div>
      )
    },
    {
      id: 'database',
      label: 'Database',
      icon: <HardDrives size={16} />,
      content: (
        <div className="space-y-6 max-w-2xl">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">Database Management</h3>
            
            {/* Stats placeholder - will show when endpoint available */}
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
                <Button variant="secondary" onClick={handleOptimizeDb}>
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
    },
    {
      id: 'https',
      label: 'HTTPS',
      icon: <Lock size={16} />,
      content: (
        <div className="space-y-6 max-w-2xl">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">HTTPS Certificate Management</h3>
            
            {/* Certificate info placeholder - will show when endpoint available */}
            <div className="p-4 bg-bg-tertiary border border-border rounded-sm mb-4">
              <h4 className="text-xs font-semibold text-text-primary uppercase mb-3">Current Certificate</h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-secondary">Common Name:</span>
                  <span className="text-text-primary font-medium">{httpsInfo?.common_name || window.location.hostname}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Issuer:</span>
                  <span className="text-text-primary font-medium">{httpsInfo?.issuer || 'Self-Signed'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Valid From:</span>
                  <span className="text-text-primary font-medium">{httpsInfo?.valid_from || '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Valid Until:</span>
                  <span className="text-text-primary font-medium">{httpsInfo?.valid_until || '-'}</span>
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
                      label: `${cert.common_name} (expires ${new Date(cert.valid_until).toLocaleDateString()})`
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
    },
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message="Loading settings..." />
      </div>
    )
  }

  return (
    <>
      <ExplorerPanel title="Settings">
        <div className="p-3 space-y-3">
          {/* System Status */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">System Status</h3>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">Service</span>
                <span className="text-green-500 font-medium">Running</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">Database</span>
                <span className="text-green-500 font-medium">Connected</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">Version</span>
                <span className="text-text-primary font-medium">1.0.0</span>
              </div>
            </div>
          </div>

          {/* Quick Help */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">Quick Help</h3>
            <div className="text-xs text-text-secondary space-y-1.5">
              <p>• General settings control core application behavior</p>
              <p>• Email settings require SMTP configuration</p>
              <p>• Security settings affect all users</p>
              <p>• Database settings require restart</p>
            </div>
          </div>

          {/* Actions */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wide">Actions</h3>
            <div className="space-y-1.5">
              <Button size="sm" variant="secondary" className="w-full justify-start">
                <Database size={14} />
                Backup Database
              </Button>
              <Button size="sm" variant="secondary" className="w-full justify-start">
                <ShieldCheck size={14} />
                Test Security
              </Button>
            </div>
          </div>
        </div>
      </ExplorerPanel>

      <DetailsPanel>
        <Tabs tabs={tabs} defaultTab="general" />
      </DetailsPanel>
    </>
  )
}
