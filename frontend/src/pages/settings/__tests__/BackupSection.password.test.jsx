import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, value, helperText }) => <label>{label}<input readOnly value={value} />{helperText}</label>,
  Select: ({ label }) => <label>{label}</label>,
  FileUpload: () => <div />,
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label }) => <span>{label}</span>,
}))

import BackupSection from '../BackupSection'

const renderSection = (settings, extra = {}) => render(
  <BackupSection
    settings={{ auto_backup_enabled: true, backup_password: '', ...settings }}
    updateSetting={vi.fn()}
    handleSave={vi.fn()}
    saving={false}
    hasPermission={() => true}
    backups={[]}
    {...extra}
  />
)

describe('BackupSection scheduled-backup password status', () => {
  it('says a password is set and offers to clear it, without showing it', () => {
    const handleClearBackupPassword = vi.fn()
    renderSection({ backup_password_set: true }, { handleClearBackupPassword })

    expect(screen.getByText('settings.backupPasswordSet')).toBeInTheDocument()
    expect(screen.getByText('settings.backupPasswordKeepHelper')).toBeInTheDocument()
    fireEvent.click(screen.getByText('settings.clearBackupPassword'))
    expect(handleClearBackupPassword).toHaveBeenCalledOnce()
  })

  it('says none is set and offers nothing to clear', () => {
    renderSection({ backup_password_set: false }, { handleClearBackupPassword: vi.fn() })

    expect(screen.getByText('settings.backupPasswordNotSet')).toBeInTheDocument()
    expect(screen.queryByText('settings.clearBackupPassword')).not.toBeInTheDocument()
  })
})
