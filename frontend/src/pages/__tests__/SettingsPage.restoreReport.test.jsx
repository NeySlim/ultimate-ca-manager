/**
 * Settings > Backup: a restore shows its upload progress, then its report; a report
 * with things to do stays, one without reloads as before.
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

import './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { systemService } from '../../services/system.service'
import { holdSignOut } from '../../services/apiClient'

const reload = vi.fn()
beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.stubGlobal('location', { ...window.location, reload })
})
afterEach(() => {
  cleanup() // the unmount releases the hold: before the calls are cleared
  vi.useRealTimers()
  vi.unstubAllGlobals()
  reload.mockClear()
  holdSignOut.mockClear()
})

async function startRestore() {
  const view = render(
    <MemoryRouter initialEntries={['/settings?tab=backup']}>
      <SettingsPage />
    </MemoryRouter>,
  )
  await act(async () => { (await screen.findByText('pick-archive')).click() })
  fireEvent.change(screen.getByPlaceholderText('settings.enterBackupPassword'),
    { target: { value: 'a-long-enough-password' } })
  await act(async () => { screen.getByText('settings.restoreBackup').click() })
  return view
}

describe('SettingsPage: restore report', () => {
  it('keeps the report open, with its to-do lines, and does not reload', async () => {
    systemService.restore = vi.fn().mockResolvedValue({
      data: { users: 1, cas: 1, certificates: 1, restart_requested: true, todo: ['No new CRL could be signed for: Root CA'] },
    })
    await startRestore()
    expect(await screen.findByText('No new CRL could be signed for: Root CA')).toBeTruthy()
    await act(async () => { vi.advanceTimersByTime(10000) })
    expect(reload).not.toHaveBeenCalled()
    expect(screen.getByText('No new CRL could be signed for: Root CA')).toBeTruthy()
  })

  it('without anything to do reloads after two seconds', async () => {
    systemService.restore = vi.fn().mockResolvedValue({
      data: { users: 1, cas: 1, certificates: 1, restart_requested: true, todo: [] },
    })
    await startRestore()
    expect(await screen.findByText('settings.restoreReportTitle')).toBeTruthy()
    await act(async () => { vi.advanceTimersByTime(2000) })
    expect(reload).toHaveBeenCalled()
  })

  it('holds the sign-out from the restore on: it revokes the session of the page too', async () => {
    let finish
    systemService.restore = vi.fn(() => new Promise((resolve) => { finish = resolve }))
    await startRestore()
    expect(holdSignOut.mock.calls).toEqual([[]])
    await act(async () => { finish({ data: { users: 1, cas: 1, certificates: 1, restart_requested: false, todo: [] } }) })
    expect(holdSignOut.mock.calls).toEqual([[]])
  })

  it('releases the held sign-out when the restore is refused', async () => {
    systemService.restore = vi.fn().mockRejectedValue(Object.assign(new Error('Invalid password'), { status: 400 }))
    await startRestore()
    expect(holdSignOut.mock.calls).toEqual([[], [false]])
  })

  it('leaving the page during the upload releases the sign-out and reloads once restored', async () => {
    let finish
    systemService.restore = vi.fn(() => new Promise((resolve) => { finish = resolve }))
    const { unmount } = await startRestore()
    unmount()
    expect(holdSignOut.mock.calls).toEqual([[], [false]])
    expect(reload).not.toHaveBeenCalled()
    await act(async () => { finish({ data: { users: 1, cas: 1, certificates: 1, restart_requested: true, todo: ['x'] } }) })
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('leaving the page after a refused restore neither holds nor reloads', async () => {
    let fail
    systemService.restore = vi.fn(() => new Promise((resolve, reject) => { fail = reject }))
    const { unmount } = await startRestore()
    unmount()
    await act(async () => { fail(Object.assign(new Error('Invalid password'), { status: 400 })) })
    expect(holdSignOut.mock.calls.at(-1)).toEqual([false])
    expect(reload).not.toHaveBeenCalled()
  })

  it('leaving the page under its report releases the sign-out', async () => {
    systemService.restore = vi.fn().mockResolvedValue({
      data: { users: 1, cas: 1, certificates: 1, restart_requested: true, todo: ['x'] },
    })
    const { unmount } = await startRestore()
    expect(await screen.findByText('settings.restoreReportTitle')).toBeTruthy()
    unmount()
    expect(holdSignOut.mock.calls).toEqual([[], [false]])
  })

  it('shows the upload progress while the archive travels', async () => {
    let finish
    systemService.restore = vi.fn((file, password, { onProgress }) => {
      onProgress(5, 10)
      return new Promise((resolve) => { finish = resolve })
    })
    await startRestore()
    expect(await screen.findByText('settings.restoreUploading')).toBeTruthy()
    await act(async () => { finish({ data: { todo: [] } }) })
  })
})
