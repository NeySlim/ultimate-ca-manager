/**
 * SsoProviderForm: each OAuth2 preset gives a provider that signs in (issuer and ID token
 * verification included), and switching preset puts back what the previous one set.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

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
  ssoService: {},
  rolesService: { listRoles: vi.fn(() => Promise.resolve({ data: [] })) },
}))

import SsoProviderForm from '../settings/SsoProviderForm'

const ENTRA_ISSUER = 'https://login.microsoftonline.com/{tenant}/v2.0'

const open = () => {
  const onSave = vi.fn()
  render(<SsoProviderForm forcedType="oauth2" onSave={onSave} onCancel={vi.fn()} />)
  return () => {
    fireEvent.submit(document.querySelector('form'))
    expect(onSave).toHaveBeenCalled()
    return onSave.mock.calls.at(-1)[0]
  }
}
const preset = (label) => fireEvent.click(screen.getByText(label))

describe('OAuth2 presets', () => {
  it('Entra sets the issuer with the same {tenant} as its URLs, verification on', () => {
    const saved = open()
    preset('sso.oauthProviders.azure')
    const data = saved()
    expect(data.oauth2_issuer).toBe(ENTRA_ISSUER)
    expect(data.oauth2_auth_url).toContain('/{tenant}/')
    expect(data.id_token_verify).toBe(true)
    expect(screen.getByText('sso.tenantPlaceholderHint')).toBeInTheDocument()
  })

  it('Google sets the issuer of its discovery document, verification on', () => {
    const saved = open()
    preset('sso.oauthProviders.google')
    const data = saved()
    expect(data.oauth2_issuer).toBe('https://accounts.google.com')
    expect(data.id_token_verify).toBe(true)
    expect(screen.queryByText('sso.idTokenVerifyIssuerMissing')).toBeNull()
  })

  it('GitHub turns ID token verification off, says why, and maps login to the username', () => {
    const saved = open()
    preset('sso.oauthProviders.github')
    expect(screen.getByText('sso.githubNotOidc')).toBeInTheDocument()
    const data = saved()
    expect(data.id_token_verify).toBe(false)
    expect(data.oauth2_issuer).toBe('')
    expect(data.oauth2_scopes).not.toContain('openid')
    expect(data.attribute_mapping).toEqual({ login: 'username' })
  })

  it('switching from GitHub to Google turns verification back on', () => {
    const saved = open()
    preset('sso.oauthProviders.github')
    preset('sso.oauthProviders.google')
    const data = saved()
    expect(data.id_token_verify).toBe(true)
    expect(data.oauth2_issuer).toBe('https://accounts.google.com')
    expect(data.attribute_mapping).toEqual({})
    expect(screen.queryByText('sso.githubNotOidc')).toBeNull()
  })

  it('switching from Entra to GitHub clears the Entra issuer', () => {
    const saved = open()
    preset('sso.oauthProviders.azure')
    preset('sso.oauthProviders.github')
    const data = saved()
    expect(data.oauth2_issuer).toBe('')
    expect(data.id_token_verify).toBe(false)
  })

  it('switching to Custom puts back what the previous preset set, keeps what was typed', () => {
    const saved = open()
    preset('sso.oauthProviders.github')
    preset('sso.oauth2PresetCustom')
    expect(saved().id_token_verify).toBe(true)
    expect(saved().attribute_mapping).toEqual({})

    preset('sso.oauthProviders.azure')
    const issuer = screen.getByDisplayValue(ENTRA_ISSUER)
    fireEvent.change(issuer, { target: { value: 'https://login.microsoftonline.com/tenant-example/v2.0' } })
    preset('sso.oauth2PresetCustom')
    expect(saved().oauth2_issuer).toBe('https://login.microsoftonline.com/tenant-example/v2.0')
  })
})
