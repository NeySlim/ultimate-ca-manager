import { useTranslation } from 'react-i18next'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks/useClipboard'
import { Bell, Warning, ArrowsClockwise, CheckCircle, XCircle, Key, Copy, Info, PencilSimple, PaperPlaneTilt, Question } from '@phosphor-icons/react'
import { Button, Input, Select } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import TagsInput from '../../components/ui/TagsInput'
import EmailTemplateWindow from '../../components/EmailTemplateWindow'
import { WarningCircle } from '@phosphor-icons/react'
import { secretInputProps, smtpSecretTargets } from '../../lib/secretTarget'
import { FormGroup } from '../../components/sectioned'

export default function EmailSection({ settings, fieldErrors = {}, savedEmail, updateSetting, saving, canWrite, isMobile, emailTestResult, emailTesting, handleTestEmail, defaultTestRecipient, oauthDirty, setOauthDirty, oauthPresets, applyOAuthProviderPreset, handleSmtpOAuthAuthorize, handleSmtpOAuthRevoke, expiryAlerts, setExpiryAlerts, triggerExpiryCheck, showTemplateEditor, setShowTemplateEditor }) {
  const { t } = useTranslation()
  const secretTargets = smtpSecretTargets(savedEmail, settings)
  const { showSuccess } = useNotification()
  const { copy } = useClipboard()
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
    <>
      <FormGroup title={t('settings.smtpConfig')}>
        <div className="space-y-5">
          {/* Server: host and sender, the port and the encryption as short fields */}
          <div className="sf-grid">
            <Input
              label={t('settings.smtpHost')}
              value={settings.smtp_host || ''}
              onChange={(e) => updateSetting('smtp_host', e.target.value)}
              placeholder={t('settings.smtpHostPlaceholder')}
            />
            <Input
              className="sf-short"
              label={t('settings.smtpPort')}
              type="number"
              inputMode="numeric"
              value={settings.smtp_port ?? 587}
              onChange={(e) => updateSetting('smtp_port', e.target.value === '' ? '' : Number(e.target.value))}
              error={fieldErrors.smtp_port}
            />
            <Select
              className="sf-short"
              label={t('settings.smtpSecurity')}
              value={settings.smtp_security || 'starttls'}
              onChange={(mode) => updateSetting('smtp_security', mode)}
              options={[['starttls', 'smtpSecurityStarttls'], ['ssl', 'smtpSecuritySsl'], ['none', 'smtpSecurityNone']]
                .map(([value, labelKey]) => ({ value, label: t(`settings.${labelKey}`) }))}
            />
            <Input
              label={t('settings.fromEmail')}
              type="email"
              value={settings.smtp_from_email || ''}
              onChange={(e) => updateSetting('smtp_from_email', e.target.value)}
              placeholder={t('settings.fromEmailPlaceholder')}
            />
            <Select
              label={t('settings.smtpAuthMethod')}
              value={settings.smtp_auth_method || 'password'}
              onChange={(method) => {
                updateSetting('smtp_auth_method', method)
                setOauthDirty(prev => prev || method === 'oauth2')
              }}
              options={['password', 'oauth2', 'none'].map((value) => ({ value, label: t(`settings.smtpAuthMethod_${value}`) }))}
            />
            <Select
              label={t('settings.emailFormat')}
              value={settings.smtp_content_type || 'html'}
              onChange={(fmt) => updateSetting('smtp_content_type', fmt)}
              options={['html', 'text', 'both'].map((value) => ({ value, label: t(`settings.emailFormat_${value}`) }))}
              helperText={t('settings.smtpSecurityHint')}
            />
          </div>

          {/* Authentication: what the chosen method asks */}
          <div className="space-y-3">
            {(settings.smtp_auth_method || 'password') === 'none' && (
              <p className="text-xs text-text-tertiary">{t('settings.smtpNoAuthHint')}</p>
            )}
            {/* Saving without authentication deletes the stored OAuth2 credentials (api/v2/settings/email) */}
            {(settings.smtp_auth_method || 'password') === 'none' &&
              (settings.has_oauth_client_secret || settings.has_oauth_refresh_token) && (
              <p className="flex items-start gap-1.5 text-xs text-status-warning">
                <Warning size={14} className="mt-0.5 shrink-0" />
                {t('settings.smtpNoAuthClearsOauth')}
              </p>
            )}

            {(settings.smtp_auth_method || 'password') === 'password' && (
              <div className="sf-fields">
                  <Input
                    label={t('settings.smtpUsername')}
                    value={settings.smtp_username || ''}
                    onChange={(e) => updateSetting('smtp_username', e.target.value)}
                  />
                  <Input
                    label={t('settings.smtpPassword')}
                    type="password"
                    noAutofill
                    value={settings.smtp_password === '********' ? '' : (settings.smtp_password || '')}
                    onChange={(e) => updateSetting('smtp_password', e.target.value)}
                    hasExistingValue={settings.smtp_password === '********'}
                    {...secretInputProps(t, secretTargets.password)}
                  />
              </div>
            )}

            {(settings.smtp_auth_method || 'password') === 'oauth2' && (
              <div className="space-y-3">
                {/* Mailbox / username (XOAUTH2 uses email address as user) */}
                <div className="sf-fields">
                  <div className="col-span-full md:col-span-1">
                    <Input
                      label={t('settings.smtpUsername')}
                      value={settings.smtp_username || ''}
                      onChange={(e) => updateSetting('smtp_username', e.target.value)}
                    />
                  </div>
                </div>

                {/* Provider: a preset that fills the endpoints */}
                <div className="ui-field">
                  <span className="ui-label" id="smtp-oauth-provider">{t('settings.smtpOauthProvider')}</span>
                  <div className="ui-segmented" role="group" aria-labelledby="smtp-oauth-provider">
                    {['google', 'microsoft', 'microsoft365', 'custom'].map(provider => (
                      <button
                        key={provider}
                        type="button"
                        aria-pressed={(settings.smtp_oauth_provider || 'google') === provider}
                        onClick={() => applyOAuthProviderPreset(provider)}
                      >
                        {t(`settings.smtpOauthProvider_${provider}`)}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Per-provider setup guide */}
                {oauthProviderSetup[settings.smtp_oauth_provider || 'google'] && (
                  <div className="ui-notice">
                    <Info aria-hidden="true" />
                    <div className="ui-notice-body space-y-1.5">
                      <p><strong>
                        {t(`settings.smtpOauthSetup_${settings.smtp_oauth_provider || 'google'}_title`)}
                      </strong></p>
                      <p className="whitespace-pre-line">
                        {t(`settings.smtpOauthSetup_${settings.smtp_oauth_provider || 'google'}_steps`)}
                      </p>
                      <a
                        href={oauthProviderSetup[settings.smtp_oauth_provider || 'google'].consoleUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-accent-primary hover:underline"
                      >
                        {oauthProviderSetup[settings.smtp_oauth_provider || 'google'].consoleLabel} ↗
                      </a>
                    </div>
                  </div>
                )}

                <div className="sf-fields">
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
                      {...secretInputProps(t, secretTargets.oauth)}
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
                        onClick={async () => {
                          const val = settings.smtp_oauth_redirect_uri || ''
                          if (!val) return
                          // Plain HTTP has no async clipboard API: only
                          // say it was copied once it really was.
                          if (await copy(val)) showSuccess(t('common.copiedToClipboard'))
                        }}
                      >
                        <Copy size={14} className="mr-1.5" />
                        {t('common.copy')}
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Authorization status + actions */}
                {/* Unverified-app warning notice — only shown before authorization */}
                {!settings.has_oauth_refresh_token && ['google', 'microsoft', 'microsoft365'].includes(settings.smtp_oauth_provider || 'google') && (
                  <div className="ui-notice is-warn">
                    <Warning aria-hidden="true" />
                    <div className="ui-notice-body">
                      <p><strong>{t('settings.smtpOauthUnverifiedTitle')}</strong></p>
                      <p>{t('settings.smtpOauthUnverifiedBody')}</p>
                    </div>
                  </div>
                )}

                {/* Authorization status + actions */}
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <span className={`inline-flex items-center gap-1.5 text-xs ${
                    settings.has_oauth_refresh_token ? 'text-status-success' : 'text-text-secondary'
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

          {/* Test of the saved relay: the recipient, the button and its result on one line */}
          {canWrite('settings') && (
            <div className="sf-test">
              <Input
                className="sf-test-field"
                label={t('settings.testRecipient')}
                type="email"
                value={settings._testRecipient || ''}
                onChange={(e) => updateSetting('_testRecipient', e.target.value)}
                placeholder={defaultTestRecipient || 'admin@example.com'}
              />
              <Button type="button" variant="secondary" onClick={handleTestEmail} disabled={emailTesting}>
                {emailTesting ? <ArrowsClockwise size={16} className="animate-spin" /> : <PaperPlaneTilt size={16} />}
                {t('settings.testEmail')}
              </Button>
              {emailTestResult ? (
                <p className={`sf-test-result ${emailTestResult.success ? 'is-good' : 'is-bad'}`} role="status">
                  {emailTestResult.success ? <CheckCircle aria-hidden="true" /> : <WarningCircle aria-hidden="true" />}
                  <span className="break-all">{emailTestResult.message}</span>
                </p>
              ) : (
                <p className="sf-test-result">
                  <Question aria-hidden="true" />
                  <span>{t('settings.testEmailSavedHint')}</span>
                </p>
              )}
            </div>
          )}
        </div>
      </FormGroup>

      {/* Email Template */}
      <FormGroup title={t('settings.emailTemplate')}>
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-text-secondary">{t('settings.templateDescription')}</p>
          <div className="relative group shrink-0">
            <Button type="button" variant="secondary" size="sm" onClick={() => setShowTemplateEditor(true)} disabled={isMobile}>
              <PencilSimple size={16} />
              {t('settings.editTemplate')}
            </Button>
            {isMobile && (
              <div className="absolute bottom-full right-0 mb-1 px-2 py-1 rounded bg-bg-tertiary border border-border text-xs text-text-secondary whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity">
                {t('settings.templateDesktopOnly')}
              </div>
            )}
          </div>
        </div>
      </FormGroup>

      {showTemplateEditor && (
        <EmailTemplateWindow onClose={() => setShowTemplateEditor(false)} />
      )}

      <FormGroup title={t('settings.expiryAlerts')}>
        {!settings.smtp_host ? (
          <p className="ui-notice is-warn">
            <Warning aria-hidden="true" />
            <span className="ui-notice-body">{t('settings.smtpRequiredForAlerts')}</span>
          </p>
        ) : (
        <div className="space-y-4">
          <ToggleSwitch
            checked={expiryAlerts.enabled}
            onChange={(val) => setExpiryAlerts(prev => ({ ...prev, enabled: val }))}
            label={t('settings.enableExpiryAlerts')}
            size="sm"
          />
          <div className="ui-field">
            <span className="ui-label" id="expiry-alert-days">{t('settings.alertDays')}</span>
            <div className="ui-segmented" role="group" aria-labelledby="expiry-alert-days">
              {[90, 60, 30, 14, 7, 3, 1].map(d => (
                <button
                  key={d}
                  type="button"
                  aria-pressed={expiryAlerts.alert_days.includes(d)}
                  onClick={() => {
                    setExpiryAlerts(prev => ({
                      ...prev,
                      alert_days: prev.alert_days.includes(d)
                        ? prev.alert_days.filter(x => x !== d)
                        : [...prev.alert_days, d].sort((a, b) => b - a)
                    }))
                  }}
                >
                  {t('time.short.days', { count: d })}
                </button>
              ))}
            </div>
            <p className="ui-help">{t('settings.alertDaysHelp')}</p>
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
          <ToggleSwitch
            checked={!!expiryAlerts.exclude_acme}
            onChange={(val) => setExpiryAlerts(prev => ({ ...prev, exclude_acme: val }))}
            label={t('settings.excludeAcme')}
            description={t('settings.excludeAcmeDesc')}
            size="sm"
          />
          {canWrite('settings') && (
            <div className="flex gap-2 pt-2">
              <Button type="button" variant="secondary" onClick={triggerExpiryCheck}>
                <Bell size={16} />
                {t('settings.checkNow')}
              </Button>
            </div>
          )}
        </div>
        )}
      </FormGroup>
    </>
  )
}
