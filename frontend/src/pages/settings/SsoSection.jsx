import { useTranslation } from 'react-i18next'
import { Key, Database, Globe, Shield, TestTube, Power, PencilSimple, Trash, Plus, ArrowsClockwise } from '@phosphor-icons/react'
import { Button, Badge, HelpCard, DetailHeader, DetailContent } from '../../components'

export default function SsoSection({ ssoProviders, ssoLoading, ssoTesting, handleSsoCreate, handleSsoEdit, handleSsoToggle, handleSsoTest, setSsoConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={Key}
        title={t('common.sso')}
        subtitle={t('sso.subtitle')}
      />

      <HelpCard variant="info" title={t('sso.helpTitle')} className="mb-4">
        {t('sso.helpDescription')}
      </HelpCard>

      {ssoLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
        </div>
      ) : (
        <div className="space-y-3">
          {/* One card per provider type */}
          {[
            { type: 'ldap', label: t('sso.ldap'), icon: Database, color: 'icon-bg-blue', desc: t('sso.providerDescriptions.ldap') },
            { type: 'oauth2', label: t('sso.oauth2'), icon: Globe, color: 'icon-bg-teal', desc: t('sso.providerDescriptions.oauth2') },
            { type: 'saml', label: t('sso.saml'), icon: Shield, color: 'icon-bg-violet', desc: t('sso.providerDescriptions.saml') },
          ].map(({ type, label, icon: Icon, color, desc }) => {
            const provider = ssoProviders.find(p => p.provider_type === type)
            return (
              <div key={type} className="flex items-center justify-between p-4 bg-tertiary-50 border border-border rounded-lg">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
                    <Icon size={20} weight="bold" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-text-primary">{label}</span>
                      {provider ? (
                        <>
                          <Badge variant={provider.enabled ? 'success' : 'secondary'} size="sm">
                            {provider.enabled ? t('common.enabled') : t('common.disabled')}
                          </Badge>
                          {provider.is_default && (
                            <Badge variant="primary" size="sm">{t('sso.default')}</Badge>
                          )}
                        </>
                      ) : (
                        <Badge variant="secondary" size="sm">{t('sso.notConfigured')}</Badge>
                      )}
                    </div>
                    <p className="text-xs text-text-secondary">
                      {provider ? (provider.display_name || provider.name) : desc}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {provider ? (
                    <>
                      <Button type="button" size="sm" variant="secondary" onClick={() => handleSsoTest(provider)} disabled={ssoTesting} title={t('sso.testConnection')}>
                        {ssoTesting ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
                      </Button>
                      <Button type="button" size="sm" variant="secondary" onClick={() => handleSsoToggle(provider)} title={provider.enabled ? t('sso.disable') : t('sso.enable')}>
                        <Power size={14} />
                      </Button>
                      <Button type="button" size="sm" variant="secondary" onClick={() => handleSsoEdit(provider)} title={t('common.edit')}>
                        <PencilSimple size={14} />
                      </Button>
                      <Button type="button" size="sm" variant="danger" onClick={() => setSsoConfirmDelete(provider)} title={t('common.delete')}>
                        <Trash size={14} />
                      </Button>
                    </>
                  ) : (
                    hasPermission('admin:system') && (
                      <Button type="button" size="sm" onClick={() => handleSsoCreate(type)}>
                        <Plus size={14} />
                        {t('sso.configure')}
                      </Button>
                    )
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </DetailContent>
  )
}
