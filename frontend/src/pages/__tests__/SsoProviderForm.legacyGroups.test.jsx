/**
 * SsoProviderForm: a legacy `groups -> attribute` row is rewritten at save, never while typing,
 * and a rewrite that cannot keep both group sources is refused on screen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const showError = vi.fn()
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.attribute ? `${key}:${opts.attribute}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError, showInfo: vi.fn(), showWarning: vi.fn() }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))
vi.mock('../../services', () => ({
  ssoService: {
    getSamlCertificates: vi.fn(() => Promise.resolve({ data: [] })),
    getSamlSpInfo: vi.fn(() => Promise.resolve({ data: { entity_id: 'x', acs_url: 'y', origin_configured: true } })),
  },
  rolesService: { listRoles: vi.fn(() => Promise.resolve({ data: [] })) },
}))

import SsoProviderForm from '../settings/SsoProviderForm'

const SAML = { id: 7, name: 'idp', provider_type: 'saml', saml_entity_id: 'https://idp/saml',
  saml_sso_url: 'https://idp/sso', saml_certificate: 'MII...' }
const OIDC = { id: 8, name: 'oidc', provider_type: 'oauth2', oauth2_client_id: 'c',
  oauth2_auth_url: 'https://a', oauth2_token_url: 'https://t', oauth2_userinfo_url: 'https://u' }

const cases = [['SAML', SAML], ['OIDC', OIDC]]

const open = (provider, attribute_mapping, onSave) => {
  render(<SsoProviderForm provider={{ ...provider, attribute_mapping }} onSave={onSave} onCancel={vi.fn()} />)
  fireEvent.click(screen.getByText('sso.attributeRoleMappingSection'))
}
const save = () => fireEvent.submit(document.querySelector('form'))

beforeEach(() => showError.mockClear())

describe.each(cases)('%s legacy groups row', (_name, provider) => {
  it('leaves the rows as typed while editing, then rewrites the legacy one on save', () => {
    const onSave = vi.fn()
    open(provider, { groups: 'memberOf', Role: 'x' }, onSave)
    fireEvent.change(screen.getByDisplayValue('x'), { target: { value: 'groups' } })
    const keys = screen.getAllByPlaceholderText('e.g., preferred_username').map(i => i.value)
    expect(keys).toEqual(['groups', 'Role'])
    expect(onSave).not.toHaveBeenCalled()
    save()
    expect(onSave.mock.calls[0][0].attribute_mapping).toEqual({ memberOf: 'groups', Role: 'groups' })
  })

  it('reads the backend spacing: a trailing space on the target still counts', () => {
    const onSave = vi.fn()
    open(provider, { groups: 'memberOf', Role: 'groups ' }, onSave)
    save()
    expect(onSave.mock.calls[0][0].attribute_mapping).toEqual({ memberOf: 'groups', Role: 'groups ' })
  })

  it('refuses to save when the legacy attribute already points elsewhere', () => {
    const onSave = vi.fn()
    open(provider, { groups: 'memberOf', memberOf: 'username', Role: 'groups' }, onSave)
    save()
    expect(onSave).not.toHaveBeenCalled()
    expect(showError).toHaveBeenCalledWith('sso.legacyGroupsConflict:memberOf')
  })

  it('leaves a lone legacy row alone', () => {
    const onSave = vi.fn()
    open(provider, { groups: 'memberOf' }, onSave)
    save()
    expect(onSave.mock.calls[0][0].attribute_mapping).toEqual({ groups: 'memberOf' })
  })
})
