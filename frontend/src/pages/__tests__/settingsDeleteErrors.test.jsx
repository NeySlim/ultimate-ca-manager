/**
 * Settings: a refused deletion or switch of an SSO provider or a webhook shows the server's reason
 * (busy, permission, already gone), and the generic text only when the server gave none.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, fireEvent, within, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/SsoSection', () => ({
  default: ({ setSsoConfirmDelete, handleSsoToggle }) => <>
    <button onClick={() => setSsoConfirmDelete({ id: 3, name: 'Corp LDAP' })}>delete-sso</button>
    <button onClick={() => handleSsoToggle({ id: 3, name: 'Corp LDAP', enabled: true })}>toggle-sso</button>
  </>,
}))
vi.mock('../settings/WebhooksSection', () => ({
  default: ({ setWebhookConfirmDelete, handleWebhookToggle }) => <>
    <button onClick={() => setWebhookConfirmDelete({ id: 4, name: 'Chat hook' })}>delete-webhook</button>
    <button onClick={() => handleWebhookToggle({ id: 4, name: 'Chat hook', enabled: true })}>toggle-webhook</button>
  </>,
}))

import { notificationSpies } from './pageRenderingSetup.jsx'
import SettingsPage from '../SettingsPage'
import { ssoService, settingsService } from '../../services'

const BUSY = 'The database is busy, nothing was written: retry'
const refused = (message) => Object.assign(new Error(message), { status: 503 })

const open = async (tab) => {
  render(<MemoryRouter initialEntries={[`/settings?tab=${tab}`]}><SettingsPage /></MemoryRouter>)
}

describe('a refused SSO or webhook action says why', () => {
  beforeEach(() => { notificationSpies.showError.mockClear() })

  it.each([
    ['sso', 'delete-sso', () => { ssoService.deleteProvider = vi.fn(); return ssoService.deleteProvider }, 'sso.deleteFailed'],
    ['webhooks', 'delete-webhook', () => { settingsService.deleteWebhook = vi.fn(); return settingsService.deleteWebhook }, 'webhooks.deleteFailed'],
  ])('deletion: %s', async (tab, opener, spy, fallback) => {
    const del = spy()
    del.mockRejectedValueOnce(refused(BUSY))
    await open(tab)
    await act(async () => { (await screen.findByText(opener)).click() })
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(notificationSpies.showError).toHaveBeenCalledWith(BUSY))
    // No reason from the server: the generic text
    del.mockRejectedValueOnce(new Error(''))
    await act(async () => { (await screen.findByText(opener)).click() })
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(notificationSpies.showError).toHaveBeenLastCalledWith(fallback))
  })

  it.each([
    ['sso', 'toggle-sso', () => { ssoService.toggleProvider = vi.fn(); return ssoService.toggleProvider }],
    ['webhooks', 'toggle-webhook', () => { settingsService.toggleWebhook = vi.fn(); return settingsService.toggleWebhook }],
  ])('switch: %s', async (tab, opener, spy) => {
    spy().mockRejectedValueOnce(refused(BUSY))
    await open(tab)
    await act(async () => { (await screen.findByText(opener)).click() })
    await waitFor(() => expect(notificationSpies.showError).toHaveBeenCalledWith(BUSY))
  })
})
