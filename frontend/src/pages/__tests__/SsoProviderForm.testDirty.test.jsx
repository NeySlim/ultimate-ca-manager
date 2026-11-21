/** The provider connection test runs on the saved row: it is off while the form has unsaved edits. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import SsoProviderForm from '../settings/SsoProviderForm'

const LDAP = { id: 5, name: 'Corp LDAP', provider_type: 'ldap', ldap_server: 'ldap.example.com',
  ldap_port: 636, ldap_use_ssl: true, ldap_verify_ssl: true, ldap_bind_dn: 'cn=svc',
  ldap_bind_password: '***' }

const testButton = () => screen.getByRole('button', { name: /sso\.testConnection/ })

describe('SSO provider connection test', () => {
  it('is available while the form matches the saved provider', () => {
    render(<SsoProviderForm provider={LDAP} onSave={vi.fn()} onCancel={() => {}} />)
    expect(testButton()).not.toBeDisabled()
    expect(screen.queryByText('sso.saveBeforeTest')).not.toBeInTheDocument()
  })

  it('is off with a hint once a field is edited, and back when the edit is undone', () => {
    render(<SsoProviderForm provider={LDAP} onSave={vi.fn()} onCancel={() => {}} />)
    fireEvent.change(screen.getByDisplayValue('ldap.example.com'), { target: { value: 'ldap2.example.com' } })
    expect(testButton()).toBeDisabled()
    expect(screen.getByText('sso.saveBeforeTest')).toBeInTheDocument()
    fireEvent.change(screen.getByDisplayValue('ldap2.example.com'), { target: { value: 'ldap.example.com' } })
    expect(testButton()).not.toBeDisabled()
  })
})
