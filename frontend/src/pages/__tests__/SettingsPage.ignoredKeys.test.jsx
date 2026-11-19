/**
 * A save by an account without admin:settings sends no reserved key, so a
 * server that refuses reserved keys (as the real one does) has nothing to
 * refuse and the page shows a plain success, no warning.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/BackupSection', () => ({
  default: ({ handleSave }) => <button onClick={() => handleSave('backup')}>save-backup</button>,
}))

vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: (p) => p !== 'admin:settings', canRead: () => true, canWrite: () => true,
    canDelete: () => true, isAdmin: () => false, permissions: ['write:settings'],
  }),
}))

import { notificationSpies } from './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { ADMIN_ONLY_SETTINGS } from '../settings/adminOnlySettings'
import { settingsService } from '../../services/settings.service'

describe('SettingsPage: reserved settings without admin:settings', () => {
  it('sends no reserved key, so nothing is refused and no warning is shown', async () => {
    settingsService.getAll = vi.fn().mockResolvedValue({
      data: { system_name: 'x', backup_retention_days: 30, auto_backup_enabled: true } })
    // What the server does: drop the reserved keys it receives and name them
    settingsService.updateBulk = vi.fn(async (body) => ({
      data: { ignored_keys: Object.keys(body).filter((k) => ADMIN_ONLY_SETTINGS.includes(k)) } }))
    settingsService.getBackupSchedule = vi.fn().mockResolvedValue({ data: {} })
    settingsService.getEmailSettings = vi.fn().mockResolvedValue({ data: {} })

    render(
      <MemoryRouter initialEntries={['/settings?tab=backup']}>
        <SettingsPage />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByText('save-backup')).toBeTruthy())
    await waitFor(() => expect(settingsService.getAll).toHaveBeenCalled())
    await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
    await act(async () => { screen.getByText('save-backup').click() })
    await waitFor(() => expect(settingsService.updateBulk).toHaveBeenCalled())
    const sent = settingsService.updateBulk.mock.calls[0][0]
    expect(sent.system_name).toBe('x')
    expect(sent).not.toHaveProperty('backup_retention_days')
    expect(sent).not.toHaveProperty('auto_backup_enabled')
    await waitFor(() => expect(notificationSpies.showSuccess).toHaveBeenCalled())
    expect(Object.keys(sent).filter((k) => ADMIN_ONLY_SETTINGS.includes(k))).toEqual([])
    expect(notificationSpies.showWarning).not.toHaveBeenCalled()
  })
})
