/**
 * The data and system sections on the mockup's settings gabarit: the backup frequency carries
 * the off switch, the restore file is checked before its dialog opens, the archives sort by
 * their headers, the database test and its confirmations, the appearance choices, the automatic
 * updates, and which tests the write guard holds.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within, waitFor, act } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getStatus: vi.fn(), testConnection: vi.fn(), migrateData: vi.fn(), switchBackend: vi.fn(),
  notify: { showError: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() },
  theme: { themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(),
    themes: [{ id: 'atelier', nameKey: 'themes.atelier', accent: 'var(--accent)' }, { id: 'aurore', nameKey: 'themes.aurore', accent: 'var(--accent)' }] },
  mobile: { forceDesktop: false, setForceDesktop: vi.fn(), screenWidth: 1600, breakpoints: { lg: 1024 }, isMobile: false },
  chooseLanguage: vi.fn(),
  get: vi.fn(), patch: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'fr' } }),
}))
vi.mock('../../../services', () => ({
  databaseService: { getStatus: mocks.getStatus, testConnection: mocks.testConnection, migrateData: mocks.migrateData, switchBackend: mocks.switchBackend },
  apiClient: { get: mocks.get, patch: mocks.patch },
}))
vi.mock('../../../contexts', () => ({ useNotification: () => mocks.notify, useMobile: () => mocks.mobile }))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => mocks.mobile }))
vi.mock('../../../contexts/ThemeContext', () => ({ useTheme: () => mocks.theme }))
vi.mock('../../../lib/chooseLanguage', () => ({ chooseLanguage: mocks.chooseLanguage }))
vi.mock('../../../i18n', () => ({ languages: [{ code: 'en', name: 'English' }, { code: 'fr', name: 'Français' }] }))
vi.mock('../../../hooks/useSaveParts', () => ({ useSavePart: () => {}, keptPartDraft: () => ({}) }))

import BackupSection from '../BackupSection'
import DatabaseBackendSection from '../DatabaseBackendSection'
import AppearanceSettings from '../AppearanceSettings'
import AutoUpdateSettings from '../AutoUpdateSettings'
import FipsPreflightPanel from '../FipsPreflightPanel'
import AuditSection from '../AuditSection'
import { BackupDialog, RestoreDialog } from '../BackupDialogs'

const all = () => true
const backup = (props = {}) => {
  const p = {
    settings: { auto_backup_enabled: true, backup_frequency: 'weekly' }, updateSetting: vi.fn(), hasPermission: all,
    backups: [], backupMeta: {}, updateBackupQuery: vi.fn(), setShowRestoreModal: vi.fn(), setRestoreFile: vi.fn(),
    toggleSelectBackup: vi.fn(), toggleSelectAllBackups: vi.fn(), clearBackupSelection: vi.fn(), handleBulkDeleteBackups: vi.fn(),
    handleDownloadBackup: vi.fn(), handleDeleteBackup: vi.fn(), setShowBackupModal: vi.fn(), ...props,
  }
  render(<BackupSection {...p} />)
  return p
}
const archives = [
  { filename: 'a.ucmbkp', size_bytes: 1024, created_at: '2026-11-20 10:05:00 UTC' },
  { filename: 'b.ucmbkp', size_bytes: 2048, created_at: '2026-11-19 10:05:00 UTC' },
]

beforeEach(() => {
  vi.clearAllMocks()
  mocks.mobile.isMobile = false
})

describe('Backup: the mockup frequency', () => {
  it('shows a disabled schedule as « off » and switches it on with the cadence chosen', () => {
    const p = backup({ settings: { auto_backup_enabled: false, backup_frequency: 'monthly' } })
    const freq = screen.getByLabelText('settings.backupFrequency')
    expect(freq.value).toBe('off')
    expect([...freq.options].map((o) => o.value)).toEqual(['daily', 'weekly', 'monthly', 'off'])
    // The fields of a scheduled archive only while it runs
    expect(screen.queryByLabelText(/settings.autoBackupPassword/)).toBeNull()
    fireEvent.change(freq, { target: { value: 'daily' } })
    expect(p.updateSetting).toHaveBeenCalledWith('auto_backup_enabled', true)
    expect(p.updateSetting).toHaveBeenCalledWith('backup_frequency', 'daily')
  })

  it('« off » stops the schedule and keeps the cadence', () => {
    const p = backup()
    const freq = screen.getByLabelText('settings.backupFrequency')
    expect(freq.value).toBe('weekly')
    fireEvent.change(freq, { target: { value: 'off' } })
    expect(p.updateSetting).toHaveBeenCalledWith('auto_backup_enabled', false)
    expect(p.updateSetting).not.toHaveBeenCalledWith('backup_frequency', 'off')
  })
})

describe('Backup: the restore file', () => {
  it('refuses a file above the announced ceiling under the field, without opening the dialog', async () => {
    const p = backup({ backupMeta: { restore_limits: { archive_bytes: 10, upload_bytes: 10 } } })
    const input = document.getElementById('set-restore_file')
    await act(async () => { fireEvent.change(input, { target: { files: [new File(['x'.repeat(20)], 'big.ucmbkp')] } }) })
    expect(p.setShowRestoreModal).not.toHaveBeenCalled()
    const pick = screen.getByRole('button', { name: /settings.restoreChooseFile/ })
    expect(pick).toHaveAccessibleDescription('settings.restoreTooLarge')
    expect(document.getElementById('err-set-restore_file')).toHaveTextContent('settings.restoreTooLarge')
  })

  it('opens the restore dialog with a file it accepts', async () => {
    const p = backup({ backupMeta: { restore_limits: { archive_bytes: 100, upload_bytes: 100 } } })
    const file = new File(['abc'], 'ok.ucmbkp')
    // The button opens the hidden file input
    const input = document.getElementById('set-restore_file')
    const click = vi.spyOn(input, 'click')
    fireEvent.click(screen.getByRole('button', { name: /settings.restoreChooseFile/ }))
    expect(click).toHaveBeenCalled()
    await act(async () => { fireEvent.change(input, { target: { files: [file] } }) })
    expect(p.setRestoreFile).toHaveBeenCalledWith(file)
    expect(p.setShowRestoreModal).toHaveBeenCalledWith(true)
  })
})

describe('Backup: the archives in the module table', () => {
  it('sorts by its headers alone, the server order kept in the query: a new column ascending, the sorted one reversed (T3)', () => {
    const p = backup({ backups: archives, backupQuery: { sort: 'created_desc' } })
    expect(screen.getByRole('columnheader', { name: /table.fullCreated/ })).toHaveAttribute('aria-sort', 'descending')
    fireEvent.click(screen.getByRole('button', { name: /table.fullCreated/ }))
    expect(p.updateBackupQuery).toHaveBeenLastCalledWith({ sort: 'created_asc' })
    fireEvent.click(screen.getByRole('button', { name: /settings.backupSize/ }))
    expect(p.updateBackupQuery).toHaveBeenLastCalledWith({ sort: 'size_asc' })
    // One sort control for one list: no select beside the headers
    expect(document.querySelector('#backup-sort')).toBeNull()
    // The size is a number, at the right; the archive names its row, its whole name in a title
    expect(screen.getByRole('columnheader', { name: /settings.backupSize/ })).toHaveClass('num')
    expect(screen.getByText('a.ucmbkp')).toHaveAttribute('title', 'a.ucmbkp')
  })

  it('selects for the bulk delete and clears the selection from its bar', () => {
    const p = backup({ backups: archives, selectedBackups: ['a.ucmbkp'] })
    fireEvent.click(screen.getByLabelText(/table.selectRow/, { selector: '[data-select="b.ucmbkp"]' }))
    expect(p.toggleSelectBackup).toHaveBeenCalledWith('b.ucmbkp')
    const bar = screen.getByRole('group', { name: 'table.selection' })
    fireEvent.click(within(bar).getByRole('button', { name: /settings.backupDeleteSelected/ }))
    expect(p.handleBulkDeleteBackups).toHaveBeenCalled()
    fireEvent.click(within(bar).getByRole('button', { name: 'table.clearSelection' }))
    expect(p.clearBackupSelection).toHaveBeenCalled()
  })

  it('keeps the selection and the delete from a reader without admin:system', () => {
    backup({ backups: archives, hasPermission: (perm) => perm !== 'admin:system' })
    expect(document.querySelector('[data-select]')).toBeNull()
    expect(screen.queryByTitle('common.delete')).toBeNull()
    expect(screen.getAllByTitle('common.download')).toHaveLength(2)
  })

  it('keeps download and delete on each card of a phone', () => {
    mocks.mobile.isMobile = true
    const p = backup({ backups: archives })
    const card = screen.getByText('a.ucmbkp').closest('.mobile-record')
    // Its date and its size named by their columns (M3)
    expect([...card.querySelectorAll('.row-meta .fact-label')].map((l) => l.textContent)).toEqual(['table.fullCreated', 'settings.backupSize'])
    fireEvent.click(within(card).getByTitle('common.download'))
    expect(p.handleDownloadBackup).toHaveBeenCalledWith('a.ucmbkp')
    fireEvent.click(within(card).getByTitle('common.delete'))
    expect(p.handleDeleteBackup).toHaveBeenCalledWith('a.ucmbkp')
  })
})

describe('Database: change of backend', () => {
  beforeEach(() => {
    mocks.getStatus.mockResolvedValue({ data: { backend: 'sqlite', version: '3.45', table_count: 80, size_bytes: 1024, uri_redacted: 'sqlite:///x.db', healthy: true, is_docker: false } })
  })

  it('tests the typed URL, then opens the migration confirmation in the mockup dialog', async () => {
    mocks.testConnection.mockResolvedValue({ data: { success: true, message: 'PostgreSQL 16 reachable' } })
    render(<DatabaseBackendSection />)
    const url = await screen.findByLabelText('settings.backend.targetUrl')
    const migrate = screen.getByRole('button', { name: /settings.backend.migrateData/ })
    expect(migrate).toBeDisabled()
    expect(screen.getByRole('button', { name: /settings.backend.test/ })).toBeDisabled()
    fireEvent.change(url, { target: { value: 'postgresql://u:p@db:5432/ucm' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /settings.backend.test/ })) })
    expect(mocks.testConnection).toHaveBeenCalledWith('postgresql://u:p@db:5432/ucm')
    expect(screen.getByRole('status')).toHaveTextContent('PostgreSQL 16 reachable')
    expect(screen.getByRole('status')).toHaveClass('good')
    fireEvent.click(migrate)
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('settings.backend.confirmMigrateMessage')).toBeInTheDocument()
    expect(dialog.querySelector('.modal-actions')).not.toBeNull()
  })

  it('names its health in words and offers the redacted URI to copy', async () => {
    render(<DatabaseBackendSection />)
    expect((await screen.findByText('settings.backend.healthy')).closest('.badge')).toHaveClass('good')
    expect(screen.getByText('sqlite:///x.db')).toHaveClass('mono')
    expect(screen.getByRole('button', { name: 'common.copy' })).toBeInTheDocument()
  })
})

describe('Appearance', () => {
  it('picks the theme, the mode and the language', () => {
    render(<AppearanceSettings />)
    const family = screen.getByRole('group', { name: 'settings.colorTheme' })
    expect(within(family).getByRole('button', { name: 'themes.atelier' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(within(family).getByRole('button', { name: 'themes.aurore' }))
    expect(mocks.theme.setThemeFamily).toHaveBeenCalledWith('aurore')
    fireEvent.click(within(screen.getByRole('group', { name: 'settings.appearanceMode' })).getByRole('button', { name: 'settings.light' }))
    expect(mocks.theme.setMode).toHaveBeenCalledWith('light')
    fireEvent.change(screen.getByLabelText('settings.language'), { target: { value: 'en' } })
    expect(mocks.chooseLanguage).toHaveBeenCalledWith(expect.anything(), 'en')
    fireEvent.click(screen.getByRole('checkbox', { name: 'settings.forceDesktopLayout' }))
    expect(mocks.mobile.setForceDesktop).toHaveBeenCalledWith(true)
  })
})

describe('Automatic updates', () => {
  it('asks the hour only while the installation is automatic', async () => {
    mocks.get.mockResolvedValue({ data: { channel: 'stable', auto_install: false, hour: 4, popup_enabled: true, can_auto_update: true } })
    render(<AutoUpdateSettings />)
    const auto = await screen.findByRole('checkbox', { name: 'settings.autoUpdateEnable' })
    expect(screen.queryByLabelText('settings.autoUpdateHour')).toBeNull()
    fireEvent.click(auto)
    await waitFor(() => expect(screen.getByLabelText('settings.autoUpdateHour').value).toBe('4'))
  })

  it('cannot switch the installation on under Docker, and says why', async () => {
    mocks.get.mockResolvedValue({ data: { channel: 'rc', auto_install: false, hour: 3, popup_enabled: false, can_auto_update: false } })
    render(<AutoUpdateSettings />)
    const auto = await screen.findByRole('checkbox', { name: 'settings.autoUpdateEnable' })
    expect(auto).toBeDisabled()
    expect(auto).toHaveAccessibleDescription('settings.autoUpdateDockerHint')
    expect(screen.getByLabelText('settings.autoUpdateChannel').value).toBe('rc')
  })
})

describe('Tests and the write guard', () => {
  it('lets a read-only check run (FIPS preflight), holds a test that sends (syslog)', () => {
    render(<FipsPreflightPanel />)
    expect(screen.getByRole('button', { name: /settings.fipsPreflight.run/ })).not.toHaveAttribute('data-write')
    render(<AuditSection settings={{}} updateSetting={vi.fn()} hasPermission={all} syslogConfig={{ categories: [] }}
      updateSyslogConfig={vi.fn()} handleTestSyslog={vi.fn()} />)
    expect(screen.getByRole('button', { name: /settings.syslogTest/ })).toHaveAttribute('data-write')
  })
})

describe('Backup and restore dialogs', () => {
  const create = (props) => {
    const p = { password: '', setPassword: vi.fn(), problem: null, loading: false, onClose: vi.fn(), onCreate: vi.fn(), onCancelJob: vi.fn(), onDownload: vi.fn(), ...props }
    render(<BackupDialog {...p} />)
    return p
  }

  it('creates on Enter once the password passes, never while it is refused', () => {
    const refused = create({ password: 'short', problem: 'settings.passwordMinLength' })
    const field = screen.getByLabelText('settings.encryptionPassword')
    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('button', { name: /settings.createAndDownload/ })).toBeDisabled()
    fireEvent.submit(field.closest('form'))
    expect(refused.onCreate).not.toHaveBeenCalled()
  })

  it('creates from a password it accepts, the field focused at the opening', () => {
    const p = create({ password: 'a long enough passphrase' })
    expect(document.activeElement).toBe(screen.getByLabelText('settings.encryptionPassword'))
    fireEvent.submit(screen.getByLabelText('settings.encryptionPassword').closest('form'))
    expect(p.onCreate).toHaveBeenCalledOnce()
  })

  it('restores only with a password of 12 characters or more', () => {
    const p = { job: { running: false, signInNeeded: false }, file: new File(['x'], 'x.ucmbkp'), password: 'eleven char', setPassword: vi.fn(),
      onClose: vi.fn(), onCancel: vi.fn(), onRestore: vi.fn(), onCancelJob: vi.fn(), onSignIn: vi.fn() }
    const { rerender } = render(<RestoreDialog {...p} />)
    expect(screen.getByRole('button', { name: /settings.restoreBackup/ })).toBeDisabled()
    expect(screen.getByText('x.ucmbkp')).toBeInTheDocument()
    rerender(<RestoreDialog {...p} password="twelve chars" />)
    fireEvent.submit(screen.getByLabelText('settings.backupPassword').closest('form'))
    expect(p.onRestore).toHaveBeenCalledOnce()
  })
})
