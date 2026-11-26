/**
 * The OAuth2 provider is saved as the API gave it: a stored empty provider is not
 * rewritten to the preset the card shows, which the API would refuse to an operator
 * as a move of the SMTP target. Choosing OAuth2 anew takes the provider shown.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/EmailSection', () => ({
  default: ({ settings, updateSetting, handleSave }) => (
    <div>
      <div data-testid="smtp-method">{settings.smtp_auth_method}</div>
      <button onClick={() => updateSetting('smtp_auth_method', 'oauth2')}>pick-oauth2</button>
      <button onClick={() => handleSave('email')}>save-email</button>
    </div>
  ),
}))

import './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { settingsService } from '../../services/settings.service'

function mockEmailApi(emailData) {
  settingsService.getAll = vi.fn().mockResolvedValue({ data: {} })
  settingsService.getEmailSettings = vi.fn().mockResolvedValue({ data: emailData })
  settingsService.updateEmailSettings = vi.fn().mockResolvedValue({ data: {} })
  settingsService.getSmtpOAuthProviders = vi.fn().mockResolvedValue({ data: { providers: {} } })
}

async function save(emailData, before) {
  mockEmailApi(emailData)
  render(<MemoryRouter initialEntries={['/settings?tab=email']}><SettingsPage /></MemoryRouter>)
  await waitFor(() => expect(screen.getByTestId('smtp-method').textContent).toBe(emailData.smtp_auth_method))
  if (before) await act(async () => { screen.getByText(before).click() })
  await act(async () => { screen.getByText('save-email').click() })
  await waitFor(() => expect(settingsService.updateEmailSettings).toHaveBeenCalled())
  return settingsService.updateEmailSettings.mock.calls[0][0]
}

describe('SettingsPage: SMTP OAuth2 provider', () => {
  beforeEach(() => vi.clearAllMocks())

  it('saves a stored empty provider unchanged', async () => {
    const body = await save({ smtp_auth: true, smtp_auth_method: 'oauth2', smtp_oauth_provider: '' })
    expect(body.smtp_oauth_provider).toBe('')
  })

  it('saves a stored provider unchanged', async () => {
    const body = await save({ smtp_auth: true, smtp_auth_method: 'oauth2', smtp_oauth_provider: 'microsoft' })
    expect(body.smtp_oauth_provider).toBe('microsoft')
  })

  it('takes the provider the card shows when OAuth2 is chosen anew', async () => {
    const body = await save({ smtp_auth: true, smtp_auth_method: 'password', smtp_oauth_provider: '' }, 'pick-oauth2')
    expect(body.smtp_auth_method).toBe('oauth2')
    expect(body.smtp_oauth_provider).toBe('google')
  })
})
