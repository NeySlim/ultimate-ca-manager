/**
 * Testing a saved Microsoft CA connection sends the form's values, not just its id.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { notificationSpies } from './pageRenderingSetup.jsx'

import { apiClient } from '../../services/apiClient'
import MscaConnectionForm from '../settings/MscaConnectionForm'

const CONNECTION = { id: 4, name: 'ADCS', server: 'adcs.corp.example', auth_method: 'basic', username: 'u',
  password: '***', use_ssl: true, verify_ssl: true, ca_bundle: '', winrm_host: '', winrm_port: 5986,
  winrm_use_ssl: true, winrm_verify_ssl: true, winrm_transport: 'kerberos', winrm_username: '',
  winrm_password: null }

const test = () => fireEvent.click(screen.getByText('msca.testConnection'))
const posted = () => apiClient.post.mock.calls.filter(([url]) => url === '/microsoft-cas/4/test')

describe('MscaConnectionForm: test connection', () => {
  beforeEach(() => {
    apiClient.post.mockClear()
    apiClient.post.mockResolvedValue({ data: { templates: [] } })
  })

  it('tests the values on the form', async () => {
    render(<MscaConnectionForm connection={CONNECTION} onSave={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByLabelText('msca.caName'), { target: { value: 'Issuing CA 2' } })
    test()
    await waitFor(() => expect(posted()).toHaveLength(1))
    const body = posted()[0][1]
    expect(body).toMatchObject({ server: 'adcs.corp.example', username: 'u', ca_name: 'Issuing CA 2' })
    expect(body.password).toBeUndefined()
  })

  it('asks for the password again when the server moves, and sends nothing', async () => {
    render(<MscaConnectionForm connection={CONNECTION} onSave={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByDisplayValue('adcs.corp.example'), { target: { value: 'other.example' } })
    test()
    await new Promise((r) => setTimeout(r, 20))
    expect(posted()).toHaveLength(0)
  })

  it("shows the server's refusal of a Kerberos test it may not run", async () => {
    const message = 'Setting a Kerberos keytab or principal, or moving a connection or test that uses one, '
      + 'requires the admin:system permission'
    apiClient.post.mockRejectedValueOnce(Object.assign(new Error(message), { status: 403 }))
    notificationSpies.showError.mockClear()
    const connection = { ...CONNECTION, auth_method: 'kerberos', kerberos_principal: 'svc@CORP.EXAMPLE',
      kerberos_keytab_path: '/srv/keytabs/ucm.keytab' }
    render(<MscaConnectionForm connection={connection} onSave={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByDisplayValue('adcs.corp.example'), { target: { value: 'other.example' } })
    test()
    await waitFor(() => expect(notificationSpies.showError).toHaveBeenCalledWith(message))
    expect(posted()[0][1]).toMatchObject({ server: 'other.example', kerberos_keytab_path: '/srv/keytabs/ucm.keytab' })
  })
})

describe('MscaConnectionForm: test the admin channel', () => {
  beforeEach(() => {
    apiClient.post.mockClear()
    apiClient.post.mockResolvedValue({ data: { templates: [] } })
  })

  it('sends the Kerberos keytab and principal of the form', async () => {
    const connection = { ...CONNECTION, auth_method: 'kerberos', kerberos_principal: 'svc@CORP.EXAMPLE',
      kerberos_keytab_path: '/srv/keytabs/ucm.keytab', winrm_enabled: true }
    render(<MscaConnectionForm connection={connection} onSave={() => {}} onCancel={() => {}} />)
    fireEvent.click(screen.getByText('msca.testAdminChannel'))
    const channel = () => apiClient.post.mock.calls.filter(([url]) => url === '/microsoft-cas/4/admin-channel/test')
    await waitFor(() => expect(channel()).toHaveLength(1))
    expect(channel()[0][1]).toMatchObject({ kerberos_principal: 'svc@CORP.EXAMPLE',
      kerberos_keytab_path: '/srv/keytabs/ucm.keytab' })
  })
})
