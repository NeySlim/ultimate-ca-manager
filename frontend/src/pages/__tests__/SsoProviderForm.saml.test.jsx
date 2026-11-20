/**
 * SsoProviderForm (SAML): the strict-mode options reach the saved payload.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn() }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

let mockSpInfo = { entity_id: 'https://ucm.example.test/api/v2/sso', acs_url: 'https://ucm.example.test/acs', origin_configured: true }
vi.mock('../../services', () => ({
  ssoService: {
    getSamlCertificates: vi.fn(() => Promise.resolve({ data: [] })),
    getSamlSpInfo: vi.fn(() => Promise.resolve({ data: mockSpInfo })),
  },
  rolesService: { listRoles: vi.fn(() => Promise.resolve({ data: [] })) },
}))

import SsoProviderForm from '../settings/SsoProviderForm'

const PROVIDER = {
  id: 7, name: 'idp', provider_type: 'saml', saml_entity_id: 'https://idp/saml',
  saml_sso_url: 'https://idp/sso', saml_certificate: 'MII...', saml_sign_requests: false,
}

const switchFor = (labelKey) => screen.getByText(labelKey).closest('label').querySelector('input[type="checkbox"]')

const submit = async (onSave) => {
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  return onSave.mock.calls[0][0]
}

describe('SsoProviderForm SAML strict options', () => {
  it('keeps IdP-initiated login off unless the operator turns it on', async () => {
    const onSave = vi.fn()
    render(<SsoProviderForm provider={PROVIDER} onSave={onSave} onCancel={vi.fn()} />)
    expect(switchFor('sso.allowIdpInitiated')).not.toBeChecked()
    fireEvent.click(switchFor('sso.allowIdpInitiated'))
    const payload = await submit(onSave)
    expect(payload.saml_allow_idp_initiated).toBe(true)
  })

  it('round-trips a provider that already allows it', async () => {
    const onSave = vi.fn()
    render(<SsoProviderForm provider={{ ...PROVIDER, saml_allow_idp_initiated: true }} onSave={onSave} onCancel={vi.fn()} />)
    expect(switchFor('sso.allowIdpInitiated')).toBeChecked()
    const payload = await submit(onSave)
    expect(payload.saml_allow_idp_initiated).toBe(true)
  })

  it('leaves request signing off for a new provider', async () => {
    const onSave = vi.fn()
    render(<SsoProviderForm forcedType="saml" onSave={onSave} onCancel={vi.fn()} />)
    expect(switchFor('sso.signRequests')).not.toBeChecked()
    const payload = await submit(onSave)
    expect(payload.saml_sign_requests).toBe(false)
  })

  it('asks for an unspecified NameID unless the provider chose a format', async () => {
    const onSave = vi.fn()
    const { unmount } = render(<SsoProviderForm forcedType="saml" onSave={onSave} onCancel={vi.fn()} />)
    expect((await submit(onSave)).saml_name_id_format).toBe('urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified')
    unmount()
    const persistent = 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent'
    const onSave2 = vi.fn()
    render(<SsoProviderForm provider={{ ...PROVIDER, saml_name_id_format: persistent }} onSave={onSave2} onCancel={vi.fn()} />)
    expect((await submit(onSave2)).saml_name_id_format).toBe(persistent)
  })

  it('shows the SP URLs the server computes and explains the NameID choice', async () => {
    mockSpInfo = { entity_id: 'https://ucm.example.test/api/v2/sso', acs_url: 'https://ucm.example.test/acs', origin_configured: true }
    render(<SsoProviderForm provider={PROVIDER} onSave={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.click(screen.getByText('sso.spSection'))
    expect(await screen.findByText('https://ucm.example.test/api/v2/sso')).toBeInTheDocument()
    expect(screen.queryByText('sso.spOriginNotConfigured')).not.toBeInTheDocument()
    expect(screen.getByText('sso.nameIdFormatHelp')).toBeInTheDocument()
  })

  it('warns when no Base URL or FQDN fixes the SP URLs', async () => {
    mockSpInfo = { entity_id: 'https://10.0.0.5:8443/api/v2/sso', origin_configured: false }
    render(<SsoProviderForm provider={PROVIDER} onSave={vi.fn()} onCancel={vi.fn()} />)
    expect(await screen.findByText('sso.spOriginNotConfigured')).toBeInTheDocument()
  })

  it('adds a groups row for a common attribute only when the operator clicks', async () => {
    const onSave = vi.fn()
    render(<SsoProviderForm provider={{ ...PROVIDER, attribute_mapping: { email: 'email' } }}
      onSave={onSave} onCancel={vi.fn()} />)
    fireEvent.click(screen.getByText('sso.attributeRoleMappingSection'))
    expect(screen.getByText('sso.samlGroupShortcutKeycloakRoles')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /urn:oid:1\.3\.6\.1\.4\.1\.5923\.1\.5\.1\.1/ }))
    fireEvent.click(screen.getByRole('button', { name: /^Role/ }))
    expect(screen.getByDisplayValue('urn:oid:1.3.6.1.4.1.5923.1.5.1.1')).toBeInTheDocument()
    const payload = await submit(onSave)
    expect(payload.attribute_mapping).toEqual({
      email: 'email', 'urn:oid:1.3.6.1.4.1.5923.1.5.1.1': 'groups', Role: 'groups' })
  })

  it('saves no groups row the operator did not add', async () => {
    const onSave = vi.fn()
    render(<SsoProviderForm provider={{ ...PROVIDER, attribute_mapping: { email: 'email' } }}
      onSave={onSave} onCancel={vi.fn()} />)
    expect((await submit(onSave)).attribute_mapping).toEqual({ email: 'email' })
  })
})
