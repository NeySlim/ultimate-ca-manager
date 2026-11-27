/**
 * Settings: a failed master key download or backup cancel says what went wrong, the
 * server's or the browser's reason first, the generic text only when there is none.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/SecuritySection', () => ({
  default: ({ setShowEnableEncryptionModal, handleDownloadExistingMasterKey }) => (
    <div>
      <button onClick={() => setShowEnableEncryptionModal(true)}>open-enable</button>
      <button onClick={handleDownloadExistingMasterKey}>download-existing</button>
    </div>
  ),
}))

vi.mock('../settings/EncryptionDialogs', () => ({
  EnableEncryptionDialog: ({ open, onConfirm }) => (open ? <button onClick={onConfirm}>confirm-enable</button> : null),
  MasterKeyBackupDialog: ({ open, onDownload }) => (open ? <button onClick={onDownload}>download-new</button> : null),
}))

vi.mock('../settings/BackupSection', () => ({
  default: ({ setShowBackupModal }) => <button onClick={() => setShowBackupModal(true)}>open-backup</button>,
}))

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
import { settingsService } from '../../services/settings.service'
import { systemService } from '../../services/system.service'
import jobsService from '../../services/jobs.service'

const realCreateObjectURL = URL.createObjectURL
beforeEach(() => {
  jobsService.list.mockResolvedValue({ data: [] })
  systemService.listBackups = vi.fn().mockResolvedValue({ data: [], meta: {} })
})
afterEach(() => {
  URL.createObjectURL = realCreateObjectURL
  cleanup()
  vi.clearAllMocks()
})

const renderPage = (tab) => render(
  <MemoryRouter initialEntries={[`/settings?tab=${tab}`]}><SettingsPage /></MemoryRouter>,
)
const click = async (label) => {
  const target = await screen.findByText(label)
  await act(async () => { target.click() })
}

describe('SettingsPage: master key download failures', () => {
  it('the key shown once after enabling: says why the browser could not save it', async () => {
    settingsService.enableEncryption = vi.fn().mockResolvedValue({ data: { master_key: 'KEY' } })
    renderPage('security')
    await click('open-enable')
    await click('confirm-enable')
    URL.createObjectURL = vi.fn(() => { throw new Error('quota exceeded') })
    await click('download-new')
    expect(notificationSpies.showError).toHaveBeenCalledWith('quota exceeded')
  })

  it('the existing key: gives the server reason', async () => {
    settingsService.downloadMasterKey = vi.fn().mockRejectedValue(Object.assign(new Error('Key file unreadable'), { status: 500 }))
    renderPage('security')
    await click('download-existing')
    await waitFor(() => expect(notificationSpies.showError).toHaveBeenCalledWith('Key file unreadable'))
  })

  it('the existing key: falls back to the generic text when the failure has no message', async () => {
    settingsService.downloadMasterKey = vi.fn().mockRejectedValue(undefined)
    renderPage('security')
    await click('download-existing')
    await waitFor(() => expect(notificationSpies.showError).toHaveBeenCalledWith('settings.masterKeyDownloadFailed'))
  })
})

describe('SettingsPage: backup cancel failure', () => {
  it('gives the server reason', async () => {
    const running = { id: 'b1', kind: 'backup', state: 'running', progress: { done: 3, total: 40 } }
    jobsService.get.mockResolvedValue({ data: running })
    jobsService.cancel.mockRejectedValue(Object.assign(new Error('Job already finishing'), { status: 409 }))
    systemService.backup = vi.fn().mockResolvedValue({ data: { job: running } })
    renderPage('backup')
    await click('open-backup')
    fireEvent.change(screen.getByPlaceholderText('settings.min12Characters'), { target: { value: 'A-long-enough-Passw0rd!' } })
    await click('settings.createAndDownload')
    const cancel = await screen.findByTestId('backup-job-cancel')
    await act(async () => { cancel.click() })
    await waitFor(() => expect(notificationSpies.showError).toHaveBeenCalledWith('Job already finishing'))
  })
})
