/**
 * LDAP group search base: offered for member / uniqueMember searches, sent as typed;
 * memberOf is read on the user entry and has no search base.
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

import SsoLdapFields from '../settings/sso/SsoLdapFields'

const show = (formData, handleChange = vi.fn()) => {
  render(
    <SsoLdapFields
      formData={formData} handleChange={handleChange} provider={{ id: 4 }}
      testMappingUsername="" setTestMappingUsername={vi.fn()} testingMapping={false}
      testMappingResult={null} handleTestConnection={vi.fn()} handleTestMapping={vi.fn()}
      roleOptions={[]} defaultRoleOptions={[]} customRoles={[]} setFormData={vi.fn()}
      secretProps={{}}
    />)
  fireEvent.click(screen.getByText('sso.groupsRolesSection'))
  return handleChange
}

describe('SsoLdapFields group search base', () => {
  it('is offered for a member search and sent as typed', () => {
    const handleChange = show({ ldap_group_member_attr: 'member', ldap_group_base_dn: '' })
    expect(screen.getByText('sso.groupBaseDnHelp')).toBeTruthy()
    fireEvent.change(screen.getByPlaceholderText('ou=groups,dc=example,dc=com'),
      { target: { value: 'ou=groups,dc=corp' } })
    expect(handleChange).toHaveBeenCalledWith('ldap_group_base_dn', 'ou=groups,dc=corp')
  })

  it('is not offered for memberOf', () => {
    show({ ldap_group_member_attr: 'memberOf' })
    expect(screen.queryByText('sso.groupBaseDn')).toBeNull()
    expect(screen.queryByPlaceholderText('ou=groups,dc=example,dc=com')).toBeNull()
  })
})
