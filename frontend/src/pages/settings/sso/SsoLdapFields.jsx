import { useTranslation } from 'react-i18next'
import { Plugs, MagnifyingGlass, UsersThree, UserPlus, Play } from '@phosphor-icons/react'
import { Button, Input, Select, Badge, LoadingSpinner, CompactSection } from '../../../components'
import { ToggleSwitch } from '../../../components/ui/ToggleSwitch'
import MappingEditor from '../MappingEditor'

export default function SsoLdapFields({
  formData,
  handleChange,
  provider,
  testingConnection,
  connectionBadge,
  testMappingUsername,
  setTestMappingUsername,
  testingMapping,
  testMappingResult,
  handleTestConnection,
  handleTestMapping,
  roleOptions,
  setFormData,
}) {
  const { t } = useTranslation()

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
    <div className="space-y-3">
      {/* Connection */}
      <CompactSection
        title={<span className="flex items-center">{t('sso.connectionSection')}{connectionBadge}</span>}
        icon={Plugs}
        collapsible
        defaultOpen
      >
        <div className="space-y-3">
          <Select
            label={t('sso.directoryType')}
            value={formData._directoryType || 'custom'}
            onChange={handleDirectoryType}
            options={[
              { value: 'openldap', label: t('sso.ldapTypes.openldap') },
              { value: 'ad', label: t('sso.ldapTypes.activeDirectory') },
              { value: 'custom', label: t('common.custom') },
            ]}
          />
          <div className="grid grid-cols-3 gap-4">
            <Input
              label={t('sso.ldapServer')}
              value={formData.ldap_server}
              onChange={e => handleChange('ldap_server', e.target.value)}
              placeholder={formData._directoryType === 'ad' ? 'dc.example.com' : 'ldap.example.com'}
              className="col-span-2"
            />
            <Input
              label={t('common.portLabel')}
              type="number"
              value={formData.ldap_port}
              onChange={e => handleChange('ldap_port', parseInt(e.target.value))}
            />
          </div>
          <ToggleSwitch
            checked={formData.ldap_use_ssl}
            onChange={(val) => {
              handleChange('ldap_use_ssl', val)
              if (formData._directoryType === 'ad') handleChange('ldap_port', val ? 636 : 389)
            }}
            label={t('sso.ldapUseSsl')}
            size="sm"
          />
          {formData.ldap_use_ssl && (
            <>
              <ToggleSwitch
                checked={formData.ldap_verify_ssl}
                onChange={(val) => handleChange('ldap_verify_ssl', val)}
                label={t('sso.verifySsl')}
                size="sm"
              />
              {!formData.ldap_verify_ssl && (
                <p className="text-xs text-amber-500">{t('sso.sslWarning')}</p>
              )}
            </>
          )}
          <Input
            label={t('sso.bindDn')}
            value={formData.ldap_bind_dn}
            onChange={e => handleChange('ldap_bind_dn', e.target.value)}
            placeholder={formData._directoryType === 'ad' ? 'CN=svc-ldap,OU=Service Accounts,DC=example,DC=com' : t('sso.bindDnPlaceholder')}
          />
          <Input
            label={t('sso.bindPassword')}
            type="password"
            noAutofill
            value={formData.ldap_bind_password}
            onChange={e => handleChange('ldap_bind_password', e.target.value)}
            hasExistingValue={!!provider?.ldap_bind_password}
          />
          <Input
            label={t('sso.baseDn')}
            value={formData.ldap_base_dn}
            onChange={e => handleChange('ldap_base_dn', e.target.value)}
            placeholder={formData._directoryType === 'ad' ? 'DC=example,DC=com' : t('sso.baseDnPlaceholder')}
          />
          {provider?.id && (
            <Button type="button" variant="secondary" size="sm" onClick={handleTestConnection} disabled={testingConnection} className="gap-1.5">
              {testingConnection ? <LoadingSpinner size="xs" /> : <Plugs size={14} />}
              {t('sso.testConnection')}
            </Button>
          )}
        </div>
      </CompactSection>

      {/* User Search */}
      <CompactSection title={t('sso.userSearchSection')} icon={MagnifyingGlass} collapsible defaultOpen={false}>
        <div className="space-y-3">
          <Input
            label={t('sso.userFilter')}
            value={formData.ldap_user_filter}
            onChange={e => handleChange('ldap_user_filter', e.target.value)}
            placeholder={formData._directoryType === 'ad' ? '(sAMAccountName={username})' : t('sso.userFilterPlaceholder')}
          />
          <div className="grid grid-cols-3 gap-4">
            <Input label={t('sso.usernameAttr')} value={formData.ldap_username_attr} onChange={e => handleChange('ldap_username_attr', e.target.value)} placeholder={formData._directoryType === 'ad' ? 'sAMAccountName' : 'uid'} />
            <Input label={t('sso.emailAttr')} value={formData.ldap_email_attr} onChange={e => handleChange('ldap_email_attr', e.target.value)} placeholder="mail" />
            <Input label={t('sso.fullnameAttr')} value={formData.ldap_fullname_attr} onChange={e => handleChange('ldap_fullname_attr', e.target.value)} placeholder={formData._directoryType === 'ad' ? 'displayName' : 'cn'} />
          </div>
        </div>
      </CompactSection>

      {/* Groups & Role Mapping */}
      <CompactSection title={t('sso.groupsRolesSection')} icon={UsersThree} collapsible defaultOpen={false}>
        <div className="space-y-3">
          <Input
            label={t('sso.groupFilter')}
            value={formData.ldap_group_filter}
            onChange={e => handleChange('ldap_group_filter', e.target.value)}
            placeholder={formData._directoryType === 'ad' ? '(objectClass=group)' : t('sso.groupFilterPlaceholder')}
          />
          <Select
            label={t('sso.groupMemberAttr')}
            value={formData.ldap_group_member_attr || 'member'}
            onChange={value => handleChange('ldap_group_member_attr', value)}
            options={[
              { value: 'memberOf', label: t('sso.ldapGroupAttrs.memberOf') },
              { value: 'member', label: t('sso.ldapGroupAttrs.member') },
              { value: 'uniqueMember', label: t('sso.ldapGroupAttrs.uniqueMember') },
            ]}
          />
          <Select
            label={t('sso.defaultRole')}
            value={formData.default_role}
            onChange={value => handleChange('default_role', value)}
            options={roleOptions}
          />
          <div className="pt-1">
            <p className="text-xs font-medium text-text-secondary mb-2">{t('sso.roleMapping')}</p>
            <p className="text-xs text-text-muted mb-2">{t('sso.roleMappingHelp')}</p>
            <MappingEditor
              value={formData.role_mapping}
              onChange={val => handleChange('role_mapping', val)}
              keyLabel={t('sso.externalGroup')}
              valueLabel={t('sso.ucmRole')}
              keyPlaceholder="e.g., pki-admins"
              valueOptions={roleOptions}
            />
          </div>
          {provider?.id && (
            <div className="pt-2 border-t border-border">
              <p className="text-xs text-text-muted mb-2">{t('sso.testMappingDesc')}</p>
              <div className="flex gap-2">
                <Input
                  value={testMappingUsername}
                  onChange={e => setTestMappingUsername(e.target.value)}
                  placeholder={t('sso.testMappingUserPlaceholder')}
                  className="flex-1"
                  size="sm"
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleTestMapping}
                  disabled={testingMapping || !testMappingUsername.trim()}
                  className="gap-1 whitespace-nowrap"
                >
                  {testingMapping ? <LoadingSpinner size="xs" /> : <Play size={14} />}
                  {t('sso.testMappingRun')}
                </Button>
              </div>
              {testMappingResult && (
                <div className="mt-2 p-2.5 rounded-lg border border-border bg-bg-secondary text-xs space-y-1">
                  {testMappingResult.found === false ? (
                    <p className="text-status-error">{t('sso.testMappingNotFound')}</p>
                  ) : (
                    <>
                      <p><span className="text-text-secondary font-medium">DN:</span> <span className="text-text-muted font-mono">{testMappingResult.user_dn}</span></p>
                      <p>
                        <span className="text-text-secondary font-medium">{t('sso.testMappingGroups')}:</span>{' '}
                        {testMappingResult.groups?.length > 0
                          ? testMappingResult.groups.map(g => <Badge key={g} variant="secondary" size="sm" className="mr-1">{g}</Badge>)
                          : <span className="text-text-muted italic">{t('sso.testMappingNoGroups')}</span>
                        }
                      </p>
                      <p>
                        <span className="text-text-secondary font-medium">{t('sso.testMappingResolvedRole')}:</span>{' '}
                        <Badge variant={testMappingResult.resolved_role === 'admin' ? 'error' : testMappingResult.resolved_role === 'operator' ? 'warning' : 'info'} size="sm">
                          {testMappingResult.resolved_role}
                        </Badge>
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </CompactSection>

      {/* Provisioning */}
      <CompactSection title={t('sso.provisioningSection')} icon={UserPlus} collapsible defaultOpen={false}>
        <div className="space-y-2">
          <ToggleSwitch checked={formData.auto_create_users} onChange={(val) => handleChange('auto_create_users', val)} label={t('sso.autoCreateUsers')} />
          <ToggleSwitch checked={formData.auto_update_users} onChange={(val) => handleChange('auto_update_users', val)} label={t('sso.autoUpdateUsers')} />
          <ToggleSwitch checked={formData.sync_role_on_login} onChange={(val) => handleChange('sync_role_on_login', val)} label={t('sso.syncRoleOnLogin')} description={t('sso.syncRoleOnLoginHelp')} />
        </div>
      </CompactSection>
    </div>
  )
}
