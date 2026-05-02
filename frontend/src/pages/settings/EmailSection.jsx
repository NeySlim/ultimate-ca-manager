import { useTranslation } from 'react-i18next'
import { useNotification } from '../../contexts'
import { EnvelopeSimple, Envelope, Bell, Warning, ArrowsClockwise, FloppyDisk, CheckCircle, XCircle, Key, Copy, Info, PencilSimple } from '@phosphor-icons/react'
import { Button, Input, HelpCard, DetailHeader, DetailSection, DetailGrid, DetailContent } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import TagsInput from '../../components/ui/TagsInput'
import EmailTemplateWindow from '../../components/EmailTemplateWindow'
import { WarningCircle } from '@phosphor-icons/react'

export default function EmailSection({ settings, updateSetting, handleSave, saving, canWrite, isMobile, emailTestResult, emailTesting, handleTestEmail, oauthDirty, setOauthDirty, oauthPresets, applyOAuthProviderPreset, handleSmtpOAuthAuthorize, handleSmtpOAuthRevoke, expiryAlerts, setExpiryAlerts, saveExpiryAlerts, triggerExpiryCheck, showTemplateEditor, setShowTemplateEditor }) {
  const { t } = useTranslation()
  const { showSuccess } = useNotification()
  const oauthProviderSetup = {
    google: {
      consoleUrl: 'https://console.cloud.google.com/apis/credentials',
      consoleLabel: 'Google Cloud Console → APIs & Services → Credentials',
    },
    microsoft: {
      consoleUrl: 'https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade',
      consoleLabel: 'Azure Portal → App registrations',
    },
    microsoft365: {
      consoleUrl: 'https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade',
      consoleLabel: 'Azure Portal → App registrations',
    },
  }
  return (
    <DetailContent>
      <DetailHeader
        icon={EnvelopeSimple}
        title={t('settings.emailTitle')}
        subtitle={t('settings.emailSubtitle')}
      />
      <DetailSection title={t('settings.smtpConfig')} icon={Envelope} iconClass="icon-bg-violet">
        <div className="space-y-5">
          {/* Server */}
          <DetailGrid>
            <div className="col-span-full md:col-span-1">
              <Input
                label={t('settings.smtpHost')}
                value={settings.smtp_host || ''}
                onChange={(e) => updateSetting('smtp_host', e.target.value)}
                placeholder={t('settings.smtpHostPlaceholder')}
              />
            </div>
            <div className="col-span-full md:col-span-1">
              <Input
                label={t('settings.smtpPort')}
                type="number"
                value={settings.smtp_port || 587}
                onChange={(e) => updateSetting('smtp_port', parseInt(e.target.value))}
              />
            </div>
          </DetailGrid>

          {/* Authentication */}
          <div className="border-t border-border pt-4 space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm text-text-secondary">{t('settings.smtpAuthMethod')}:</span>
              {['password', 'oauth2', 'none'].map(method => (
                <button
                  key={method}
                  type="button"
                  onClick={() => {
                    updateSetting('smtp_auth_method', method)
                    setOauthDirty(prev => prev || method === 'oauth2')
                  }}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    (settings.smtp_auth_method || 'password') === method
                      ? 'bg-accent-primary text-white'
                      : 'bg-bg-tertiary text-text-secondary hover:bg-bg-secondary'
                  }`}
                >
                  {t(`settings.smtpAuthMethod_${method}`)}
                </button>
              ))}
            </div>

            {(settings.smtp_auth_method || 'password') === 'none' && (
              <p className="text-xs text-text-tertiary">{t('settings.smtpNoAuthHint')}</p>
            )}

            {(settings.smtp_auth_method || 'password') === 'password' && (
              <DetailGrid>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label={t('settings.smtpUsername')}
                    value={settings.smtp_username || ''}
                    onChange={(e) => updateSetting('smtp_username', e.target.value)}
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label={t('settings.smtpPassword')}
                    type="password"
                    noAutofill
                    value={settings.smtp_password === '********' ? '' : (settings.smtp_password || '')}
                    onChange={(e) => updateSetting('smtp_password', e.target.value)}
                    hasExistingValue={settings.smtp_password === '********'}
                  />
                </div>
              </DetailGrid>
            )}

            {(settings.smtp_auth_method || 'password') === 'oauth2' && (
              <div className="space-y-3">
                {/* Mailbox / username (XOAUTH2 uses email address as user) */}
                <DetailGrid>
                  <div className="col-span-full md:col-span-1">
                    <Input
                      label={t('settings.smtpUsername')}
                      value={settings.smtp_username || ''}
                      onChange={(e) => updateSetting('smtp_username', e.target.value)}
                    />
                  </div>
                </DetailGrid>

                {/* Provider selector */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm text-text-secondary">{t('settings.smtpOauthProvider')}:</span>
                  {['google', 'microsoft', 'microsoft365', 'custom'].map(provider => (
                    <button
                      key={provider}
                      type="button"
                      onClick={() => applyOAuthProviderPreset(provider)}
                      className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                        (settings.smtp_oauth_provider || 'google') === provider
                          ? 'bg-accent-primary text-white'
                          : 'bg-bg-tertiary text-text-secondary hover:bg-bg-secondary'
                      }`}
                    >
                      {t(`settings.smtpOauthProvider_${provider}`)}
                    </button>
                  ))}
                </div>

                {/* Per-provider setup guide */}
                {oauthProviderSetup[settings.smtp_oauth_provider || 'google'] && (
                  <div className="flex items-start gap-2 p-3 bg-status-info-op10 border border-status-info-op30 rounded-lg text-xs text-text-secondary">
                    <Info size={16} className="shrink-0 mt-0.5 text-status-info" />
                    <div className="space-y-1.5 flex-1">
                      <p className="font-medium text-text-primary">
                        {t(`settings.smtpOauthSetup_${settings.smtp_oauth_provider || 'google'}_title`)}
                      </p>
                      <p className="whitespace-pre-line">
                        {t(`settings.smtpOauthSetup_${settings.smtp_oauth_provider || 'google'}_steps`)}
                      </p>
                      <a
                        href={oauthProviderSetup[settings.smtp_oauth_provider || 'google'].consoleUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-accent-primary hover:underline font-medium"
                      >
                        {oauthProviderSetup[settings.smtp_oauth_provider || 'google'].consoleLabel} ↗
                      </a>
                    </div>
                  </div>
                )}

                <DetailGrid>
                  {(settings.smtp_oauth_provider || 'google') === 'microsoft365' && (
                    <div className="col-span-full md:col-span-1">
                      <Input
                        label={t('settings.smtpOauthTenant')}
                        value={settings.smtp_oauth_tenant_id || ''}
                        onChange={(e) => { updateSetting('smtp_oauth_tenant_id', e.target.value); setOauthDirty(true) }}
                        placeholder="common"
                        helper={t('settings.smtpOauthTenantHintM365')}
                      />
                    </div>
                  )}
                  <div className="col-span-full md:col-span-1">
                    <Input
                      label={t('settings.smtpOauthClientId')}
                      value={settings.smtp_oauth_client_id || ''}
                      onChange={(e) => { updateSetting('smtp_oauth_client_id', e.target.value); setOauthDirty(true) }}
                    />
                  </div>
                  <div className="col-span-full md:col-span-1">
                    <Input
                      label={t('settings.smtpOauthClientSecret')}
                      type="password"
                      noAutofill
                      value={settings.smtp_oauth_client_secret === '********' ? '' : (settings.smtp_oauth_client_secret || '')}
                      onChange={(e) => { updateSetting('smtp_oauth_client_secret', e.target.value); setOauthDirty(true) }}
                      hasExistingValue={settings.has_oauth_client_secret}
                    />
                  </div>
                  {(settings.smtp_oauth_provider || 'google') === 'custom' && (
                    <>
                      <div className="col-span-full md:col-span-1">
                        <Input
                          label={t('settings.smtpOauthAuthorizeUrl')}
                          value={settings.smtp_oauth_authorize_url || ''}
                          onChange={(e) => { updateSetting('smtp_oauth_authorize_url', e.target.value); setOauthDirty(true) }}
                        />
                      </div>
                      <div className="col-span-full md:col-span-1">
                        <Input
                          label={t('settings.smtpOauthTokenUrl')}
                          value={settings.smtp_oauth_token_url || ''}
                          onChange={(e) => { updateSetting('smtp_oauth_token_url', e.target.value); setOauthDirty(true) }}
                        />
                      </div>
                      <div className="col-span-full md:col-span-1">
                        <Input
                          label={t('settings.smtpOauthScope')}
                          value={settings.smtp_oauth_scope || ''}
                          onChange={(e) => { updateSetting('smtp_oauth_scope', e.target.value); setOauthDirty(true) }}
                        />
                      </div>
                    </>
                  )}
                  <div className="col-span-full">
                    <Input
                      label={t('settings.smtpOauthRedirectUri')}
                      value={settings.smtp_oauth_redirect_uri || ''}
                      onChange={(e) => { updateSetting('smtp_oauth_redirect_uri', e.target.value); setOauthDirty(true) }}
                      placeholder={`${typeof window !== 'undefined' ? window.location.origin : ''}/api/v2/settings/email/oauth/callback`}
                      helper={t('settings.smtpOauthRedirectUriHint')}
                    />
                    <div className="flex flex-wrap gap-2 mt-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          if (typeof window === 'undefined') return
                          const defaultUri = `${window.location.origin}/api/v2/settings/email/oauth/callback`
                          updateSetting('smtp_oauth_redirect_uri', defaultUri)
                          setOauthDirty(true)
                        }}
                      >
                        {t('settings.smtpOauthRedirectUriUseDefault')}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={!settings.smtp_oauth_redirect_uri}
                        onClick={() => {
                          const val = settings.smtp_oauth_redirect_uri || ''
                          if (!val) return
                          navigator.clipboard?.writeText(val)
                          showSuccess(t('common.copiedToClipboard'))
                        }}
                      >
                        <Copy size={14} className="mr-1.5" />
                        {t('common.copy')}
                      </Button>
                    </div>
                  </div>
                </DetailGrid>

                {/* Authorization status + actions */}
                {/* Unverified-app warning notice — only shown before authorization */}
                {!settings.has_oauth_refresh_token && ['google', 'microsoft', 'microsoft365'].includes(settings.smtp_oauth_provider || 'google') && (
                  <div className="flex items-start gap-2 p-3 bg-status-info-op10 border border-status-info-op30 rounded-lg text-xs text-text-secondary">
                    <Warning size={16} className="shrink-0 mt-0.5 text-status-info" />
                    <div className="space-y-1">
                      <p className="font-medium text-text-primary">{t('settings.smtpOauthUnverifiedTitle')}</p>
                      <p>{t('settings.smtpOauthUnverifiedBody')}</p>
                    </div>
                  </div>
                )}

                {/* Authorization status + actions */}
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                    settings.has_oauth_refresh_token
                      ? 'bg-status-success-op10 text-status-success'
                      : 'bg-bg-tertiary text-text-tertiary'
                  }`}>
                    {settings.has_oauth_refresh_token
                      ? <><CheckCircle size={13} />{t('settings.smtpOauthStatusAuthorized')}</>
                      : <><XCircle size={13} />{t('settings.smtpOauthStatusNotAuthorized')}</>
                    }
                  </span>

                  <Button
                    type="button"
                    size="sm"
                    onClick={handleSmtpOAuthAuthorize}
                    disabled={!settings.smtp_oauth_client_id || saving}
                    title={oauthDirty ? t('settings.smtpOauthAutoSaveHint') : undefined}
                  >
                    <Key size={14} />
                    {oauthDirty ? t('settings.smtpOauthSaveAndAuthorize') : t('settings.smtpOauthAuthorize')}
                  </Button>

                  {settings.has_oauth_refresh_token && (
                    <Button
                      type="button"
                      size="sm"
                      variant="danger-soft"
                      onClick={handleSmtpOAuthRevoke}
                    >
                      <XCircle size={14} />
                      {t('settings.smtpOauthRevoke')}
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Options */}
          <div className="border-t border-border pt-4 space-y-3">
            <DetailGrid>
              <div className="col-span-full md:col-span-1">
                <Input
                  label={t('settings.fromEmail')}
                  type="email"
                  value={settings.smtp_from_email || ''}
                  onChange={(e) => updateSetting('smtp_from_email', e.target.value)}
                  placeholder={t('settings.fromEmailPlaceholder')}
                />
              </div>
            </DetailGrid>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
              <ToggleSwitch
                checked={settings.smtp_use_tls || false}
                onChange={(val) => updateSetting('smtp_use_tls', val)}
                label={t('settings.useTls')}
                size="sm"
              />
              <div className="flex items-center gap-2">
                <span className="text-sm text-text-secondary">{t('settings.emailFormat')}:</span>
                {['html', 'text', 'both'].map(fmt => (
                  <button
                    key={fmt}
                    type="button"
                    onClick={() => updateSetting('smtp_content_type', fmt)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                      (settings.smtp_content_type || 'html') === fmt
                        ? 'bg-accent-primary text-white'
                        : 'bg-bg-tertiary text-text-secondary hover:bg-bg-secondary'
                    }`}
                  >
                    {t(`settings.emailFormat_${fmt}`)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Test result banner */}
          {emailTestResult && (
            <div className={`flex items-start gap-3 p-3 rounded-lg text-sm ${
              emailTestResult.success
                ? 'bg-status-success-op10 text-status-success'
                : 'bg-status-danger-op10 text-status-danger'
            }`}>
              {emailTestResult.success
                ? <CheckCircle size={18} className="shrink-0 mt-0.5" />
                : <WarningCircle size={18} className="shrink-0 mt-0.5" />
              }
              <span className="break-all">{emailTestResult.message}</span>
            </div>
          )}

          {/* Actions */}
          {canWrite('settings') && (
            <div className="space-y-3 pt-1">
              <DetailGrid>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label={t('settings.testRecipient')}
                    type="email"
                    value={settings._testRecipient || ''}
                    onChange={(e) => updateSetting('_testRecipient', e.target.value)}
                    placeholder={settings.smtp_from_email || 'admin@example.com'}
                  />
                </div>
                <div className="col-span-full md:col-span-1 flex items-end gap-2">
                  <Button type="button" variant="secondary" onClick={handleTestEmail} disabled={emailTesting}>
                    {emailTesting ? <ArrowsClockwise size={16} className="animate-spin" /> : <Envelope size={16} />}
                    {t('settings.testEmail')}
                  </Button>
                  <Button type="button" onClick={() => handleSave('email')} disabled={saving}>
                    <FloppyDisk size={16} />
                    {t('common.save')}
                  </Button>
                </div>
              </DetailGrid>
            </div>
          )}
        </div>
      </DetailSection>

      {/* Email Template */}
      <DetailSection title={t('settings.emailTemplate')} icon={EnvelopeSimple} iconClass="icon-bg-indigo">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-text-secondary">{t('settings.templateDescription')}</p>
          <div className="relative group shrink-0">
            <Button type="button" variant="secondary" size="sm" onClick={() => setShowTemplateEditor(true)} disabled={isMobile}>
              <PencilSimple size={16} />
              {t('settings.editTemplate')}
            </Button>
            {isMobile && (
              <div className="absolute bottom-full right-0 mb-1 px-2 py-1 rounded bg-bg-tertiary border border-border text-[11px] text-text-secondary whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity">
                {t('settings.templateDesktopOnly')}
              </div>
            )}
          </div>
        </div>
      </DetailSection>

      {showTemplateEditor && (
        <EmailTemplateWindow onClose={() => setShowTemplateEditor(false)} />
      )}

      <DetailSection title={t('settings.expiryAlerts')} icon={Bell} iconClass="icon-bg-rose">
        {!settings.smtp_host ? (
          <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-tertiary text-text-secondary text-sm">
            <Warning size={20} className="text-status-warning shrink-0" />
            {t('settings.smtpRequiredForAlerts')}
          </div>
        ) : (
        <div className="space-y-4">
          <ToggleSwitch
            checked={expiryAlerts.enabled}
            onChange={(val) => setExpiryAlerts(prev => ({ ...prev, enabled: val }))}
            label={t('settings.enableExpiryAlerts')}
            size="sm"
          />
          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              {t('settings.alertDays')}
            </label>
            <div className="flex flex-wrap gap-2">
              {[90, 60, 30, 14, 7, 3, 1].map(d => (
                <button
                  key={d}
                  type="button"
                  onClick={() => {
                    setExpiryAlerts(prev => ({
                      ...prev,
                      alert_days: prev.alert_days.includes(d)
                        ? prev.alert_days.filter(x => x !== d)
                        : [...prev.alert_days, d].sort((a, b) => b - a)
                    }))
                  }}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    expiryAlerts.alert_days.includes(d)
                      ? 'bg-accent-primary text-white'
                      : 'bg-bg-tertiary text-text-secondary hover:bg-bg-secondary'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
            <p className="text-xs text-text-tertiary mt-1">{t('settings.alertDaysHelp')}</p>
          </div>
          <TagsInput
            label={t('settings.alertRecipients')}
            value={expiryAlerts.recipients || []}
            onChange={(tags) => setExpiryAlerts(prev => ({ ...prev, recipients: tags }))}
            placeholder={t('settings.alertRecipientsPlaceholder')}
            helperText={t('settings.tagsInputHelp')}
            validate={(v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)}
          />
          <ToggleSwitch
            checked={expiryAlerts.include_revoked}
            onChange={(val) => setExpiryAlerts(prev => ({ ...prev, include_revoked: val }))}
            label={t('settings.includeRevoked')}
            size="sm"
          />
          {canWrite('settings') && (
            <div className="flex gap-2 pt-2">
              <Button type="button" variant="secondary" onClick={triggerExpiryCheck}>
                <Bell size={16} />
                {t('settings.checkNow')}
              </Button>
              <Button type="button" onClick={saveExpiryAlerts} disabled={saving}>
                <FloppyDisk size={16} />
                {t('common.saveChanges')}
              </Button>
            </div>
          )}
        </div>
        )}
      </DetailSection>
    </DetailContent>
  )
}
