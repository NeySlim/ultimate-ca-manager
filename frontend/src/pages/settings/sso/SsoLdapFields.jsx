import { useTranslation } from 'react-i18next'
import { Btn } from '../../../components/atelier'
import { Input, NumberInput, SecretInput, Select, ToggleSwitch, Fold, Notice } from '../../../components/atelier/Form'
import RoleMappingEditor from '../RoleMappingEditor'
import ProvisioningNotice, { hasRoleRules } from './ProvisioningNotice'
import MappingTestResult from './MappingTestResult'
import TestConnectionButton from './TestConnectionButton'
import { shownNumber, typedNumber } from '../numberFields'

export default function SsoLdapFields({
  formData,
  handleChange,
  provider,
  testingConnection,
  connectionStatus,
  testMappingUsername,
  setTestMappingUsername,
  testingMapping,
  testMappingResult,
  handleTestConnection,
  dirty,
  handleTestMapping,
  roleOptions,
  defaultRoleOptions,
  customRoles,
  setFormData,
  secretProps,
}) {
  const { t } = useTranslation()
  const ad = formData._directoryType === 'ad'

  const handleDirectoryType = (value) => {
    handleChange('_directoryType', value)
    if (value === 'openldap') {
      setFormData(prev => ({
        ...prev,
        _directoryType: value,
        ldap_port: prev.ldap_port || 389,
        ldap_user_filter: '(uid={username})',
        ldap_username_attr: 'uid',
        ldap_email_attr: 'mail',
        ldap_fullname_attr: 'cn',
        ldap_group_filter: '(objectClass=groupOfNames)',
        ldap_group_member_attr: 'member',
      }))
    } else if (value === 'ad') {
      setFormData(prev => ({
        ...prev,
        _directoryType: value,
        ldap_port: prev.ldap_use_ssl ? 636 : 389,
        ldap_user_filter: '(sAMAccountName={username})',
        ldap_username_attr: 'sAMAccountName',
        ldap_email_attr: 'mail',
        ldap_fullname_attr: 'displayName',
        ldap_group_filter: '(objectClass=group)',
        ldap_group_member_attr: 'memberOf',
      }))
    }
  }

  return (
    <>
      <Fold title={t('sso.connectionSection')} defaultOpen>
        <Select id="sso-ldap-directory" label={t('sso.directoryType')} value={formData._directoryType || 'custom'} onChange={handleDirectoryType}
          options={[
            { value: 'openldap', label: t('sso.ldapTypes.openldap') },
            { value: 'ad', label: t('sso.ldapTypes.activeDirectory') },
            { value: 'custom', label: t('common.custom') },
          ]} />
        <Input id="sso-ldap-server" label={t('sso.ldapServer')} value={formData.ldap_server}
          onChange={e => handleChange('ldap_server', e.target.value)} placeholder={ad ? 'dc.example.com' : 'ldap.example.com'} />
        <NumberInput id="sso-ldap-port" label={t('common.portLabel')} value={shownNumber(formData.ldap_port)}
          onChange={e => handleChange('ldap_port', typedNumber(e))} />
        <ToggleSwitch checked={formData.ldap_use_ssl} label={t('sso.ldapUseSsl')}
          onChange={(val) => {
            handleChange('ldap_use_ssl', val)
            if (ad) handleChange('ldap_port', val ? 636 : 389)
          }} />
        {!formData.ldap_use_ssl && (
          <ToggleSwitch checked={formData.ldap_start_tls} onChange={(val) => handleChange('ldap_start_tls', val)}
            label={t('sso.ldapStartTls')} description={t('sso.ldapStartTlsHelp')} />
        )}
        {!formData.ldap_use_ssl && !formData.ldap_start_tls && <Notice tone="warn">{t('sso.ldapPlainWarning')}</Notice>}
        {(formData.ldap_use_ssl || formData.ldap_start_tls) && (
          <>
            <ToggleSwitch checked={formData.ldap_verify_ssl} onChange={(val) => handleChange('ldap_verify_ssl', val)} label={t('sso.verifySsl')} />
            {!formData.ldap_verify_ssl && <Notice tone="warn">{t('sso.sslWarning')}</Notice>}
          </>
        )}
        <Input id="sso-ldap-bind-dn" full label={t('sso.bindDn')} value={formData.ldap_bind_dn}
          onChange={e => handleChange('ldap_bind_dn', e.target.value)}
          placeholder={ad ? 'CN=svc-ldap,OU=Service Accounts,DC=example,DC=com' : t('sso.bindDnPlaceholder')} />
        <SecretInput id="sso-ldap-bind-password" label={t('sso.bindPassword')} value={formData.ldap_bind_password}
          onChange={e => handleChange('ldap_bind_password', e.target.value)} hasExistingValue={!!provider?.ldap_bind_password} {...secretProps} />
        <Input id="sso-ldap-base-dn" label={t('sso.baseDn')} value={formData.ldap_base_dn}
          onChange={e => handleChange('ldap_base_dn', e.target.value)} placeholder={ad ? 'DC=example,DC=com' : t('sso.baseDnPlaceholder')} />
        {provider?.id && (
          <TestConnectionButton onClick={handleTestConnection} testing={testingConnection} dirty={dirty} status={connectionStatus} />
        )}
      </Fold>

      <Fold title={t('sso.userSearchSection')}>
        <Input id="sso-ldap-user-filter" full label={t('sso.userFilter')} value={formData.ldap_user_filter}
          onChange={e => handleChange('ldap_user_filter', e.target.value)}
          placeholder={ad ? '(sAMAccountName={username})' : t('sso.userFilterPlaceholder')} />
        <Input id="sso-ldap-username-attr" label={t('sso.usernameAttr')} value={formData.ldap_username_attr}
          onChange={e => handleChange('ldap_username_attr', e.target.value)} placeholder={ad ? 'sAMAccountName' : 'uid'} />
        <Input id="sso-ldap-email-attr" label={t('sso.emailAttr')} value={formData.ldap_email_attr}
          onChange={e => handleChange('ldap_email_attr', e.target.value)} placeholder="mail" />
        <Input id="sso-ldap-fullname-attr" label={t('sso.fullnameAttr')} value={formData.ldap_fullname_attr}
          onChange={e => handleChange('ldap_fullname_attr', e.target.value)} placeholder={ad ? 'displayName' : 'cn'} />
        <Input id="sso-ldap-uid-attr" label={t('sso.uidAttr')} value={formData.ldap_uid_attr || ''}
          onChange={e => handleChange('ldap_uid_attr', e.target.value)} placeholder={ad ? 'objectGUID' : 'entryUUID'} hint={t('sso.uidAttrHelp')} />
        <Input id="sso-ldap-status-attr" label={t('sso.accountStatusAttr')} value={formData.account_status_attr || ''}
          onChange={e => handleChange('account_status_attr', e.target.value)} placeholder={ad ? 'userAccountControl' : 'accountStatus'} />
      </Fold>

      <Fold title={t('sso.groupsRolesSection')}>
        {/* Default-deny: the groups a user must belong to */}
        <Input id="sso-ldap-required-groups" full label={t('sso.requiredGroups')} value={formData.ldap_required_groups || ''}
          onChange={e => handleChange('ldap_required_groups', e.target.value)} placeholder={t('sso.requiredGroupsPlaceholder')}
          hint={t('sso.requiredGroupsHelp')} />
        <Input id="sso-ldap-group-filter" label={t('sso.groupFilter')} value={formData.ldap_group_filter}
          onChange={e => handleChange('ldap_group_filter', e.target.value)}
          placeholder={ad ? '(objectClass=group)' : t('sso.groupFilterPlaceholder')} />
        <Select id="sso-ldap-member-attr" label={t('sso.groupMemberAttr')} value={formData.ldap_group_member_attr || 'member'}
          onChange={value => handleChange('ldap_group_member_attr', value)}
          options={[
            { value: 'memberOf', label: t('sso.ldapGroupAttrs.memberOf') },
            { value: 'member', label: t('sso.ldapGroupAttrs.member') },
            { value: 'uniqueMember', label: t('sso.ldapGroupAttrs.uniqueMember') },
          ]} />
        <ToggleSwitch checked={formData.ldap_nested_groups === true} onChange={(val) => handleChange('ldap_nested_groups', val)}
          label={t('sso.ldapNestedGroups')} description={t('sso.ldapNestedGroupsHelp')} />
        {formData.ldap_nested_groups === true && <Notice tone="warn">{t('sso.ldapNestedGroupsWarning')}</Notice>}
        {/* With the nested option, the parent groups are searched under this base, memberOf included */}
        {((formData.ldap_group_member_attr || 'member') !== 'memberOf' || formData.ldap_nested_groups === true) && (
          <Input id="sso-ldap-group-base" label={t('sso.groupBaseDn')} value={formData.ldap_group_base_dn || ''}
            onChange={e => handleChange('ldap_group_base_dn', e.target.value)} placeholder="ou=groups,dc=example,dc=com"
            hint={t('sso.groupBaseDnHelp')} />
        )}
        <Select id="sso-ldap-default-role" label={t('sso.defaultRole')} value={formData.default_role}
          onChange={value => handleChange('default_role', value)} options={defaultRoleOptions} />
        <RoleMappingEditor legend={t('sso.roleMapping')} hint={t('sso.roleMappingHelp')}
          value={formData.role_mapping} onChange={val => handleChange('role_mapping', val)}
          keyLabel={t('sso.externalGroup')} keyPlaceholder="e.g., pki-admins" roleOptions={roleOptions} customRoles={customRoles} />
        {provider?.id && (
          <>
            <div className="settings-test">
              <Input id="sso-test-mapping-user" label={t('sso.testMapping')} hint={t('sso.testMappingDesc')} value={testMappingUsername}
                onChange={e => setTestMappingUsername(e.target.value)} placeholder={t('sso.testMappingUserPlaceholder')} />
              <Btn icon="users" onClick={handleTestMapping} disabled={testingMapping || !testMappingUsername.trim() || undefined}>
                {testingMapping ? t('common.testing') : t('sso.testMappingRun')}
              </Btn>
            </div>
            {testMappingResult && <MappingTestResult result={testMappingResult} />}
          </>
        )}
      </Fold>

      <Fold title={t('sso.provisioningSection')} defaultOpen={!hasRoleRules(formData.role_mapping)}>
        <ProvisioningNotice formData={formData} />
        <ToggleSwitch checked={formData.auto_create_users} onChange={(val) => handleChange('auto_create_users', val)} label={t('sso.autoCreateUsers')} />
        <ToggleSwitch checked={formData.auto_update_users} onChange={(val) => handleChange('auto_update_users', val)} label={t('sso.autoUpdateUsers')} />
        <ToggleSwitch checked={formData.sync_role_on_login} onChange={(val) => handleChange('sync_role_on_login', val)}
          label={t('sso.syncRoleOnLogin')} description={t('sso.syncRoleOnLoginHelp')} />
      </Fold>
    </>
  )
}
