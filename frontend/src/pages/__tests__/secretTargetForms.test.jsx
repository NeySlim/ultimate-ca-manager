/**
 * Forms holding a saved secret: moving its target (server, URL, port, TLS,
 * account) asks for the secret again before anything is sent, as the server
 * refuses to send a saved secret to a new target.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import { ProviderModal } from '../HSMPage'
import WebhookForm from '../settings/WebhookForm'
import DnsProviderForm from '../acme/DnsProviderForm'
import MscaConnectionForm from '../settings/MscaConnectionForm'
import SsoProviderForm from '../settings/SsoProviderForm'

const MESSAGE = 'common.secretRequiredForTarget'
const submit = (container) => fireEvent.submit(container.querySelector('form'))

describe('HSM provider', () => {
  const PROVIDER = { id: 1, name: 'Bao', provider_type: 'openbao', openbao_url: 'https://bao.example',
    openbao_token: '***', openbao_mount_path: 'transit', openbao_tls_skip_verify: false }

  it('asks for the token when the URL moves', async () => {
    const onSave = vi.fn()
    render(<ProviderModal provider={PROVIDER} hsmStatus={null} onSave={onSave} onClose={() => {}} />)
    fireEvent.change(screen.getByDisplayValue('https://bao.example'), { target: { value: 'https://bao.attacker.example' } })
    expect(screen.getByText(MESSAGE)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await new Promise(r => setTimeout(r, 20))
    expect(onSave).not.toHaveBeenCalled()

    // The modal renders in a portal
    const token = document.querySelector('input[autocomplete="off"]')
    fireEvent.change(token, { target: { value: 'typed' } })
    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0][0].config).toMatchObject({ url: 'https://bao.attacker.example', token: 'typed' })
  })
})

describe('Webhook', () => {
  const HOOK = { id: 3, name: 'Hook', url: 'https://hooks.example.com/a', events: [], auth_type: 'bearer',
    auth_token_set: true }

  it('asks for the token when the URL moves', () => {
    const onSave = vi.fn()
    const { container } = render(<WebhookForm webhook={HOOK} onSave={onSave} onCancel={() => {}} />)
    fireEvent.change(screen.getByDisplayValue('https://hooks.example.com/a'),
      { target: { value: 'https://hooks.attacker.example/a' } })
    submit(container)
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByText(MESSAGE)).toBeInTheDocument()
  })

  it('keeps the saved token when the URL stays', () => {
    const onSave = vi.fn()
    const { container } = render(<WebhookForm webhook={HOOK} onSave={onSave} onCancel={() => {}} />)
    fireEvent.change(screen.getByDisplayValue('Hook'), { target: { value: 'Renamed' } })
    submit(container)
    expect(onSave).toHaveBeenCalledWith(expect.not.objectContaining({ auth_token: expect.anything() }))
  })
})

describe('Webhook with custom headers set through the API', () => {
  const HOOK = { id: 6, name: 'Hdr', url: 'https://hooks.example.com/h', events: [], auth_type: 'none',
    custom_headers_set: true }

  it('moves the URL only once the headers are dropped', () => {
    const onSave = vi.fn()
    const { container } = render(<WebhookForm webhook={HOOK} onSave={onSave} onCancel={() => {}} />)
    expect(screen.getByText('webhooks.customHeadersSet')).toBeInTheDocument()
    fireEvent.change(screen.getByDisplayValue('https://hooks.example.com/h'),
      { target: { value: 'https://hooks.example.com/moved' } })
    submit(container)
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByText('webhooks.customHeadersFollowUrl')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('webhooks.dropCustomHeaders'))
    submit(container)
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      url: 'https://hooks.example.com/moved', custom_headers: {} }))
    expect(onSave.mock.calls[0][0]).not.toHaveProperty('drop_custom_headers')
  })

  it('keeps the headers when the URL stays', () => {
    const onSave = vi.fn()
    const { container } = render(<WebhookForm webhook={HOOK} onSave={onSave} onCancel={() => {}} />)
    submit(container)
    expect(onSave.mock.calls[0][0]).not.toHaveProperty('custom_headers')
  })
})

describe('DNS provider', () => {
  const TYPES = [{ type: 'powerdns', name: 'PowerDNS', credentials_schema: [
    { name: 'server_url', label: 'Server URL', type: 'text', required: true },
    { name: 'api_key', label: 'API Key', type: 'password', required: true },
  ] }]
  const PROVIDER = { id: 2, name: 'pdns', provider_type: 'powerdns', credential_keys: ['server_url', 'api_key'] }

  it('asks for the saved key when the server is typed', () => {
    const onSubmit = vi.fn()
    const { container } = render(<DnsProviderForm provider={PROVIDER} providerTypes={TYPES}
                                                  onSubmit={onSubmit} onCancel={() => {}} />)
    const [server, key] = container.querySelectorAll('input[autocomplete="off"], input[autocomplete="new-password"]')
    fireEvent.change(server, { target: { value: 'https://pdns.attacker.example' } })
    expect(screen.getByText(MESSAGE)).toBeInTheDocument()
    submit(container)
    expect(onSubmit).not.toHaveBeenCalled()
    fireEvent.change(key, { target: { value: 'typed' } })
    submit(container)
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      credentials: { server_url: 'https://pdns.attacker.example', api_key: 'typed' } }))
  })
})

describe('Microsoft CA', () => {
  const CONNECTION = { id: 4, name: 'ADCS', server: 'adcs.corp.example', auth_method: 'basic', username: 'u',
    password: '***', use_ssl: true, verify_ssl: true, ca_bundle: '', winrm_host: '', winrm_port: 5986,
    winrm_use_ssl: true, winrm_verify_ssl: true, winrm_transport: 'kerberos', winrm_username: '',
    winrm_password: null }

  it('asks for the password when the server moves, not for other edits', () => {
    const onSave = vi.fn()
    const { container } = render(<MscaConnectionForm connection={CONNECTION} onSave={onSave} onCancel={() => {}} />)
    fireEvent.change(screen.getByDisplayValue('ADCS'), { target: { value: 'ADCS 2' } })
    submit(container)
    expect(onSave).toHaveBeenCalledTimes(1)
    fireEvent.change(screen.getByDisplayValue('adcs.corp.example'), { target: { value: 'adcs.attacker.example' } })
    expect(screen.getByText(MESSAGE)).toBeInTheDocument()
    submit(container)
    expect(onSave).toHaveBeenCalledTimes(1)
  })
})

describe('SSO provider', () => {
  const LDAP = { id: 5, name: 'Corp LDAP', provider_type: 'ldap', ldap_server: 'ldap.example.com',
    ldap_port: 636, ldap_use_ssl: true, ldap_verify_ssl: true, ldap_bind_dn: 'cn=svc',
    ldap_bind_password: '***' }

  it('asks for the bind password when the server moves', () => {
    const onSave = vi.fn()
    const { container } = render(<SsoProviderForm provider={LDAP} onSave={onSave} onCancel={() => {}} />)
    fireEvent.change(screen.getByDisplayValue('ldap.example.com'), { target: { value: 'ldap.attacker.example' } })
    expect(screen.getByText(MESSAGE)).toBeInTheDocument()
    submit(container)
    expect(onSave).not.toHaveBeenCalled()
    fireEvent.change(screen.getByDisplayValue('ldap.attacker.example'), { target: { value: 'ldap.example.com' } })
    submit(container)
    expect(onSave).toHaveBeenCalledTimes(1)
  })
})
