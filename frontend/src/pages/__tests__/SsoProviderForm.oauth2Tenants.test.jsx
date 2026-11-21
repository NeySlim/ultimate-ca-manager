/**
 * SsoProviderForm: the accepted Entra tenants are shown with the Entra preset or once set, saved
 * as a list, and a provider without them saves an empty list. GUIDs invented.
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

const TENANT_A = '0f1e2d3c-4b5a-4968-8778-a6b5c4d3e2f1'
const TENANT_B = '1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'

const open = (provider) => {
  const onSave = vi.fn()
  render(<SsoProviderForm provider={provider} forcedType="oauth2" onSave={onSave} onCancel={vi.fn()} />)
  return () => {
    fireEvent.submit(document.querySelector('form'))
    return onSave.mock.calls.at(-1)[0]
  }
}
const field = () => screen.queryByLabelText('sso.oidcTenants')

describe('Accepted Entra tenants', () => {
  it('is hidden for a custom provider, which saves none', () => {
    const saved = open()
    expect(field()).toBeNull()
    expect(saved().oauth2_tenants).toEqual([])
  })

  it('shows with the Entra preset and saves one tenant per line as a list', () => {
    const saved = open()
    fireEvent.click(screen.getByText('sso.oauthProviders.azure'))
    fireEvent.change(field(), { target: { value: `${TENANT_A}\n ${TENANT_B}, \n` } })
    expect(saved().oauth2_tenants).toEqual([TENANT_A, TENANT_B])
  })

  it('shows the saved tenants of a provider, and warns when verification is off', () => {
    const saved = open({ id: 3, provider_type: 'oauth2', oauth2_tenants: [TENANT_A], id_token_verify: false })
    expect(field().value).toBe(TENANT_A)
    expect(screen.getByText('sso.oidcTenantsNeedVerify')).toBeInTheDocument()
    expect(saved().oauth2_tenants).toEqual([TENANT_A])
  })

  it('saves the tenants whose roles are honoured as a list', () => {
    const saved = open({ id: 3, provider_type: 'oauth2', oauth2_tenants: [TENANT_A, TENANT_B],
      oauth2_role_tenants: [TENANT_A], id_token_verify: true })
    const roles = screen.getByLabelText('sso.oidcRoleTenants')
    expect(roles.value).toBe(TENANT_A)
    fireEvent.change(roles, { target: { value: `${TENANT_A}\n${TENANT_B}` } })
    expect(saved().oauth2_role_tenants).toEqual([TENANT_A, TENANT_B])
  })

  it('warns that role rules with no honoured tenant refuse every sign-in', () => {
    const warning = () => screen.queryByText('sso.oidcRoleTenantsNoneWarning')
    open({ id: 3, provider_type: 'oauth2', oauth2_tenants: [TENANT_A, TENANT_B],
      oauth2_role_tenants: [], role_mapping: { 'UCM.Admin': 'admin' }, id_token_verify: true })
    expect(warning()).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('sso.oidcRoleTenants'), { target: { value: TENANT_A } })
    expect(warning()).toBeNull()
  })

  it('does not warn without role rules, nor for a provider without tenants', () => {
    const warning = () => screen.queryByText('sso.oidcRoleTenantsNoneWarning')
    const { unmount } = render(<SsoProviderForm forcedType="oauth2" onSave={vi.fn()} onCancel={vi.fn()}
      provider={{ id: 3, provider_type: 'oauth2', oauth2_tenants: [TENANT_A], oauth2_role_tenants: [],
        role_mapping: {}, id_token_verify: true }} />)
    expect(warning()).toBeNull()
    unmount()
    open({ id: 4, provider_type: 'oauth2', oauth2_issuer: 'https://login.microsoftonline.com/x/v2.0',
      oauth2_role_tenants: [], role_mapping: { 'UCM.Admin': 'admin' }, id_token_verify: true })
    expect(warning()).toBeNull()
  })

  it('shows a stored value the server could not read as it is', () => {
    open({ id: 3, provider_type: 'oauth2', oauth2_tenants: 'not-a-list', id_token_verify: true })
    expect(field().value).toBe('not-a-list')
  })
})
