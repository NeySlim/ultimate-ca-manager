import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label }) => <label>{label}</label>,
  Select: ({ label }) => <label>{label}</label>,
  Textarea: ({ label, value, onChange, disabled }) => (
    <label>{label}<textarea aria-label={label} value={value} onChange={onChange} disabled={disabled} /></label>
  ),
  Badge: ({ children }) => <span>{children}</span>,
  LoadingSpinner: () => <span>loading</span>,
  ExperimentalBadge: () => <span>experimental</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, badge, children }) => <section><h2>{title}</h2>{badge}{children}</section>,
  DetailGrid: ({ children }) => <div>{children}</div>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label }) => <span>{label}</span>,
}))

import SecuritySection from '../SecuritySection'

const renderSection = (encryptionStatus, extra = {}) => render(
  <SecuritySection
    settings={{}}
    updateSetting={vi.fn()}
    handleSave={vi.fn()}
    saving={false}
    hasPermission={() => true}
    encryptionStatus={encryptionStatus}
    setShowEnableEncryptionModal={vi.fn()}
    setShowDisableEncryptionModal={vi.fn()}
    anomalies={[]}
    anomaliesLoading={false}
    loadAnomalies={vi.fn()}
    mtlsSettings={{}}
    setMtlsSettings={vi.fn()}
    mtlsLoading={false}
    mtlsSaving={false}
    handleMtlsSave={vi.fn()}
    cas={[]}
    {...extra}
  />
)

