/**
 * Deleting an SSO provider or a webhook asks a question of its own, as the mockup's
 * confirmations do ("Révoquer ce certificat ?"), not the generic "delete this?".
 * The sections are stubbed: the test drives their delete callback directly.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/SsoSection', () => ({
  default: ({ setSsoConfirmDelete }) => (
    <button onClick={() => setSsoConfirmDelete({ id: 3, name: 'Corp LDAP' })}>delete-sso</button>
  ),
}))
vi.mock('../settings/WebhooksSection', () => ({
  default: ({ setWebhookConfirmDelete }) => (
    <button onClick={() => setWebhookConfirmDelete({ id: 4, name: 'Chat hook' })}>delete-webhook</button>
  ),
}))

import './pageRenderingSetup.jsx'
import SettingsPage from '../SettingsPage'

const renderAt = (tab) => render(
  <MemoryRouter initialEntries={[`/settings?tab=${tab}`]}>
    <SettingsPage />
  </MemoryRouter>,
)

describe('SettingsPage delete confirmations', () => {
  it('titles the SSO provider deletion with its own question, the named one in the body', async () => {
    renderAt('sso')
    await act(async () => { (await screen.findByText('delete-sso')).click() })
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('sso.deleteTitle')
    expect(dialog).not.toHaveTextContent('common.confirmDelete')
    expect(dialog).toHaveTextContent('sso.deleteConfirm')
  })

  it('titles the webhook deletion with its own question', async () => {
    renderAt('webhooks')
    await act(async () => { (await screen.findByText('delete-webhook')).click() })
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('webhooks.deleteTitle')
    expect(dialog).not.toHaveTextContent('common.confirmDelete')
  })
})
