/** Microsoft CA form: every field shown has an effect on the server. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import MscaConnectionForm from '../settings/MscaConnectionForm'

const BASE = { id: 4, name: 'ADCS', server: 'adcs.corp.example', auth_method: 'basic', username: 'u',
  password: '***', verify_ssl: true, ca_bundle: '', winrm_host: '', winrm_port: 5986,
  winrm_use_ssl: true, winrm_verify_ssl: true, winrm_transport: 'kerberos' }

const renderForm = (over = {}) => render(
  <MscaConnectionForm connection={{ ...BASE, ...over }} onSave={vi.fn()} onCancel={() => {}} />)

describe('Microsoft CA form fields', () => {
  it('offers the CA bundle while TLS verification is on', () => {
    renderForm({ verify_ssl: true })
    expect(screen.getByText('msca.caBundle')).toBeInTheDocument()
  })

  it('hides the CA bundle while TLS verification is off (it is not used then)', () => {
    renderForm({ verify_ssl: false })
    expect(screen.queryByText('msca.caBundle')).not.toBeInTheDocument()
  })
})
