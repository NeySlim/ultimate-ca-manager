/**
 * Testing a saved Microsoft CA connection sends the form's values, not just its id.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'

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
})
