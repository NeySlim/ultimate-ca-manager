/**
 * Settings > Backup takes the space used and the ceiling warning from the server,
 * read again once the settings are saved.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/BackupSection', () => ({
  default: ({ backupSchedule, handleSave }) => (
    <div>
      <button onClick={() => handleSave('backup')}>save-backup</button>
      <div data-testid="schedule">{JSON.stringify(backupSchedule)}</div>
    </div>
  ),
}))

vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => true, canRead: () => true, canWrite: () => true,
    canDelete: () => true, isAdmin: () => true, permissions: ['*'],
  }),
}))

import './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { settingsService } from '../../services/settings.service'

describe('SettingsPage: backup schedule figures', () => {
  it('reads the schedule on load and again after a save', async () => {
    settingsService.getAll = vi.fn().mockResolvedValue({ data: {} })
    settingsService.updateBulk = vi.fn().mockResolvedValue({ data: {} })
    settingsService.getBackupSchedule = vi.fn()
      .mockResolvedValueOnce({ data: { over_ceiling: false, max_total_mb: 0 } })
      .mockResolvedValue({ data: { over_ceiling: true, max_total_mb: 1 } })

    render(
      <MemoryRouter initialEntries={['/settings?tab=backup']}>
        <SettingsPage />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('schedule').textContent).toContain('"over_ceiling":false')
    })
    await act(async () => { screen.getByText('save-backup').click() })
    await waitFor(() => {
      expect(screen.getByTestId('schedule').textContent).toContain('"over_ceiling":true')
    })
    expect(settingsService.updateBulk).toHaveBeenCalled()
  })
})
