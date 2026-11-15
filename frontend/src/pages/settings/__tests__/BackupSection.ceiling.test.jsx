import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, value, onChange }) => <label>{label}<input aria-label={label} value={value} onChange={onChange} /></label>,
  Select: () => <select />,
  FileUpload: () => <div />,
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

const copy = vi.fn(async () => true)
vi.mock('../../../hooks/useClipboard', () => ({
  useClipboard: () => ({ copy, isCopied: () => false }),
}))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label }) => <span>{label}</span>,
}))

import BackupSection from '../BackupSection'

const renderSection = ({ settings = {}, backupMeta = {}, updateSetting = vi.fn() } = {}) => render(
  <BackupSection
    settings={settings}
    updateSetting={updateSetting}
    handleSave={vi.fn()}
    saving={false}
    hasPermission={() => true}
    backups={[]}
    backupMeta={backupMeta}
  />
)

describe('BackupSection size ceiling', () => {
  it('shows the ceiling and writes a whole number of MiB', () => {
    const updateSetting = vi.fn()
    renderSection({ settings: { backup_max_total_mb: 512 }, updateSetting })
    const field = screen.getByLabelText('settings.backupMaxTotalMb')
    expect(field.value).toBe('512')
    fireEvent.change(field, { target: { value: '64' } })
    expect(updateSetting).toHaveBeenCalledWith('backup_max_total_mb', 64)
    fireEvent.change(field, { target: { value: '' } })
    expect(updateSetting).toHaveBeenLastCalledWith('backup_max_total_mb', 0)
  })

  it('says how much room the stored archives take', () => {
    renderSection({ backupMeta: { total_size_all: '12.5 MB', total_all: 3, total_size_all_bytes: 13107200 } })
    expect(screen.getByTestId('backup-space-used')).toBeTruthy()
  })

  it('warns when the archives are above the ceiling, and only then', () => {
    const meta = { total_size_all: '2.0 MB', total_all: 1, total_size_all_bytes: 2 * 1024 * 1024 }
    const { unmount } = renderSection({ settings: { backup_max_total_mb: 1 }, backupMeta: meta })
    expect(screen.getByRole('alert')).toBeTruthy()
    unmount()
    renderSection({ settings: { backup_max_total_mb: 4 }, backupMeta: meta })
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('does not warn without a ceiling', () => {
    renderSection({ settings: { backup_max_total_mb: 0 },
      backupMeta: { total_size_all: '2.0 MB', total_all: 1, total_size_all_bytes: 2 * 1024 * 1024 } })
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
