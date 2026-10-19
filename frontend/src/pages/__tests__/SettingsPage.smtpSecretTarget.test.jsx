/**
 * SMTP: the saved password stays with the saved server. Moving the host
 * without typing it again sends nothing; typing it saves.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/EmailSection', () => ({
  default: ({ settings, updateSetting, handleSave }) => (
    <div>
      <div data-testid="host">{settings.smtp_host}</div>
      <button onClick={() => updateSetting('smtp_host', 'smtp.attacker.example')}>move</button>
      <button onClick={() => updateSetting('smtp_password', 'typed')}>type</button>
      <button onClick={() => handleSave('email')}>save-email</button>
    </div>
  ),
}))

import './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { settingsService } from '../../services/settings.service'

const SAVED = { smtp_host: 'smtp.example.com', smtp_port: 587, smtp_username: 'mailer',
  smtp_password: '********', smtp_security: 'starttls', smtp_auth: true, smtp_auth_method: 'password' }

const click = async (label) => act(async () => { screen.getByText(label).click() })

describe('SettingsPage: SMTP saved password and target', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    settingsService.getAll = vi.fn().mockResolvedValue({ data: {} })
    settingsService.getEmailSettings = vi.fn().mockResolvedValue({ data: SAVED })
    settingsService.updateEmailSettings = vi.fn().mockResolvedValue({ data: {} })
    settingsService.getSmtpOAuthProviders = vi.fn().mockResolvedValue({ data: { providers: {} } })
    render(<MemoryRouter initialEntries={['/settings?tab=email']}><SettingsPage /></MemoryRouter>)
  })

  it('does not send a moved host without the password', async () => {
    await waitFor(() => expect(screen.getByTestId('host').textContent).toBe('smtp.example.com'))
    await click('move')
    await click('save-email')
    expect(settingsService.updateEmailSettings).not.toHaveBeenCalled()
  })

  it('sends it once the password is typed', async () => {
    await waitFor(() => expect(screen.getByTestId('host').textContent).toBe('smtp.example.com'))
    await click('move')
    await click('type')
    await click('save-email')
    await waitFor(() => expect(settingsService.updateEmailSettings).toHaveBeenCalledWith(
      expect.objectContaining({ smtp_host: 'smtp.attacker.example', smtp_password: 'typed' })))
  })

  it('saves an unchanged server with the password kept', async () => {
    await waitFor(() => expect(screen.getByTestId('host').textContent).toBe('smtp.example.com'))
    await click('save-email')
    await waitFor(() => expect(settingsService.updateEmailSettings).toHaveBeenCalled())
  })
})
