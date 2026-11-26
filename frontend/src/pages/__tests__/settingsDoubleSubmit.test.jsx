/**
 * Settings: a save or a delete already sent ignores a second click, and its button says so,
 * for the webhook and Microsoft CA forms and the SSO, webhook and Microsoft CA deletions.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, act, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../settings/SsoSection', () => ({
  default: ({ setSsoConfirmDelete }) => <button onClick={() => setSsoConfirmDelete({ id: 3, name: 'Corp LDAP' })}>delete-sso</button>,
}))
vi.mock('../settings/WebhooksSection', () => ({
  default: ({ setWebhookConfirmDelete }) => <button onClick={() => setWebhookConfirmDelete({ id: 4, name: 'Chat hook' })}>delete-webhook</button>,
}))
vi.mock('../settings/MicrosoftCASection', async () => ({
  default: ({ setMscaConfirmDelete }) => <button onClick={() => setMscaConfirmDelete({ id: 5, name: 'ADCS' })}>delete-msca</button>,
}))

import './pageRenderingSetup.jsx'
import SettingsPage from '../SettingsPage'
import WebhookForm from '../settings/WebhookForm'
import MscaConnectionForm from '../settings/MscaConnectionForm'
import { ssoService, mscaService, settingsService } from '../../services'

const pending = () => { let done; const p = new Promise((r) => { done = r }); return [p, done] }

describe('a form already sent ignores a second submit', () => {
  it('webhook form', async () => {
    const [p, done] = pending()
    const onSave = vi.fn(() => p)
    const hook = { name: 'Hook', url: 'https://example.com/h', events: [], ca_filter: '', enabled: true, auth_type: 'none' }
    const { container } = render(<WebhookForm webhook={hook} onSave={onSave} onCancel={() => {}} />)
    const form = container.querySelector('form')
    fireEvent.submit(form)
    fireEvent.submit(form)
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(container.querySelector('button[type="submit"]')).toBeDisabled()
    await act(async () => { done() })
    expect(container.querySelector('button[type="submit"]')).not.toBeDisabled()
  })

  it('Microsoft CA form', async () => {
    const [p, done] = pending()
    const onSave = vi.fn(() => p)
    const conn = { id: 4, name: 'ADCS', server: 'adcs.corp.example', auth_method: 'basic', username: 'u', password: '***',
      verify_ssl: true, ca_bundle: '', winrm_host: '', winrm_port: 5986, winrm_use_ssl: true, winrm_verify_ssl: true, winrm_transport: 'kerberos' }
    const { container } = render(<MscaConnectionForm connection={conn} onSave={onSave} onCancel={() => {}} />)
    const form = container.querySelector('form')
    fireEvent.submit(form)
    fireEvent.submit(form)
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(container.querySelector('button[type="submit"]')).toBeDisabled()
    await act(async () => { done() })
  })
})

describe('a deletion already sent ignores a second click', () => {
  it.each([
    ['sso', 'delete-sso', () => { ssoService.deleteProvider = vi.fn(); return ssoService.deleteProvider }],
    ['webhooks', 'delete-webhook', () => { settingsService.deleteWebhook = vi.fn(); return settingsService.deleteWebhook }],
    ['microsoftCA', 'delete-msca', () => { mscaService.delete = vi.fn(); return mscaService.delete }],
  ])('%s', async (tab, opener, spy) => {
    const del = spy()
    const [p, done] = pending()
    del.mockReturnValue(p)
    render(<MemoryRouter initialEntries={[`/settings?tab=${tab}`]}><SettingsPage /></MemoryRouter>)
    await act(async () => { (await screen.findByText(opener)).click() })
    const dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'common.delete' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    expect(del).toHaveBeenCalledTimes(1)
    expect(confirm).toBeDisabled()
    await act(async () => { done({ data: {} }) })
  })
})
