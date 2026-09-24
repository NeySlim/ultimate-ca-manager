import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label }) => <label>{label}</label>,
  Select: ({ label }) => <label>{label}</label>,
  Badge: ({ children }) => <span>{children}</span>,
  LoadingSpinner: () => <span>loading</span>,
  ExperimentalBadge: () => <span>experimental</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
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

  it('is not offered when the key comes from the environment', () => {
    renderSection({ ...status, key_source: 'env' })
    expect(screen.queryByText('settings.disableEncryption')).not.toBeInTheDocument()
  })
})
