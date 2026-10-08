/**
 * SMTP transport security travels as one `smtp_security` value (none,
 * starttls, ssl) between the API and the email section, so implicit TLS on
 * port 465 can be chosen and saved.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/EmailSection', () => ({
  default: ({ settings, updateSetting, handleSave, applyOAuthProviderPreset }) => (
    <div>
      <div data-testid="smtp-security">{settings.smtp_security}</div>
      <button onClick={() => updateSetting('smtp_security', 'ssl')}>pick-ssl</button>
      <button onClick={() => applyOAuthProviderPreset('implicit')}>pick-preset</button>
      <button onClick={() => handleSave('email')}>save-email</button>
    </div>
  ),
}))

import './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { settingsService } from '../../services/settings.service'

function renderSettings() {
  return render(
    <MemoryRouter initialEntries={['/settings?tab=email']}>
      <SettingsPage />
    </MemoryRouter>,
  )
}

function mockEmailApi(emailData, presets = {}) {
  settingsService.getAll = vi.fn().mockResolvedValue({ data: {} })
  settingsService.getEmailSettings = vi.fn().mockResolvedValue({ data: emailData })
  settingsService.updateEmailSettings = vi.fn().mockResolvedValue({ data: {} })
  settingsService.getSmtpOAuthProviders = vi.fn().mockResolvedValue({ data: { providers: presets } })
}

const shown = () => screen.getByTestId('smtp-security').textContent

describe('SettingsPage: SMTP transport security', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads smtp_security from the API', async () => {
    mockEmailApi({ smtp_tls: false, smtp_ssl: true, smtp_security: 'ssl' })
    renderSettings()
    await waitFor(() => expect(shown()).toBe('ssl'))
  })

  it('derives it from smtp_tls when an older backend omits it', async () => {
    mockEmailApi({ smtp_tls: true })
    renderSettings()
    await waitFor(() => expect(shown()).toBe('starttls'))
  })

  it('saves the chosen mode as smtp_security', async () => {
    mockEmailApi({ smtp_security: 'starttls' })
    renderSettings()
    await waitFor(() => expect(shown()).toBe('starttls'))
    await act(async () => { screen.getByText('pick-ssl').click() })
    await act(async () => { screen.getByText('save-email').click() })
    await waitFor(() => expect(settingsService.updateEmailSettings).toHaveBeenCalled())
    const body = settingsService.updateEmailSettings.mock.calls[0][0]
    expect(body.smtp_security).toBe('ssl')
    expect(body).not.toHaveProperty('smtp_tls')
  })

  it('a failed settings read does not reset the stored mode on save', async () => {
    mockEmailApi({})
    settingsService.getEmailSettings = vi.fn().mockRejectedValue(new Error('boom'))
    renderSettings()
    await waitFor(() => expect(settingsService.getEmailSettings).toHaveBeenCalled())
    await act(async () => { screen.getByText('save-email').click() })
    await waitFor(() => expect(settingsService.updateEmailSettings).toHaveBeenCalled())
    expect(settingsService.updateEmailSettings.mock.calls[0][0].smtp_security).toBeUndefined()
  })

  it('an OAuth preset with implicit TLS selects ssl', async () => {
    mockEmailApi({ smtp_security: 'none' }, {
      implicit: { smtp_host: 'smtp.example.com', smtp_port: 465, smtp_use_tls: false, smtp_use_ssl: true },
    })
    renderSettings()
    await waitFor(() => expect(shown()).toBe('none'))
    await waitFor(() => expect(settingsService.getSmtpOAuthProviders).toHaveBeenCalled())
    await act(async () => { screen.getByText('pick-preset').click() })
    await waitFor(() => expect(shown()).toBe('ssl'))
  })
})
