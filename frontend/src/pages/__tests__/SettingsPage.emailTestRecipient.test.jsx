/**
 * #386: the test email goes to the signed-in user by default, and a typed
 * recipient survives the reload that saving the settings triggers.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/EmailSection', () => ({
  default: ({ settings, updateSetting, handleTestEmail, handleSave, defaultTestRecipient }) => (
    <div>
      <button onClick={() => updateSetting('_testRecipient', 'ops@example.com')}>set-recipient</button>
      <button onClick={handleTestEmail}>run-test-email</button>
      <button onClick={() => handleSave('email')}>save</button>
      <div data-testid="recipient">{settings._testRecipient || ''}</div>
      <div data-testid="placeholder">{defaultTestRecipient || ''}</div>
    </div>
  ),
}))

import './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { settingsService } from '../../services/settings.service'

const renderSettings = () => render(
  <MemoryRouter initialEntries={['/settings?tab=email']}>
    <SettingsPage />
  </MemoryRouter>,
)

const click = async (label) => { await act(async () => { screen.getByText(label).click() }) }

describe('#386 test email recipient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    settingsService.testEmail = vi.fn().mockResolvedValue({})
    settingsService.getAll = vi.fn().mockResolvedValue({ data: {} })
    settingsService.getEmailSettings = vi.fn().mockResolvedValue({ data: { from_email: 'noreply@example.com' } })
  })

  it('defaults to the signed-in user, not the sender', async () => {
    renderSettings()
    await waitFor(() => expect(screen.getByTestId('placeholder').textContent).toBe('admin@test.com'))
    await click('run-test-email')
    expect(settingsService.testEmail).toHaveBeenCalledWith('admin@test.com')
  })

  it('keeps a typed recipient after saving', async () => {
    settingsService.updateEmailSettings = vi.fn().mockResolvedValue({})
    renderSettings()
    // The sections show once every first load has answered, not when the email one is sent
    await screen.findByText('set-recipient')
    await click('set-recipient')
    const loads = settingsService.getEmailSettings.mock.calls.length
    await click('save')
    await waitFor(() => expect(settingsService.getEmailSettings.mock.calls.length).toBeGreaterThan(loads))
    expect(screen.getByTestId('recipient').textContent).toBe('ops@example.com')
    await click('run-test-email')
    expect(settingsService.testEmail).toHaveBeenCalledWith('ops@example.com')
  })
})
