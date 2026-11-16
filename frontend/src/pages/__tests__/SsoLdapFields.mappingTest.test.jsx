/**
 * LDAP mapping test result: the access badge is shown whenever the user is found,
 * and a refused user has no resolved role.
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

const show = (result) => {
  render(
    <SsoLdapFields
      formData={{ role_mapping: { 'PKI-Admins': 'admin' }, ldap_group_member_attr: 'memberOf' }}
      handleChange={vi.fn()} provider={{ id: 4 }} testMappingUsername="alice"
      setTestMappingUsername={vi.fn()} testingMapping={false} testMappingResult={result}
      handleTestConnection={vi.fn()} handleTestMapping={vi.fn()} roleOptions={[]}
      defaultRoleOptions={[]} customRoles={[]} setFormData={vi.fn()} secretProps={{}}
    />)
  fireEvent.click(screen.getByText('sso.groupsRolesSection'))
}

const BASE = {
  found: true, user_dn: 'CN=alice,DC=x', groups: ['VPN'], groups_readable: true,
  role_mapping: { 'PKI-Admins': 'admin' }, default_role: 'viewer', required_groups: [],
  account_checked: false,
}

describe('SsoLdapFields mapping test result', () => {
  it('says a user no rule matches is refused, without a resolved role', () => {
    show({ ...BASE, access_allowed: false, refusal: 'unmapped', resolved_role: null })
    expect(screen.getByText('sso.testMappingAccessRefused')).toBeTruthy()
    expect(screen.getByText('sso.testMappingRefusalUnmapped')).toBeTruthy()
    expect(screen.queryByText('sso.testMappingResolvedRole:')).toBeNull()
    expect(screen.queryByText('viewer')).toBeNull()
    expect(screen.getByText('sso.testMappingNotChecked')).toBeTruthy()
  })

  it('says the groups could not be read', () => {
    show({ ...BASE, groups: [], groups_readable: false, access_allowed: false,
      refusal: 'groups_unreadable', resolved_role: null })
    expect(screen.getByText('sso.testMappingGroupsUnreadable')).toBeTruthy()
    expect(screen.queryByText('sso.testMappingNoGroups')).toBeNull()
    expect(screen.getByText('sso.testMappingRefusalGroupsUnreadable')).toBeTruthy()
  })

  it('shows the access and the role of an admitted user without required groups', () => {
    show({ ...BASE, groups: ['PKI-Admins'], access_allowed: true, refusal: null,
      resolved_role: 'admin' })
    expect(screen.getByText('sso.testMappingAccessAllowed')).toBeTruthy()
    expect(screen.getByText('admin')).toBeTruthy()
  })
})
