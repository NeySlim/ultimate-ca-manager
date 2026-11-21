/**
 * The Backup section is shown to admin:system only, as before the sectioned page:
 * read:settings alone does not list it in the table of contents nor render its frame.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const granted = vi.hoisted(() => ({ list: [] }))
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: (p) => granted.list.includes(p),
    canRead: () => true, canWrite: () => false, canDelete: () => false,
    isAdmin: () => false, permissions: granted.list,
  }),
}))
vi.mock('../settings/BackupSection', () => ({ default: () => <p>backup-body</p> }))

import './pageRenderingSetup.jsx'
import SettingsPage from '../SettingsPage'
import { settingsService } from '../../services/settings.service'

const toc = () => screen.getByRole('navigation', { name: 'settings.tocLabel' })

beforeEach(() => {
  settingsService.getAll = vi.fn().mockResolvedValue({ data: { system_name: 'PKI' } })
  settingsService.getEmailSettings = vi.fn().mockResolvedValue({ data: {} })
})
afterEach(() => vi.clearAllMocks())

describe('SettingsPage: Backup section permission', () => {
  it('hides the Backup section from a role with read:settings only', async () => {
    granted.list = ['read:settings']
    render(<MemoryRouter initialEntries={['/settings']}><SettingsPage /></MemoryRouter>)
    await screen.findByRole('navigation', { name: 'settings.tocLabel' })
    expect(within(toc()).queryByRole('link', { name: /settings\.tabs\.backup/ })).toBeNull()
    expect(document.getElementById('set-sec-backup')).toBeNull()
    expect(screen.queryByText('backup-body')).toBeNull()
  })

  it('shows the Backup section with admin:system', async () => {
    granted.list = ['read:settings', 'admin:system']
    render(<MemoryRouter initialEntries={['/settings']}><SettingsPage /></MemoryRouter>)
    await screen.findByRole('navigation', { name: 'settings.tocLabel' })
    expect(within(toc()).getByRole('link', { name: /settings\.tabs\.backup/ })).toBeInTheDocument()
    expect(document.getElementById('set-sec-backup')).toBeInTheDocument()
  })
})
