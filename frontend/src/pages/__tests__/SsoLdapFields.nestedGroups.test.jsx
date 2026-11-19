/**
 * LDAP nested groups option: off unless set, its warning shown when on, and the cause of
 * a refused group read shown by the mapping test.
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

const show = (formData, result = null, handleChange = vi.fn()) => {
  render(
    <SsoLdapFields
      formData={formData} handleChange={handleChange} provider={{ id: 4 }}
      testMappingUsername="alice" setTestMappingUsername={vi.fn()} testingMapping={false}
      testMappingResult={result} handleTestConnection={vi.fn()} handleTestMapping={vi.fn()}
      roleOptions={[]} defaultRoleOptions={[]} customRoles={[]} setFormData={vi.fn()}
      secretProps={{}}
    />)
  fireEvent.click(screen.getByText('sso.groupsRolesSection'))
  return handleChange
}

const nestedSwitch = () =>
  screen.getByText('sso.ldapNestedGroups').closest('div').parentElement.querySelector('[role="switch"]')

describe('SsoLdapFields nested groups', () => {
  it('is off without the field and turns on by its switch', () => {
    const handleChange = show({ ldap_group_member_attr: 'memberOf' })
    expect(nestedSwitch().getAttribute('aria-checked')).toBe('false')
    expect(screen.queryByText('sso.ldapNestedGroupsWarning')).toBeNull()
    fireEvent.click(nestedSwitch())
    expect(handleChange).toHaveBeenCalledWith('ldap_nested_groups', true)
  })

  it('warns that parent groups give their roles when on', () => {
    show({ ldap_group_member_attr: 'member', ldap_nested_groups: true })
    expect(nestedSwitch().getAttribute('aria-checked')).toBe('true')
    expect(screen.getByText('sso.ldapNestedGroupsWarning')).toBeTruthy()
  })

  it('shows why the groups could not be read', () => {
    show({ ldap_group_member_attr: 'memberOf', role_mapping: { A: 'admin' } }, {
      found: true, user_dn: 'CN=alice,DC=x', groups: [], groups_readable: false,
      groups_error: 'nested group search under DC=x: sizeLimitExceeded',
      access_allowed: false, refusal: 'groups_unreadable', resolved_role: null,
      role_mapping: { A: 'admin' }, default_role: 'viewer', required_groups: [],
    })
    expect(screen.getByText('sso.testMappingGroupsUnreadable')).toBeTruthy()
    expect(screen.getByText('nested group search under DC=x: sizeLimitExceeded')).toBeTruthy()
  })

  it('shows the group search base whenever the option is on, memberOf included', () => {
    show({ ldap_group_member_attr: 'memberOf', ldap_nested_groups: true,
      ldap_group_base_dn: 'OU=Groups,DC=x' })
    expect(screen.getByText('sso.groupBaseDn')).toBeTruthy()
    expect(screen.getByDisplayValue('OU=Groups,DC=x')).toBeTruthy()
  })

  // Guard: today's behaviour, kept
  it('hides the group search base with memberOf while the option is off', () => {
    show({ ldap_group_member_attr: 'memberOf', ldap_nested_groups: false })
    expect(screen.queryByText('sso.groupBaseDn')).toBeNull()
  })
})
