import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label }) => <label>{label}</label>,
  Select: ({ label, options, value, onChange, disabled }) => (
    <label>
      {label}
      <select aria-label={label} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  ),
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

const renderSection = (settings, hasPermission = () => true) => {
  const updateSetting = vi.fn()
  render(
    <BackupSection
      settings={{ auto_backup_enabled: true, ...settings }}
      updateSetting={updateSetting}
      handleSave={vi.fn()}
      saving={false}
      hasPermission={hasPermission}
      backups={[]}
    />
  )
  return updateSetting
}

describe('BackupSection scheduled-backup KDF', () => {
  it('shows automatic by default and stores the chosen KDF', () => {
    const updateSetting = renderSection({})
    const select = screen.getByLabelText('settings.backupKdf')
    expect(select.value).toBe('auto')
    fireEvent.change(select, { target: { value: 'pbkdf2' } })
    expect(updateSetting).toHaveBeenCalledWith('backup_kdf', 'pbkdf2')
  })

  it('shows the stored KDF', () => {
    renderSection({ backup_kdf: 'argon2id' })
    expect(screen.getByLabelText('settings.backupKdf').value).toBe('argon2id')
  })
})
