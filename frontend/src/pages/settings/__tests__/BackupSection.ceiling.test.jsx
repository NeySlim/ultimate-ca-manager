import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts ? `${key} ${JSON.stringify(opts)}` : key), i18n: { language: 'en' } }),
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


import BackupSection from '../BackupSection'

const MiB = 1024 * 1024

const renderSection = ({ settings = {}, backupMeta = {}, backupSchedule, updateSetting = vi.fn() } = {}) => render(
  <BackupSection
    settings={settings}
    updateSetting={updateSetting}
    handleSave={vi.fn()}
    saving={false}
    hasPermission={() => true}
    backups={[]}
    backupMeta={backupMeta}
    backupSchedule={backupSchedule}
  />
)

describe('BackupSection size ceiling', () => {
  it('shows the ceiling and writes the stored size in the reader units', () => {
    const updateSetting = vi.fn()
    renderSection({ settings: { backup_max_total_mb: 512 }, updateSetting })
    const field = screen.getByLabelText('settings.backupMaxTotalMb')
    expect(field.value).toBe('512')
    fireEvent.change(field, { target: { value: '64' } })
    expect(updateSetting).toHaveBeenCalledWith('backup_max_total_mb', 64)
    // Emptied, it stays empty: the checks refuse it at the save, no 0 under the fingers
    fireEvent.change(field, { target: { value: '' } })
    expect(updateSetting).toHaveBeenLastCalledWith('backup_max_total_mb', '')
  })

  it('says how much room the archives retention counts take, from the server', () => {
    renderSection({
      backupMeta: { total_size_all: '99.0 MB', total_all: 9, total_size_all_bytes: 99 * MiB },
      backupSchedule: { stored_bytes: 5 * MiB / 2, stored_count: 3, max_total_mb: 0, over_ceiling: false },
    })
    const line = screen.getByTestId('backup-space-used').textContent
    expect(line).toContain('"size":"2.5 MB"')
    expect(line).toContain('"count":3')
  })

  it('names the archive files retention neither counts nor removes', () => {
    renderSection({ backupSchedule: { stored_bytes: 0, stored_count: 0, uncounted_count: 2 } })
    expect(screen.getByTestId('backup-uncounted').textContent).toContain('"count":2')
  })

  it('says nothing of other files when there are none', () => {
    renderSection({ backupSchedule: { stored_bytes: 0, stored_count: 0, uncounted_count: 0 } })
    expect(screen.queryByTestId('backup-uncounted')).toBeNull()
  })

  it('warns when the server says the archives are above the saved ceiling', () => {
    renderSection({
      settings: { backup_max_total_mb: 1 },
      backupSchedule: { stored_bytes: 2 * MiB, stored_count: 1, max_total_mb: 1, over_ceiling: true },
    })
    const alert = screen.getByRole('alert').textContent
    expect(alert).toContain('settings.backupOverCeiling ')
    expect(alert).toContain('"ceiling":1')
  })

  it('does not warn from the value being typed', () => {
    // Field at 1 MiB, archives at 2 MiB, but the saved ceiling is 4: nothing is over yet
    renderSection({
      settings: { backup_max_total_mb: 1 },
      backupMeta: { total_size_all: '2.0 MB', total_all: 1, total_size_all_bytes: 2 * MiB },
      backupSchedule: { stored_bytes: 2 * MiB, stored_count: 1, max_total_mb: 4, over_ceiling: false },
    })
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('does not warn before the server has answered', () => {
    renderSection({
      settings: { backup_max_total_mb: 1 },
      backupMeta: { total_size_all: '2.0 MB', total_all: 1, total_size_all_bytes: 2 * MiB },
    })
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
