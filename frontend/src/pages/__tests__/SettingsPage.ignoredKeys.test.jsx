/**
 * A save by an account without admin:settings sends no reserved key, and a
 * server reply that names refused keys is shown as a warning, never a bare success.
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
import { settingsService } from '../../services/settings.service'

describe('SettingsPage: reserved settings without admin:settings', () => {
  it('strips reserved keys and warns about the ones the server refused', async () => {
    settingsService.getAll = vi.fn().mockResolvedValue({
      data: { system_name: 'x', backup_retention_days: 30, auto_backup_enabled: true } })
    settingsService.updateBulk = vi.fn().mockResolvedValue({
      data: { ignored_keys: ['session_timeout'] } })
    settingsService.getBackupSchedule = vi.fn().mockResolvedValue({ data: {} })

    render(
      <MemoryRouter initialEntries={['/settings?tab=backup']}>
        <SettingsPage />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByText('save-backup')).toBeTruthy())
    await waitFor(() => expect(settingsService.getAll).toHaveBeenCalled())
    await act(async () => { screen.getByText('save-backup').click() })
    await waitFor(() => expect(settingsService.updateBulk).toHaveBeenCalled())
    const sent = settingsService.updateBulk.mock.calls[0][0]
    expect(sent).not.toHaveProperty('backup_retention_days')
    expect(sent).not.toHaveProperty('auto_backup_enabled')
    await waitFor(() => expect(notificationSpies.showWarning).toHaveBeenCalled())
    expect(notificationSpies.showWarning.mock.calls.at(-1)[0]).toBe('settings.adminKeysIgnored')
  })
})
