import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, Pill, RecordList, RecordRow, SkeletonPanel } from '../../components/atelier'
import { SettingsGroup } from '../../components/atelier/SettingsView'

const TYPES = [
  { type: 'ldap', labelKey: 'sso.ldap', descKey: 'sso.providerDescriptions.ldap' },
  { type: 'oauth2', labelKey: 'sso.oauth2', descKey: 'sso.providerDescriptions.oauth2' },
  { type: 'saml', labelKey: 'sso.saml', descKey: 'sso.providerDescriptions.saml' },
]

/**
 * The mockup's SSO section holds one OpenID Connect provider; the product has one per protocol,
 * listed as the mockup's records: the protocol and its provider, its state, then its actions.
 */
export default function SsoSection({ ssoProviders, ssoLoading, ssoTesting, handleSsoCreate, handleSsoEdit, handleSsoToggle, handleSsoTest, setSsoConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  // Test, enable and edit write a provider (write:sso), deleting one is delete:sso
  const canWrite = hasPermission('write:sso')
  const canDelete = hasPermission('delete:sso')
  if (ssoLoading) return <SkeletonPanel label={t('common.loading')} />
  return (
    <SettingsGroup legend={t('sso.configuredProviders')} grid={false}>
      <RecordList>
        {TYPES.map(({ type, labelKey, descKey }) => {
          const label = t(labelKey)
          const provider = ssoProviders.find(p => p.provider_type === type)
          const actions = provider ? (
            <>
              {canWrite && (
                <>
                  <IconBtn icon="send" label={t('sso.testConnection')} disabled={ssoTesting || undefined} onClick={() => handleSsoTest(provider)} />
                  <IconBtn icon={provider.enabled ? 'block' : 'check'} write label={provider.enabled ? t('sso.disable') : t('sso.enable')}
                    onClick={() => handleSsoToggle(provider)} />
                  <IconBtn icon="settings" label={t('common.edit')} onClick={() => handleSsoEdit(provider)} />
                </>
              )}
              {canDelete && <IconBtn icon="close" write label={t('common.delete')} onClick={() => setSsoConfirmDelete(provider)} />}
            </>
          ) : hasPermission('admin:system') && (
            <Btn icon="plus" onClick={() => handleSsoCreate(type)}>{t('sso.configure')}</Btn>
          )
          return (
            <RecordRow key={type} title={label}
              meta={provider ? (provider.display_name || provider.name) : t(descKey)}
              badge={provider ? (
                <span className="row-actions">
                  <Pill tone={provider.enabled ? 'good' : 'muted'} label={provider.enabled ? t('common.enabled') : t('common.disabled')} />
                  {provider.is_default && <Pill icon="pin" label={t('sso.default')} />}
                </span>
              ) : <Pill tone="muted" label={t('sso.notConfigured')} />}
              action={actions || null} />
          )
        })}
      </RecordList>
    </SettingsGroup>
  )
}
