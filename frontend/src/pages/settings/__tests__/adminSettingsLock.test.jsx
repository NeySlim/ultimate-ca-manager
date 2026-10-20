/**
 * Settings reserved to admin:settings: without it the field keeps its value
 * but is disabled (padlock beside a text or number label), and the cards keep
 * a save button for the fields write:settings may change.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, value, disabled }) => (
    <div data-field="">{label}<input readOnly value={value ?? ''} disabled={disabled} /></div>
  ),
  Textarea: ({ label, value, disabled }) => (
    <div data-field="">{label}<textarea readOnly value={value ?? ''} disabled={disabled} /></div>
  ),
  Select: ({ label, value, disabled }) => (
    <div data-field="">{label}<select value={value ?? ''} disabled={disabled} onChange={() => {}}><option value={value ?? ''} /></select></div>
  ),
  FileUpload: () => <div />,
  Badge: ({ children }) => <span>{children}</span>,
  LoadingSpinner: () => <span>loading</span>,
  ExperimentalBadge: () => <span>experimental</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  DetailGrid: ({ children }) => <div>{children}</div>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label, checked, disabled }) => (
    <button type="button" role="switch" aria-label={label} aria-checked={checked} disabled={disabled} />
  ),
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
vi.mock('../../../services', () => ({
  certificatesService: { getAll: vi.fn() },
  settingsService: { updateBulk: vi.fn() },
}))
vi.mock('../../../lib/fetchAllPages', () => ({ fetchAllPages: () => Promise.resolve([]) }))
vi.mock('../ServiceStatusWidget', () => ({ default: () => null }))
vi.mock('../PublicEndpointsPanel', () => ({ default: () => null }))

import GeneralSection from '../GeneralSection'
import SecuritySection from '../SecuritySection'
import BackupSection from '../BackupSection'
import AuditSection from '../AuditSection'

const OPERATOR = ['read:settings', 'write:settings']
const ADMIN = [...OPERATOR, 'admin:settings', 'admin:system']
const granting = (perms) => (p) => perms.includes(p)

// The field a label belongs to, its control and whether it shows a padlock
function field(labelKey) {
  const box = screen.getByText(labelKey).closest('[data-field]')
  return {
    control: box.querySelector('input, select, textarea'),
    locked: box.querySelector('[data-testid="admin-lock"]') !== null,
  }
}

const toggle = (labelKey) => screen.getByRole('switch', { name: labelKey })
const saveButtons = () => screen.queryAllByText('common.saveChanges')

describe('GeneralSection', () => {
  const settings = {
    system_name: 'PKI', base_url: 'https://pki.example.com',
    protocol_base_url: 'http://pki.example.com:8080', http_protocol_port: 8080,
    acme_public_vhost: 'acme.example.com', acme_public_port: 443, acme_public_tls_cert_id: 7,
    session_timeout: 3600, max_login_attempts: 5, lockout_duration: 900,
  }
  const MAIN_LOCKED = ['settings.baseUrl', 'settings.protocolBaseUrl', 'settings.acmePublicVhost',
    'settings.acmePublicPort', 'settings.acmePublicTlsCertId']
  const SESSION_LOCKED = ['settings.sessionTimeout', 'settings.maxLoginAttempts', 'settings.lockoutDuration']

  const renderGeneral = (props) => render(
    <GeneralSection settings={settings} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
      canWrite={() => true} {...props} />
  )

  it('locks the reserved fields for an operator and keeps their values', () => {
    renderGeneral({ hasPermission: granting(OPERATOR) })
    for (const key of [...MAIN_LOCKED, ...SESSION_LOCKED]) {
      expect(field(key).control.disabled, key).toBe(true)
      expect(field(key).locked, key).toBe(true)
    }
    expect(field('settings.baseUrl').control.value).toBe('https://pki.example.com')
    expect(field('settings.sessionTimeout').control.value).toBe('60')
    for (const key of ['settings.systemName', 'settings.httpProtocolPort', 'settings.timezone', 'settings.dateFormat']) {
      expect(field(key).control.disabled, key).toBeFalsy()
      expect(field(key).locked, key).toBe(false)
    }
    expect(screen.getByText('settings.adminFieldsLocked')).toBeInTheDocument()
  })

  it('keeps both save buttons for an operator', () => {
    const handleSave = vi.fn()
    renderGeneral({ hasPermission: granting(OPERATOR), handleSave })
    expect(saveButtons()).toHaveLength(2)
    fireEvent.click(saveButtons()[1])
    expect(handleSave).toHaveBeenCalledWith('general')
  })

  it('puts the notice under the main card save button', () => {
    renderGeneral({ hasPermission: granting(OPERATOR) })
    const notice = screen.getByText('settings.adminFieldsLocked')
    expect(notice.parentElement).toBe(saveButtons()[0].parentElement)
  })

  it('treats a missing hasPermission as no admin:settings', () => {
    renderGeneral({})
    expect(field('settings.baseUrl').control.disabled).toBe(true)
    expect(screen.getByText('settings.adminFieldsLocked')).toBeInTheDocument()
  })

  it('leaves everything open for a settings administrator', () => {
    renderGeneral({ hasPermission: granting(ADMIN) })
    for (const key of [...MAIN_LOCKED, ...SESSION_LOCKED]) {
      expect(field(key).control.disabled, key).toBeFalsy()
      expect(field(key).locked, key).toBe(false)
    }
    expect(screen.queryByText('settings.adminFieldsLocked')).not.toBeInTheDocument()
  })

  it('shows no notice to a user who cannot save', () => {
    renderGeneral({ hasPermission: () => false, canWrite: () => false })
    expect(saveButtons()).toHaveLength(0)
    expect(screen.queryByText('settings.adminFieldsLocked')).not.toBeInTheDocument()
  })
})

describe('SecuritySection', () => {
  const renderSecurity = (perms, settings = {}) => render(
    <SecuritySection
      settings={{ hsts_env_locked: [], hsts_enabled: true, hsts_max_age: 600,
        min_password_length: 12, session_max_lifetime: 7200, ...settings }}
      updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
      hasPermission={granting(perms)}
      encryptionStatus={null}
      anomalies={[]} anomaliesLoading={false} loadAnomalies={vi.fn()}
      mtlsSettings={{}} setMtlsSettings={vi.fn()} mtlsLoading={false} mtlsSaving={false}
      handleMtlsSave={vi.fn()} cas={[]}
    />
  )
  const LOCKED_SWITCHES = ['settings.enforce2fa', 'settings.hstsEnabled', 'settings.hstsIncludeSubdomains',
    'settings.ocspResponderAutoRenew', 'settings.crlAutoDeleteExpiredRevoked', 'settings.crlAutoPurgeStaleSerials',
    'settings.keyRecoveryDualControl', 'settings.requireUppercase', 'settings.requireNumbers', 'settings.requireSpecial']
  const LOCKED_FIELDS = ['settings.hstsMaxAge', 'settings.minPasswordLength', 'settings.sessionDuration']

  it('locks the reserved settings for an operator, values kept', () => {
    renderSecurity(OPERATOR)
    for (const key of LOCKED_SWITCHES) expect(toggle(key).disabled, key).toBe(true)
    for (const key of LOCKED_FIELDS) {
      expect(field(key).control.disabled, key).toBe(true)
      expect(field(key).locked, key).toBe(true)
    }
    expect(field('settings.hstsMaxAge').control.value).toBe('600')
    expect(field('settings.minPasswordLength').control.value).toBe('12')
    expect(field('settings.ocspResponseValidity').control.disabled).toBeFalsy()
    expect(field('settings.ocspResponseValidity').locked).toBe(false)
  })

  it('keeps the save buttons of the mixed cards only', () => {
    const handleSave = vi.fn()
    render(
      <SecuritySection
        settings={{ hsts_env_locked: [] }} updateSetting={vi.fn()} handleSave={handleSave} saving={false}
        hasPermission={granting(OPERATOR)} encryptionStatus={null}
        anomalies={[]} anomaliesLoading={false} loadAnomalies={vi.fn()}
        mtlsSettings={{}} setMtlsSettings={vi.fn()} mtlsLoading={false} mtlsSaving={false}
        handleMtlsSave={vi.fn()} cas={[]}
      />
    )
    saveButtons().forEach((b) => fireEvent.click(b))
    expect(handleSave.mock.calls.map((c) => c[0]).sort()).toEqual(['securityHsts', 'securitySession'])
  })

  it('gives a settings administrator every field and button', () => {
    const handleSave = vi.fn()
    render(
      <SecuritySection
        settings={{ hsts_env_locked: [] }} updateSetting={vi.fn()} handleSave={handleSave} saving={false}
        hasPermission={granting(['read:settings', 'write:settings', 'admin:settings'])} encryptionStatus={null}
        anomalies={[]} anomaliesLoading={false} loadAnomalies={vi.fn()}
        mtlsSettings={{}} setMtlsSettings={vi.fn()} mtlsLoading={false} mtlsSaving={false}
        handleMtlsSave={vi.fn()} cas={[]}
      />
    )
    for (const key of LOCKED_SWITCHES) expect(toggle(key).disabled, key).toBeFalsy()
    for (const key of LOCKED_FIELDS) expect(field(key).locked, key).toBe(false)
    saveButtons().forEach((b) => fireEvent.click(b))
    expect(handleSave.mock.calls.map((c) => c[0]).sort()).toEqual([
      'security2fa', 'securityAdminAllowlist', 'securityHsts', 'securityKeyRecovery',
      'securityPassword', 'securitySession'])
  })

  it('keeps the environment locks for an administrator', () => {
    renderSecurity(ADMIN, { hsts_env_locked: ['hsts_enabled'], key_recovery_dual_control_locked: true })
    expect(toggle('settings.hstsEnabled').disabled).toBe(true)
    expect(toggle('settings.hstsIncludeSubdomains').disabled).toBeFalsy()
    expect(toggle('settings.keyRecoveryDualControl').disabled).toBe(true)
  })
})

describe('BackupSection', () => {
  const renderBackup = (perms) => render(
    <BackupSection
      settings={{ auto_backup_enabled: true, backup_frequency: 'weekly', backup_retention_days: 14 }}
      updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
      hasPermission={granting(perms)} backups={[]}
      handleRunRetention={vi.fn()} setShowBackupModal={vi.fn()}
    />
  )

  it('locks the password only, and keeps the save and create buttons', () => {
    renderBackup(OPERATOR)
    expect(field('settings.autoBackupPassword').control.disabled).toBe(true)
    expect(field('settings.autoBackupPassword').locked).toBe(true)
    expect(toggle('settings.enableAutoBackups').disabled).toBeFalsy()
    expect(field('settings.backupFrequency').control.disabled).toBeFalsy()
    expect(field('settings.backupFrequency').control.value).toBe('weekly')
    const retention = screen.getAllByText('settings.retentionPeriod')
      .map((n) => n.closest('[data-field]')).find(Boolean).querySelector('input')
    expect(retention.disabled).toBeFalsy()
    expect(retention.value).toBe('14')
    expect(screen.getAllByText('settings.saveSettings')).toHaveLength(2)
    expect(screen.getByText('settings.createBackup')).toBeInTheDocument()
    expect(screen.queryByText('settings.backupCleanupNow')).not.toBeInTheDocument()
  })

  it('offers the immediate purge with admin:system', () => {
    renderBackup([...OPERATOR, 'admin:system'])
    expect(screen.getByText('settings.backupCleanupNow')).toBeInTheDocument()
    expect(field('settings.autoBackupPassword').control.disabled).toBe(true)
  })

  it('opens the password to a settings administrator', () => {
    renderBackup(ADMIN)
    expect(field('settings.autoBackupPassword').control.disabled).toBeFalsy()
    expect(field('settings.autoBackupPassword').locked).toBe(false)
  })
})

describe('AuditSection', () => {
  const renderAudit = (perms) => render(
    <AuditSection
      settings={{ audit_retention_days: 90 }} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
      hasPermission={granting(perms)}
      syslogConfig={{ enabled: false, host: '', port: 514, categories: [] }}
      updateSyslogConfig={vi.fn()} syslogSaving={false} syslogTesting={false}
      handleSaveSyslog={vi.fn()} handleTestSyslog={vi.fn()}
    />
  )

  it('keeps the save button for write:settings, retention locked', () => {
    renderAudit(OPERATOR)
    expect(saveButtons().length).toBeGreaterThan(0)
    expect(field('settings.logRetention').control.disabled).toBe(true)
    expect(field('settings.logRetention').control.value).toBe('90')
  })

  it('hides it without write:settings', () => {
    renderAudit(['read:settings'])
    expect(saveButtons()).toHaveLength(0)
  })
})
