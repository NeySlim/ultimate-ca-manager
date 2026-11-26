/**
 * The OAuth2 provider is saved as the API gave it: a stored empty provider is not
 * rewritten to the preset the card shows, which the API would refuse to an operator
 * as a move of the SMTP target. Choosing OAuth2 anew, or saving with admin:settings,
 * takes the provider shown.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/EmailSection', () => ({
  default: ({ settings, updateSetting, handleSave }) => (
    <div>
      <div data-testid="smtp-method">{settings.smtp_auth_method}</div>
      <button onClick={() => updateSetting('smtp_auth_method', 'oauth2')}>pick-oauth2</button>
      <button onClick={() => updateSetting('smtp_oauth_client_secret', 'typed-secret')}>type-secret</button>
      <button onClick={() => handleSave('email')}>save-email</button>
    </div>
  ),
}))

const granted = vi.hoisted(() => ({ perms: [] }))
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: (p) => granted.perms.includes(p),
    canRead: () => true, canWrite: () => true, canDelete: () => true, isAdmin: () => false,
    permissions: granted.perms,
  }),
}))

import { notificationSpies } from './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { settingsService } from '../../services/settings.service'

function mockEmailApi(emailData) {
  settingsService.getAll = vi.fn().mockResolvedValue({ data: {} })
  settingsService.getEmailSettings = vi.fn().mockResolvedValue({ data: emailData })
  settingsService.updateEmailSettings = vi.fn().mockResolvedValue({ data: {} })
  settingsService.getSmtpOAuthProviders = vi.fn().mockResolvedValue({ data: { providers: {} } })
}

async function clickSave(emailData, before) {
  mockEmailApi(emailData)
  render(<MemoryRouter initialEntries={['/settings?tab=email']}><SettingsPage /></MemoryRouter>)
  await waitFor(() => expect(screen.getByTestId('smtp-method').textContent).toBe(emailData.smtp_auth_method))
  if (before) await act(async () => { screen.getByText(before).click() })
  await act(async () => { screen.getByText('save-email').click() })
}

async function save(emailData, before) {
  await clickSave(emailData, before)
  await waitFor(() => expect(settingsService.updateEmailSettings).toHaveBeenCalled())
  return settingsService.updateEmailSettings.mock.calls[0][0]
}

describe('SettingsPage: SMTP OAuth2 provider', () => {
  beforeEach(() => { vi.clearAllMocks(); granted.perms = [] })

  it('saves a stored empty provider unchanged for an operator, whose fields are locked', async () => {
    const body = await save({ smtp_auth: true, smtp_auth_method: 'oauth2', smtp_oauth_provider: '' })
    expect(body.smtp_oauth_provider).toBe('')
  })

  it('saves the provider the card shows for a stored empty one when admin:settings may move it', async () => {
    granted.perms = ['admin:settings']
    const body = await save({ smtp_auth: true, smtp_auth_method: 'oauth2', smtp_oauth_provider: '' })
    expect(body.smtp_oauth_provider).toBe('google')
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

  it('asks for the saved client secret before sending the shown provider for a stored empty one', async () => {
    granted.perms = ['admin:settings']
    const stored = { smtp_auth: true, smtp_auth_method: 'oauth2', smtp_oauth_provider: '',
      has_oauth_client_secret: true }
    await clickSave(stored)
    await waitFor(() => expect(notificationSpies.showError).toHaveBeenCalledWith('common.secretRequiredForTarget'))
    expect(settingsService.updateEmailSettings).not.toHaveBeenCalled()

    await act(async () => { screen.getByText('type-secret').click() })
    await act(async () => { screen.getByText('save-email').click() })
    await waitFor(() => expect(settingsService.updateEmailSettings).toHaveBeenCalled())
    const body = settingsService.updateEmailSettings.mock.calls[0][0]
    expect(body.smtp_oauth_provider).toBe('google')
    expect(body.smtp_oauth_client_secret).toBe('typed-secret')
  })
})
