/**
 * SsoProviderForm: the mapping editor says which legacy `groups -> attribute` rows the backend
 * stops reading once a row `attribute -> groups` exists; the save payload is the screen's, as is.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.attributes ? `${key}:${opts.attributes}` : key),
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

const open = (provider, attribute_mapping, onSave = vi.fn()) => {
  render(<SsoProviderForm provider={{ ...provider, attribute_mapping }} onSave={onSave} onCancel={vi.fn()} />)
  fireEvent.click(screen.getByText('sso.attributeRoleMappingSection'))
  return onSave
}
const notice = (attrs) => screen.queryByText(`sso.legacyGroupsHidden:${attrs}`)
const anyNotice = () => screen.queryByText(/^sso\.legacyGroupsHidden/)
const save = () => fireEvent.submit(document.querySelector('form'))

describe.each([['SAML', SAML], ['OIDC', OIDC]])('%s legacy groups notice', (_n, provider) => {
  it('shows after typing a row to groups next to a legacy row', () => {
    open(provider, { groups: 'memberOf', Role: 'x' })
    expect(anyNotice()).toBeNull()
    fireEvent.change(screen.getByDisplayValue('x'), { target: { value: 'groups' } })
    expect(notice('memberOf')).toBeInTheDocument()
  })

  it('names every hidden legacy row, in order', () => {
    open(provider, { groups: 'a', ' groups ': 'b', Role: 'groups' })
    expect(notice('a, b')).toBeInTheDocument()
  })

  it('counts a row whose key is groups too as the new form, as the backend does', () => {
    open(provider, { groups: 'groups', ' groups ': 'memberOf' })
    expect(notice('memberOf')).toBeInTheDocument()
  })

  it('says nothing of an attribute a new-form row still reads', () => {
    open(provider, { groups: 'memberOf', memberOf: 'groups' })
    expect(screen.queryByText(/^sso\.legacyGroupsHidden/)).not.toBeInTheDocument()
  })

  it('names only the attributes no new-form row reads', () => {
    open(provider, { groups: 'memberOf', ' groups ': 'Role', memberOf: 'groups' })
    expect(notice('Role')).toBeInTheDocument()
  })

  it('trims what the backend trims, a next-line character included', () => {
    open(provider, { '\u0085groups': 'memberOf', Role: '\u001fgroups' })
    expect(notice('memberOf')).toBeInTheDocument()
  })

  it('keeps a byte order mark the backend keeps', () => {
    open(provider, { '\ufeffgroups': 'memberOf', Role: 'groups' })
    expect(screen.queryByText(/^sso\.legacyGroupsHidden/)).not.toBeInTheDocument()
  })

  it('trims the key side', () => {
    open(provider, { ' groups ': 'memberOf', Role: 'groups' })
    expect(notice('memberOf')).toBeInTheDocument()
  })

  it('trims the value side', () => {
    open(provider, { groups: 'memberOf', Role: 'groups ' })
    expect(notice('memberOf')).toBeInTheDocument()
  })

  it('goes away when the cause is removed', () => {
    open(provider, { groups: 'memberOf', Role: 'groups' })
    expect(notice('memberOf')).toBeInTheDocument()
    fireEvent.change(screen.getAllByDisplayValue('groups')[1], { target: { value: 'username' } })
    expect(anyNotice()).toBeNull()
  })

  it('is absent for a lone legacy row, no legacy row, or an empty key on the groups row', () => {
    for (const m of [{ groups: 'memberOf' }, { Role: 'groups' }, { '': 'groups', groups: 'memberOf' }]) {
      const { unmount } = render(<SsoProviderForm provider={{ ...provider, attribute_mapping: m }} onSave={vi.fn()} onCancel={vi.fn()} />)
      fireEvent.click(screen.getByText('sso.attributeRoleMappingSection'))
      expect(anyNotice()).toBeNull()
      unmount()
    }
  })

  it('sends the screen rows as they are, legacy row included', () => {
    const onSave = open(provider, { groups: 'memberOf', Role: 'groups' })
    save()
    expect(onSave.mock.calls[0][0].attribute_mapping).toEqual({ groups: 'memberOf', Role: 'groups' })
  })
})

describe('SAML shortcut', () => {
  it('shows the notice after a click on a shortcut', () => {
    open(SAML, { groups: 'memberOf' })
    expect(anyNotice()).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /^Role/ }))
    expect(notice('memberOf')).toBeInTheDocument()
  })
})