describe('SecuritySection private key mirror status', () => {
  it('shows the on-disk key count and pending-removal warning', () => {
    renderSection({
      enabled: true,
      key_source: 'file',
      key_file_path: '/etc/ucm/master.key',
      total_keys: 4,
      encrypted_count: 4,
      unencrypted_count: 0,
      key_files_on_disk: 3,
    })

    expect(screen.getByText('settings.keyFilesOnDisk:')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('settings.keyFilesRemovalPending')).toBeInTheDocument()
  })

  it('shows zero without a warning when encryption is disabled', () => {
    renderSection({
      enabled: false,
      total_keys: 0,
      encrypted_count: 0,
      unencrypted_count: 0,
      key_files_on_disk: 0,
    })

    expect(screen.getByText('settings.keyFilesOnDisk:')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
    expect(screen.queryByText('settings.keyFilesRemovalPending')).not.toBeInTheDocument()
  })
})

describe('SecuritySection encrypting the remaining keys', () => {
  const status = {
    enabled: true,
    key_source: 'file',
    key_file_path: '/etc/ucm/master.key',
    total_keys: 5,
    encrypted_count: 3,
    unencrypted_count: 2,
    key_files_on_disk: 0,
  }

  it('offers it while encryption is on and keys are still in the clear', () => {
    const handleEncryptRemainingKeys = vi.fn()
    renderSection(status, { handleEncryptRemainingKeys })

    fireEvent.click(screen.getByText('settings.encryptRemainingKeys'))
    expect(handleEncryptRemainingKeys).toHaveBeenCalledOnce()
  })

  it('is not offered when every key is encrypted', () => {
    renderSection({ ...status, encrypted_count: 5, unencrypted_count: 0 },
      { handleEncryptRemainingKeys: vi.fn() })

    expect(screen.queryByText('settings.encryptRemainingKeys')).not.toBeInTheDocument()
  })
})

describe('SecuritySection disabling encryption', () => {
  const status = {
    enabled: true,
    key_file_path: '/etc/ucm/master.key',
    total_keys: 1,
    encrypted_count: 1,
    unencrypted_count: 0,
    key_files_on_disk: 0,
  }

  it('is offered when the key comes from the key file', () => {
    renderSection({ ...status, key_source: 'file' })
    expect(screen.getByText('settings.disableEncryption')).toBeInTheDocument()
  })

  it('is offered when the key comes from the environment: it stays configured, unused', () => {
    renderSection({ ...status, key_source: 'env' })
    expect(screen.getByText('settings.disableEncryption')).toBeInTheDocument()
  })

  it('shows a disable left half-way and offers to run it again, not to rotate', () => {
    const setShow = vi.fn()
    renderSection({ ...status, key_source: 'env', disabling: true },
      { setShowDisableEncryptionModal: setShow, handleRotateDataKey: vi.fn() })
    expect(screen.getByText('settings.encryptionDisabling')).toBeInTheDocument()
    expect(screen.getByText('settings.encryptionDisablingHint')).toBeInTheDocument()
    expect(screen.queryByText('common.enabled')).not.toBeInTheDocument()
    expect(screen.queryByText('settings.rotateDataKey')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('settings.runDisableAgain'))
    expect(setShow).toHaveBeenCalledWith(true)
  })
  it('names the end of a disable grace period and holds enabling until then', () => {
    renderSection({ ...status, enabled: false, key_source: 'env',
      disabled_keys_kept_until: '2026-11-12T10:00:00Z' })
    expect(screen.getByText('common.disabled')).toBeInTheDocument()
    expect(screen.getByText('settings.disabledKeysKeptUntil')).toBeInTheDocument()
    expect(screen.getByText('settings.enableEncryption').closest('button')).toBeDisabled()
  })
})

describe('SecuritySection data key rotation', () => {
  const status = {
    enabled: true,
    key_source: 'env',
    kek_fingerprint: '0123456789abcdef',
    dek_version: 2,
    rotation_in_progress: false,
    total_keys: 1,
    encrypted_count: 1,
    unencrypted_count: 0,
    key_files_on_disk: 0,
  }

  it('shows the fingerprint and version and offers the rotation', () => {
    const handleRotateDataKey = vi.fn()
    renderSection(status, { handleRotateDataKey })
    expect(screen.getByText('0123456789abcdef')).toBeInTheDocument()
    fireEvent.click(screen.getByText('settings.rotateDataKey'))
    expect(handleRotateDataKey).toHaveBeenCalledOnce()
  })

  it('offers to finish a rotation in progress', () => {
    renderSection({ ...status, rotation_in_progress: true }, { handleRotateDataKey: vi.fn() })
    expect(screen.getByText('settings.dekRotationInProgress')).toBeInTheDocument()
    expect(screen.getByText('settings.resumeDataKeyRotation')).toBeInTheDocument()
  })

  it('names the end of the previous key grace period and holds the next rotation', () => {
    renderSection({ ...status, previous_dek_retire_after: '2026-11-12T10:00:00Z' },
      { handleRotateDataKey: vi.fn() })
    expect(screen.getByText('settings.previousDekKeptUntil')).toBeInTheDocument()
    expect(screen.getByText('settings.rotateDataKey').closest('button')).toBeDisabled()
  })

  it('is not offered while encryption is off', () => {
    renderSection({ ...status, enabled: false }, { handleRotateDataKey: vi.fn() })
    expect(screen.queryByText('settings.rotateDataKey')).not.toBeInTheDocument()
  })
})

describe('SecuritySection session settings', () => {
  it('offers no API rate limit field: nothing stores or reads it', () => {
    renderSection({ enabled: false })
    expect(screen.getByText('settings.sessionDuration')).toBeInTheDocument()
    expect(screen.queryByText('settings.apiRateLimit')).not.toBeInTheDocument()
  })
})

describe('SecuritySection OCSP responder renewal', () => {
  it('offers the auto-renewal switch and its window', () => {
    renderSection({ enabled: false })
    expect(screen.getByText('settings.ocspResponderAutoRenew')).toBeInTheDocument()
    expect(screen.getByText('settings.ocspResponderRenewDays')).toBeInTheDocument()
  })

  it('hides the window when auto-renewal is off', () => {
    renderSection({ enabled: false }, { settings: { ocsp_responder_auto_renew: false } })
    expect(screen.queryByText('settings.ocspResponderRenewDays')).toBeNull()
  })
})

describe('SecuritySection admin access allowlist', () => {
  const renderAllowlist = (settings, extra = {}) => render(
    <SecuritySection
      settings={settings}
      updateSetting={vi.fn()}
      handleSave={vi.fn()}
      saving={false}
      hasPermission={() => true}
      encryptionStatus={null}
      setShowEnableEncryptionModal={vi.fn()}
      setShowDisableEncryptionModal={vi.fn()}
      anomalies={[]}
      anomaliesLoading={false}
      loadAnomalies={vi.fn()}
      mtlsSettings={{}}
      setMtlsSettings={vi.fn()}
      mtlsLoading={false}
      mtlsSaving={false}
      handleMtlsSave={vi.fn()}
      cas={[]}
      {...extra}
    />
  )

  it('lists the networks one per line and shows the address the server sees', () => {
    renderAllowlist({ admin_allowed_networks: ['10.0.0.0/8', '2001:db8::/32'], admin_client_ip: '10.1.2.3' })

    expect(screen.getByLabelText('settings.adminAllowlistNetworks').value).toBe('10.0.0.0/8\n2001:db8::/32')
    expect(screen.getByText('10.1.2.3')).toBeInTheDocument()
    expect(screen.getByText('settings.adminAllowlistActive')).toBeInTheDocument()
  })

  it('reports no restriction for an empty list', () => {
    renderAllowlist({ admin_allowed_networks: [], admin_client_ip: '10.1.2.3' })

    expect(screen.queryByText('settings.adminAllowlistActive')).not.toBeInTheDocument()
  })

  it('stores the edited text and saves its own card', () => {
    const updateSetting = vi.fn()
    const handleSave = vi.fn()
    renderAllowlist({ admin_allowed_networks: [] }, { updateSetting, handleSave })

    fireEvent.change(screen.getByLabelText('settings.adminAllowlistNetworks'), { target: { value: '192.0.2.0/24' } })
    expect(updateSetting).toHaveBeenCalledWith('admin_allowed_networks', '192.0.2.0/24')
  })

  it('is read-only when the environment sets the list', () => {
    renderAllowlist({ admin_allowed_networks: ['10.0.0.0/8'], admin_allowed_networks_env_locked: true })

    expect(screen.getByLabelText('settings.adminAllowlistNetworks')).toBeDisabled()
    expect(screen.getByText('settings.adminAllowlistEnvLocked')).toBeInTheDocument()
  })

  it('says when the check is switched off', () => {
    renderAllowlist({ admin_allowed_networks: ['10.0.0.0/8'], admin_allowlist_disabled: true })

    expect(screen.getByText('settings.adminAllowlistDisabled')).toBeInTheDocument()
    expect(screen.getByText('settings.adminAllowlistDisabledNote')).toBeInTheDocument()
    expect(screen.queryByText('settings.adminAllowlistActive')).not.toBeInTheDocument()
  })
})
