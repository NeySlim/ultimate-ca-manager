/**
 * Settings > Backup: a restore past the bounded wait is a job, followed in its dialog. Its
 * end shows the report; the 401 of a restore that signed the page out asks for a sign-in,
 * never a failure; after that sign-in the report of the job this browser followed shows.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/BackupSection', () => ({
  default: ({ setRestoreFile, setShowRestoreModal }) => (
    <button onClick={() => { setRestoreFile(new File(['x'], 'a.ucmbkp')); setShowRestoreModal(true) }}>
      pick-archive
    </button>
  ),
}))

const jobsApi = vi.hoisted(() => ({ get: vi.fn(), list: vi.fn(), cancel: vi.fn() }))
vi.mock('../../services/jobs.service', async (importOriginal) => {
  const real = await importOriginal()
  return { ...real, default: jobsApi }
})

import './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { systemService } from '../../services/system.service'
import { PENDING_RESTORE_KEY } from '../settings/useRestoreJob'

// An administrator: the page picks up the restore this browser followed
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({ hasPermission: () => true, canWrite: () => true, canRead: () => true,
    canDelete: () => true }),
  default: () => ({ hasPermission: () => true, canWrite: () => true, canRead: () => true,
    canDelete: () => true }),
}))

const running = { id: 'job-1', kind: 'restore', state: 'running', progress: { done: 2, total: 10 } }
const report = { users: 1, cas: 1, certificates: 1, restart_requested: true, todo: ['Sign the CRL of Root CA'] }
const succeeded = { ...running, state: 'succeeded', result: { code: 200, data: report } }

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.stubGlobal('location', { ...window.location, reload: vi.fn() })
  window.localStorage.clear()
  jobsApi.list.mockResolvedValue({ data: [] })
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  Object.values(jobsApi).forEach((fn) => fn.mockReset())
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/settings?tab=backup']}>
      <SettingsPage />
    </MemoryRouter>,
  )
}

async function startRestore() {
  renderPage()
  await act(async () => { (await screen.findByText('pick-archive')).click() })
  fireEvent.change(screen.getByPlaceholderText('settings.enterBackupPassword'),
    { target: { value: 'a-long-enough-password' } })
  await act(async () => { screen.getByText('settings.restoreBackup').click() })
}

describe('SettingsPage: restore as a job', () => {
  it('follows a 202 in the dialog, then shows the report', async () => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockResolvedValueOnce({ data: running }).mockResolvedValue({ data: succeeded })
    await startRestore()
    expect(await screen.findByTestId('restore-job')).toBeTruthy()
    expect(window.localStorage.getItem(PENDING_RESTORE_KEY)).toBe('job-1')
    await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
    expect(await screen.findByText('Sign the CRL of Root CA')).toBeTruthy()
    expect(window.localStorage.getItem(PENDING_RESTORE_KEY)).toBeNull()
  })

  it('takes a 401 while following for the end of its own session, not a failure', async () => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockRejectedValue(Object.assign(new Error('Authentication required'), { status: 401 }))
    await startRestore()
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(await screen.findByTestId('restore-sign-in')).toBeTruthy()
    expect(screen.queryByText('Authentication required')).toBeNull()
    expect(window.localStorage.getItem(PENDING_RESTORE_KEY)).toBe('job-1')
  })

  it('shows the report of the followed job once signed in again', async () => {
    window.localStorage.setItem(PENDING_RESTORE_KEY, 'job-1')
    jobsApi.get.mockResolvedValue({ data: succeeded })
    renderPage()
    expect(await screen.findByText('Sign the CRL of Root CA')).toBeTruthy()
    expect(jobsApi.get).toHaveBeenCalledWith('job-1')
    expect(window.localStorage.getItem(PENDING_RESTORE_KEY)).toBeNull()
  })

  it('says a cancelled restore restored nothing', async () => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockResolvedValue({ data: { ...running, state: 'cancelled', reason: 'cancelled' } })
    await startRestore()
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(screen.queryByTestId('restore-job')).toBeNull()
    expect(window.localStorage.getItem(PENDING_RESTORE_KEY)).toBeNull()
  })

  it('asks the server to cancel the running restore', async () => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockResolvedValue({ data: running })
    jobsApi.cancel.mockResolvedValue({ data: { ...running, cancel_requested: true } })
    await startRestore()
    await act(async () => { (await screen.findByTestId('restore-job-cancel')).click() })
    expect(jobsApi.cancel).toHaveBeenCalledWith('job-1')
  })
})
