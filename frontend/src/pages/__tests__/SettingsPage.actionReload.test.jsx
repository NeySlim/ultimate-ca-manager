/**
 * Settings: a one-off action (revoke or authorize SMTP OAuth, clear the backup password)
 * reloads the settings but keeps every change still pending in the other sections.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/GeneralSection', () => ({
  default: ({ settings, updateSetting }) => (
    <input aria-label="system-name" value={settings.system_name || ''} onChange={(e) => updateSetting('system_name', e.target.value)} />
  ),
}))
vi.mock('../settings/EmailSection', () => ({
  default: ({ settings, updateSetting, setOauthDirty, handleSmtpOAuthRevoke, handleSmtpOAuthAuthorize }) => (
    <>
      <input aria-label="smtp-host" value={settings.smtp_host || ''} onChange={(e) => { updateSetting('smtp_host', e.target.value); setOauthDirty(true) }} />
      <button type="button" onClick={handleSmtpOAuthRevoke}>revoke</button>
      <button type="button" onClick={handleSmtpOAuthAuthorize}>authorize</button>
    </>
  ),
}))
vi.mock('../settings/AuditSection', () => ({
  default: ({ settings, updateSetting }) => (
    <input aria-label="retention" value={settings.audit_retention_days ?? ''} onChange={(e) => updateSetting('audit_retention_days', e.target.value)} />
  ),
}))
vi.mock('../settings/BackupSection', () => ({
  default: ({ handleClearBackupPassword }) => <button type="button" onClick={handleClearBackupPassword}>clear-backup-password</button>,
}))
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => true, canRead: () => true, canWrite: () => true, canDelete: () => true,
    isAdmin: () => true, permissions: ['*'],
  }),
}))

import { notificationSpies } from './pageRenderingSetup.jsx'
import SettingsPage from '../SettingsPage'
import { settingsService } from '../../services/settings.service'
import { dropAllDrafts } from '../../lib/draftMemory'

beforeEach(() => {
  settingsService.getAll = vi.fn().mockResolvedValue({ data: { system_name: 'PKI', audit_retention_days: 90, backup_password_set: true } })
  settingsService.getEmailSettings = vi.fn().mockResolvedValue({ data: { smtp_host: 'smtp.example.com', smtp_port: 587 } })
  settingsService.updateBulk = vi.fn().mockResolvedValue({ data: {} })
  settingsService.updateEmailSettings = vi.fn().mockResolvedValue({ data: {} })
  settingsService.revokeSmtpOAuth = vi.fn().mockResolvedValue({ data: {} })
  settingsService.getSmtpOAuthAuthorizeUrl = vi.fn().mockResolvedValue({ data: { authorize_url: 'https://idp.example.com/authorize' } })
  notificationSpies.showConfirm = vi.fn().mockResolvedValue(true)
  window.history.replaceState(null, '', '/settings')
})
afterEach(() => { vi.clearAllMocks(); dropAllDrafts() })

async function withPendingDrafts() {
  render(<MemoryRouter><SettingsPage /></MemoryRouter>)
  await waitFor(() => expect(screen.getByLabelText('system-name')).toHaveValue('PKI'))
  fireEvent.change(screen.getByLabelText('system-name'), { target: { value: 'PKI 2' } })
  fireEvent.change(screen.getByLabelText('retention'), { target: { value: '777' } })
}

const expectDraftsKept = () => {
  expect(screen.getByLabelText('system-name')).toHaveValue('PKI 2')
  expect(screen.getByLabelText('retention')).toHaveValue('777')
}

describe('SettingsPage: a one-off action keeps the pending drafts', { timeout: 20000 }, () => {
  it('after revoking SMTP OAuth', async () => {
    await withPendingDrafts()
    const loads = settingsService.getAll.mock.calls.length
    await act(async () => { fireEvent.click(screen.getByText('revoke')) })
    await waitFor(() => expect(settingsService.getAll.mock.calls.length).toBeGreaterThan(loads))
    await act(async () => {})
    expectDraftsKept()
  })

  it('after clearing the backup password', async () => {
    await withPendingDrafts()
    await act(async () => { fireEvent.click(screen.getByText('clear-backup-password')) })
    expect(settingsService.updateBulk).toHaveBeenCalledWith({ clear_backup_password: true })
    await act(async () => {})
    expectDraftsKept()
  })

  it('after authorizing SMTP OAuth, the email section saved first and the others kept', async () => {
    const popup = { closed: false }
    const open = vi.spyOn(window, 'open').mockReturnValue(popup)
    try {
      await withPendingDrafts()
      fireEvent.change(screen.getByLabelText('smtp-host'), { target: { value: 'smtp2.example.com' } })
      await act(async () => { fireEvent.click(screen.getByText('authorize')) })
      expect(settingsService.updateEmailSettings).toHaveBeenCalledWith(expect.objectContaining({ smtp_host: 'smtp2.example.com' }))
      expect(settingsService.updateBulk).not.toHaveBeenCalled()
      expectDraftsKept()
      const loads = settingsService.getAll.mock.calls.length
      await act(async () => { window.dispatchEvent(new MessageEvent('message', { data: { type: 'smtp-oauth', ok: true } })) })
      await waitFor(() => expect(settingsService.getAll.mock.calls.length).toBeGreaterThan(loads))
      await act(async () => {})
      expectDraftsKept()
      // the saved section reads what the server now holds
      expect(screen.getByLabelText('smtp-host')).toHaveValue('smtp.example.com')
    } finally {
      popup.closed = true
      open.mockRestore()
    }
  })
})
