/**
 * SSO provisioning: the form says who can sign in, keeps an empty default role
 * as "none" instead of turning it into viewer, and offers StartTLS for LDAP.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import SsoProviderForm from '../settings/SsoProviderForm'

const OIDC = { id: 9, name: 'IdP', provider_type: 'oauth2', oauth2_client_id: 'ucm',
  oauth2_client_secret: '***', default_role: 'viewer', role_mapping: {} }
const submit = (container) => fireEvent.submit(container.querySelector('form'))

describe('SSO provisioning notice', () => {
  it('warns that everyone gets in when there is no rule', () => {
    render(<SsoProviderForm provider={OIDC} onSave={vi.fn()} onCancel={() => {}} />)
    expect(screen.getByText('sso.provisioningNoRulesNotice')).toBeInTheDocument()
  })

  it('says unmatched users are refused once a rule exists', () => {
    render(<SsoProviderForm provider={{ ...OIDC, role_mapping: { admins: 'admin' } }} onSave={vi.fn()} onCancel={() => {}} />)
    expect(screen.queryByText('sso.provisioningNoRulesNotice')).not.toBeInTheDocument()
  })

  it('keeps an empty default role empty on save', () => {
    const onSave = vi.fn()
    const { container } = render(<SsoProviderForm provider={{ ...OIDC, default_role: null }} onSave={onSave} onCancel={() => {}} />)
    expect(screen.getByText('sso.provisioningNobodyNotice')).toBeInTheDocument()
    submit(container)
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave.mock.calls[0][0].default_role).toBe('')
  })
})

describe('LDAP transport', () => {
  const LDAP = { id: 5, name: 'Corp LDAP', provider_type: 'ldap', ldap_server: 'ldap.example.com',
    ldap_port: 389, ldap_use_ssl: false, ldap_start_tls: false, ldap_verify_ssl: true,
    ldap_bind_dn: 'cn=svc', ldap_bind_password: '***', default_role: 'viewer' }

  it('warns about plain LDAP and sends ldap_start_tls', () => {
    const onSave = vi.fn()
    const { container } = render(<SsoProviderForm provider={{ ...LDAP, ldap_start_tls: true }} onSave={onSave} onCancel={() => {}} />)
    expect(screen.getByText('sso.ldapStartTls')).toBeInTheDocument()
    expect(screen.queryByText('sso.ldapPlainWarning')).not.toBeInTheDocument()
    submit(container)
    expect(onSave.mock.calls[0][0].ldap_start_tls).toBe(true)
  })

  it('shows the plain LDAP warning without TLS', () => {
    render(<SsoProviderForm provider={LDAP} onSave={vi.fn()} onCancel={() => {}} />)
    expect(screen.getByText('sso.ldapPlainWarning')).toBeInTheDocument()
  })
})
