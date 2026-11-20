import { useTranslation } from 'react-i18next'
import { Database, Globe, Shield, TestTube, Power, PencilSimple, Trash, Plus, ArrowsClockwise } from '@phosphor-icons/react'
import { Button, Badge, HelpCard } from '../../components'

export default function SsoSection({ ssoProviders, ssoLoading, ssoTesting, handleSsoCreate, handleSsoEdit, handleSsoToggle, handleSsoTest, setSsoConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  // Test, enable and edit write a provider (write:sso), deleting one is delete:sso
  const canWrite = hasPermission('write:sso')
  const canDelete = hasPermission('delete:sso')
  return (
    <>

      <HelpCard variant="info" title={t('sso.helpTitle')}>
        {t('sso.helpDescription')}
      </HelpCard>

      {ssoLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
        </div>
      ) : (
        // One line per provider type, as the mockup's record list: name and state, then the actions
        <ul className="sf-records">
          {[
            { type: 'ldap', label: t('sso.ldap'), icon: Database, desc: t('sso.providerDescriptions.ldap') },
            { type: 'oauth2', label: t('sso.oauth2'), icon: Globe, desc: t('sso.providerDescriptions.oauth2') },
            { type: 'saml', label: t('sso.saml'), icon: Shield, desc: t('sso.providerDescriptions.saml') },
          ].map(({ type, label, desc }) => {
            const provider = ssoProviders.find(p => p.provider_type === type)
            const name = provider ? (provider.display_name || provider.name) : label
            return (
              <li key={type}>
                <div className="sf-record-main">
                  <span className="sf-record-title">
                    <strong>{label}</strong>
                    {provider ? (
                      <>
                        <Badge variant={provider.enabled ? 'success' : 'secondary'} size="sm">
                          {provider.enabled ? t('common.enabled') : t('common.disabled')}
                        </Badge>
                        {provider.is_default && <Badge variant="primary" size="sm">{t('sso.default')}</Badge>}
                      </>
                    ) : (
                      <Badge variant="secondary" size="sm">{t('sso.notConfigured')}</Badge>
                    )}
                  </span>
                  <span className="sf-record-meta">{provider ? name : desc}</span>
                </div>
                <div className="sf-record-actions">
                  {provider ? (
                    <>
                      {canWrite && (
                        <>
                          <Button type="button" variant="secondary" onClick={() => handleSsoTest(provider)} disabled={ssoTesting}
                            aria-label={t('sso.testConnection')} title={t('sso.testConnection')}>
                            {ssoTesting ? <ArrowsClockwise size={16} className="animate-spin" /> : <TestTube size={16} />}
                          </Button>
                          <Button type="button" variant="secondary" onClick={() => handleSsoToggle(provider)}
                            aria-label={provider.enabled ? t('sso.disable') : t('sso.enable')} title={provider.enabled ? t('sso.disable') : t('sso.enable')}>
                            <Power size={16} />
                          </Button>
                          <Button type="button" variant="secondary" onClick={() => handleSsoEdit(provider)}
                            aria-label={t('common.edit')} title={t('common.edit')}>
                            <PencilSimple size={16} />
                          </Button>
                        </>
                      )}
                      {canDelete && (
                        <Button type="button" variant="danger" onClick={() => setSsoConfirmDelete(provider)}
                          aria-label={t('common.delete')} title={t('common.delete')}>
                          <Trash size={16} />
                        </Button>
                      )}
                    </>
                  ) : (
                    hasPermission('admin:system') && (
                      <Button type="button" variant="secondary" onClick={() => handleSsoCreate(type)}>
                        <Plus size={16} />
                        {t('sso.configure')}
                      </Button>
                    )
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </>
  )
}
