/**
 * Settings > Backup: a backup that outlasts the request answers 202 with a job. The dialog
 * follows it, shows which part it exports, can cancel it, offers the archive at the end,
 * and a reload picks a running backup up again. A backup done within the wait downloads as before.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/BackupSection', () => ({
  default: ({ setShowBackupModal, backupRunning }) => (
    <button onClick={() => setShowBackupModal(true)}>{backupRunning ? 'open-running' : 'open-backup'}</button>
  ),
}))

// An administrator: the page looks for a running backup only with admin:system
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => true, canRead: () => true, canWrite: () => true, canDelete: () => true,
    isAdmin: () => true, permissions: ['*'],
  }),
}))

vi.mock('../../services/jobs.service', async (importOriginal) => {
  const real = await importOriginal()
  return { ...real, default: { get: vi.fn(), list: vi.fn(), cancel: vi.fn() } }
})

import { notificationSpies } from './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { systemService } from '../../services/system.service'
import jobsService from '../../services/jobs.service'

const running = { id: 'b1', kind: 'backup', state: 'running', progress: { done: 3, total: 40 } }
const done = {
  ...running, state: 'succeeded', reason: 'done', progress: { done: 40, total: 40 },
  result: { code: 200, message: 'Backup created successfully', data: { filename: 'ucm_backup_x.ucmbkp', size_bytes: 9, warning: null } },
}

beforeEach(() => {
  jobsService.list.mockResolvedValue({ data: [] })
  systemService.downloadBackup = vi.fn().mockResolvedValue(new Blob(['x']))
  systemService.listBackups = vi.fn().mockResolvedValue({ data: [], meta: {} })
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const renderPage = () => render(
  <MemoryRouter initialEntries={['/settings?tab=backup']}>
    <SettingsPage />
  </MemoryRouter>,
)

async function startBackup() {
  renderPage()
  await act(async () => { (await screen.findByText('open-backup')).click() })
  fireEvent.change(screen.getByPlaceholderText('settings.min12Characters'),
    { target: { value: 'A-long-enough-Passw0rd!' } })
  await act(async () => { screen.getByText('settings.createAndDownload').click() })
}

describe('SettingsPage: backup job', () => {
  it('downloads a backup answered within the wait at once, as before', async () => {
    systemService.backup = vi.fn().mockResolvedValue({ data: done.result.data })
    await startBackup()
    await waitFor(() => expect(systemService.downloadBackup).toHaveBeenCalledWith('ucm_backup_x.ucmbkp'))
    expect(jobsService.get).not.toHaveBeenCalled()
    expect(notificationSpies.showSuccess).toHaveBeenCalledWith('messages.success.backup.created')
  })

  it('follows a 202 job, shows its progress, then offers the archive', async () => {
    systemService.backup = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsService.get.mockResolvedValueOnce({ data: done })
    await startBackup()
    expect(await screen.findByText('settings.backupProgress')).toBeTruthy()
    expect(screen.getByTestId('backup-job-cancel')).toBeTruthy()
    // Its buttons sit in the mockup's dialog actions row (rule above, 36 px buttons)
    expect(screen.getByTestId('backup-job-cancel').parentElement).toHaveClass('ui-dialog-actions')
    const download = await screen.findByTestId('backup-ready-download', {}, { timeout: 3000 })
    expect(download.parentElement).toHaveClass('ui-dialog-actions')
    expect(systemService.downloadBackup).not.toHaveBeenCalled()
    // Nothing is downloaded yet: the notice says where the archive is, not that it was downloaded
    expect(notificationSpies.showSuccess).toHaveBeenCalledWith('messages.success.backup.ready')
    expect(notificationSpies.showSuccess).not.toHaveBeenCalledWith('messages.success.backup.created')
    await act(async () => { download.click() })
    expect(systemService.downloadBackup).toHaveBeenCalledWith('ucm_backup_x.ucmbkp')
  })

  it('cancels the backup it follows and closes its dialog', async () => {
    systemService.backup = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsService.cancel.mockResolvedValueOnce({ data: { ...running, cancel_requested: true } })
    jobsService.get.mockResolvedValue({ data: { ...running, state: 'cancelled', reason: 'cancelled' } })
    await startBackup()
    await act(async () => { (await screen.findByTestId('backup-job-cancel')).click() })
    expect(jobsService.cancel).toHaveBeenCalledWith('b1')
    await waitFor(() => expect(screen.queryByTestId('backup-job')).toBeNull(), { timeout: 3000 })
    expect(screen.queryByTestId('backup-ready')).toBeNull()
    expect(screen.queryByText('settings.createAndDownload')).toBeNull()
  })

  it('picks a running backup up after a reload', async () => {
    // The page asks for its running restore too: each question gets the answer of its kind
    jobsService.list.mockImplementation(({ kind }) => Promise.resolve({ data: kind === 'backup' ? [running] : [] }))
    jobsService.get.mockResolvedValueOnce({ data: done })
    renderPage()
    expect(await screen.findByTestId('backup-job')).toBeTruthy()
    expect(jobsService.list).toHaveBeenCalledWith({ kind: 'backup', state: 'active', limit: 1 })
    expect(await screen.findByTestId('backup-ready', {}, { timeout: 3000 })).toBeTruthy()
  })
})
