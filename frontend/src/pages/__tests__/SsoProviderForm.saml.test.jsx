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

vi.mock('../../services', () => ({
  ssoService: { getSamlCertificates: vi.fn(() => Promise.resolve({ data: [] })) },
}))

import SsoProviderForm from '../settings/SsoProviderForm'

const PROVIDER = {
  id: 7, name: 'idp', provider_type: 'saml', saml_entity_id: 'https://idp/saml',
  saml_sso_url: 'https://idp/sso', saml_certificate: 'MII...', saml_sign_requests: false,
}

const switchFor = (labelKey) => screen.getByText(labelKey).closest('label').querySelector('[role="switch"]')

const submit = async (onSave) => {
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  return onSave.mock.calls[0][0]
}

describe('SsoProviderForm SAML strict options', () => {
  it('keeps IdP-initiated login off unless the operator turns it on', async () => {
    const onSave = vi.fn()
    render(<SsoProviderForm provider={PROVIDER} onSave={onSave} onCancel={vi.fn()} />)
    expect(switchFor('sso.allowIdpInitiated')).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(switchFor('sso.allowIdpInitiated'))
    const payload = await submit(onSave)
    expect(payload.saml_allow_idp_initiated).toBe(true)
  })

  it('round-trips a provider that already allows it', async () => {
    const onSave = vi.fn()
    render(<SsoProviderForm provider={{ ...PROVIDER, saml_allow_idp_initiated: true }} onSave={onSave} onCancel={vi.fn()} />)
    expect(switchFor('sso.allowIdpInitiated')).toHaveAttribute('aria-checked', 'true')
    const payload = await submit(onSave)
    expect(payload.saml_allow_idp_initiated).toBe(true)
  })

  it('leaves request signing off for a new provider', async () => {
    const onSave = vi.fn()
    render(<SsoProviderForm forcedType="saml" onSave={onSave} onCancel={vi.fn()} />)
    expect(switchFor('sso.signRequests')).toHaveAttribute('aria-checked', 'false')
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
})
