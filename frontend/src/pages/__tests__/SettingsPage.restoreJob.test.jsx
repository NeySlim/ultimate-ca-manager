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

import { notificationSpies } from './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { systemService } from '../../services/system.service'
import { holdSignOut } from '../../services/apiClient'
import { PENDING_RESTORE_KEY, pendingRestore } from '../settings/useRestoreJob'

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
  notificationSpies.showError.mockClear()
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
    expect(pendingRestore('admin')).toBe('job-1')
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
    expect(pendingRestore('admin')).toBe('job-1')
    // The sign-in comes back to this tab, where the report is shown
    screen.getByTestId('restore-sign-in-button').click()
    expect(window.location.href).toBe('/login?next=%2Fsettings%3Ftab%3Dbackup')
  })

  it('shows the report of the followed job once signed in again', async () => {
    window.localStorage.setItem(PENDING_RESTORE_KEY, JSON.stringify({ id: 'job-1', account: 'admin' }))
    jobsApi.get.mockResolvedValue({ data: succeeded })
    renderPage()
    expect(await screen.findByText('Sign the CRL of Root CA')).toBeTruthy()
    expect(jobsApi.get).toHaveBeenCalledWith('job-1')
    expect(window.localStorage.getItem(PENDING_RESTORE_KEY)).toBeNull()
  })

  it('never shows another account the restore this browser followed', async () => {
    window.localStorage.setItem(PENDING_RESTORE_KEY, JSON.stringify({ id: 'job-old', account: 'someone-else' }))
    jobsApi.get.mockResolvedValue({ data: { ...succeeded, id: 'job-old' } })
    renderPage()
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(jobsApi.get).not.toHaveBeenCalled()
    expect(screen.queryByText('Sign the CRL of Root CA')).toBeNull()
    expect(window.localStorage.getItem(PENDING_RESTORE_KEY)).toBeNull()
    expect(pendingRestore('someone-else')).toBeNull()
  })

  it('keeps the followed restore under the account that started it', async () => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockResolvedValue({ data: running })
    await startRestore()
    expect(JSON.parse(window.localStorage.getItem(PENDING_RESTORE_KEY))).toEqual(
      { id: 'job-1', account: 'admin' })
    expect(pendingRestore('admin')).toBe('job-1')
    expect(pendingRestore('someone-else')).toBeNull()
  })

  it('says a cancelled restore restored nothing', async () => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockResolvedValue({ data: { ...running, state: 'cancelled', reason: 'cancelled' } })
    await startRestore()
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(screen.queryByTestId('restore-job')).toBeNull()
    expect(window.localStorage.getItem(PENDING_RESTORE_KEY)).toBeNull()
  })

  it.each([0, 502, 503])('takes a %s after the commit for the restart: sign in again', async (status) => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockResolvedValueOnce({ data: { ...running, phase: 'committed' } })
      .mockRejectedValue(Object.assign(new Error('Bad gateway'), { status }))
    await startRestore()
    await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
    expect(await screen.findByTestId('restore-sign-in')).toBeTruthy()
    expect(notificationSpies.showError).not.toHaveBeenCalledWith('Bad gateway')
    expect(notificationSpies.showError).not.toHaveBeenCalledWith('settings.restoreContactLost')
  })

  it.each([0, 502, 503])('says it lost the restore after %s errors before the commit', async (status) => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockResolvedValueOnce({ data: { ...running, phase: 'applying' } })
      .mockRejectedValue(Object.assign(new Error('Bad gateway'), { status }))
    await startRestore()
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(screen.getByTestId('restore-job')).toBeTruthy()  // one error: still followed
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(screen.queryByTestId('restore-job')).toBeNull()
    expect(screen.queryByTestId('restore-sign-in')).toBeNull()
    expect(notificationSpies.showError).toHaveBeenCalledWith('settings.restoreContactLost')
    expect(pendingRestore('admin')).toBe('job-1')  // shown at the next visit
  })

  it('says so when the restore picked up at load stops answering', async () => {
    window.localStorage.setItem(PENDING_RESTORE_KEY, JSON.stringify({ id: 'job-1', account: 'admin' }))
    jobsApi.get.mockResolvedValueOnce({ data: { ...running, phase: 'applying' } })
      .mockRejectedValue(Object.assign(new Error('Service unavailable'), { status: 503 }))
    renderPage()
    await act(async () => { await vi.advanceTimersByTimeAsync(12000) })
    expect(notificationSpies.showError).toHaveBeenCalledWith('settings.restoreContactLost')
  })

  it('lets the sign-out go when the "sign in again" box is closed', async () => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockRejectedValue(Object.assign(new Error('Authentication required'), { status: 401 }))
    await startRestore()
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(await screen.findByTestId('restore-sign-in')).toBeTruthy()
    expect(holdSignOut).toHaveBeenLastCalledWith()  // held since the restore began
    fireEvent.keyDown(document.activeElement, { key: 'Escape' })
    await act(async () => {})
    expect(screen.queryByTestId('restore-sign-in')).toBeNull()
    expect(holdSignOut).toHaveBeenLastCalledWith(false)
  })

  it('announces the progress and the sign-in, the sign-in button focused', async () => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockResolvedValueOnce({ data: running })
      .mockRejectedValue(Object.assign(new Error('Authentication required'), { status: 401 }))
    await startRestore()
    expect((await screen.findByTestId('restore-job-progress')).getAttribute('role')).toBe('status')
    await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
    const signIn = await screen.findByTestId('restore-sign-in')
    expect(signIn.querySelector('[role="status"]').textContent).toBe('settings.restoreSignInAgain')
    expect(document.activeElement).toBe(screen.getByTestId('restore-sign-in-button'))
  })

  it('offers no cancellation once the restore has committed', async () => {
    systemService.restore = vi.fn().mockResolvedValue({ data: { job: running } })
    jobsApi.get.mockResolvedValue({ data: { ...running, phase: 'sessions_revoked' } })
    await startRestore()
    expect(await screen.findByTestId('restore-job-cancel')).toBeTruthy()  // before it commits
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(screen.getByTestId('restore-job')).toBeTruthy()
    expect(screen.queryByTestId('restore-job-cancel')).toBeNull()
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
