import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks/useClipboard'
import { Btn, Pill, Notice, RecordList, RecordRow } from '../../components/atelier'
import { Input, NumberInput, SecretInput, Select, ToggleSwitch, SegmentedField, ListInput } from '../../components/atelier/Form'
import { SettingsGroup, SettingsTest } from '../../components/atelier/SettingsView'
import EmailTemplateDialog from './EmailTemplateDialog'
import { secretInputProps, smtpSecretTargets } from '../../lib/secretTarget'
import { useRefocusAfter } from '../../hooks/useRefocus'
import { shownNumber, typedNumber } from './numberFields'

const OAUTH_CONSOLES = {
  google: { consoleUrl: 'https://console.cloud.google.com/apis/credentials', consoleLabel: 'Google Cloud Console → APIs & Services → Credentials' },
  microsoft: { consoleUrl: 'https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade', consoleLabel: 'Azure Portal → App registrations' },
  microsoft365: { consoleUrl: 'https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade', consoleLabel: 'Azure Portal → App registrations' },
}
const ALERT_DAYS = [90, 60, 30, 14, 7, 3, 1]
const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)

export default function EmailSection({ settings, fieldErrors = {}, savedEmail, updateSetting, saving, canWrite, isMobile, emailTestResult, emailTesting, handleTestEmail, defaultTestRecipient, oauthDirty, setOauthDirty, applyOAuthProviderPreset, handleSmtpOAuthAuthorize, handleSmtpOAuthRevoke, expiryAlerts, setExpiryAlerts, triggerExpiryCheck, showTemplateEditor, setShowTemplateEditor }) {
  const { t } = useTranslation()
  const testButton = useRef(null)
  useRefocusAfter(emailTesting, testButton)
  const secretTargets = smtpSecretTargets(savedEmail, settings)
  const { showSuccess } = useNotification()
  const { copy } = useClipboard()
  const method = settings.smtp_auth_method || 'password'
  const provider = settings.smtp_oauth_provider || 'google'
  const oauth = (key) => (e) => { updateSetting(key, e.target.value); setOauthDirty(true) }
  const defaultRedirect = `${typeof window !== 'undefined' ? window.location.origin : ''}/api/v2/settings/email/oauth/callback`
  return (
    <>
      <SettingsGroup legend={t('settings.smtpConfig')}>
        <Input id="set-smtp_host" label={t('settings.smtpHost')} value={settings.smtp_host || ''}
          onChange={(e) => updateSetting('smtp_host', e.target.value)} placeholder={t('settings.smtpHostPlaceholder')} />
        <NumberInput id="set-smtp_port" label={t('settings.smtpPort')} value={shownNumber(settings.smtp_port ?? 587)}
          onChange={(e) => updateSetting('smtp_port', typedNumber(e))} error={fieldErrors.smtp_port} hint={t('settings.smtpSecurityHint')} />
        <Select id="set-smtp_security" short label={t('settings.smtpSecurity')} value={settings.smtp_security || 'starttls'}
          onChange={(mode) => updateSetting('smtp_security', mode)}
          options={[['starttls', 'smtpSecurityStarttls'], ['ssl', 'smtpSecuritySsl'], ['none', 'smtpSecurityNone']]
            .map(([value, labelKey]) => ({ value, label: t(`settings.${labelKey}`) }))} />
        <Input id="set-smtp_from_email" label={t('settings.fromEmail')} type="email" value={settings.smtp_from_email || ''}
          onChange={(e) => updateSetting('smtp_from_email', e.target.value)} error={fieldErrors.smtp_from_email}
          placeholder={t('settings.fromEmailPlaceholder')} />
        <Select id="set-smtp_auth_method" label={t('settings.smtpAuthMethod')} value={method}
          onChange={(next) => { updateSetting('smtp_auth_method', next); setOauthDirty((prev) => prev || next === 'oauth2') }}
          options={['password', 'oauth2', 'none'].map((value) => ({ value, label: t(`settings.smtpAuthMethod_${value}`) }))} />
        <Select id="set-smtp_content_type" label={t('settings.emailFormat')} value={settings.smtp_content_type || 'html'}
          onChange={(fmt) => updateSetting('smtp_content_type', fmt)}
          options={['html', 'text', 'both'].map((value) => ({ value, label: t(`settings.emailFormat_${value}`) }))} />
        {/* Where the test of the relay sends its message */}
        {canWrite('settings') && (
          <Input id="set-test_recipient" label={t('settings.testRecipient')} type="email" value={settings._testRecipient || ''}
            onChange={(e) => updateSetting('_testRecipient', e.target.value)} placeholder={defaultTestRecipient || 'admin@example.com'} />
        )}

        {/* Authentication: what the chosen method asks */}
        {method === 'none' && <Notice>{t('settings.smtpNoAuthHint')}</Notice>}
        {/* Saving without authentication deletes the stored OAuth2 credentials (api/v2/settings/email) */}
        {method === 'none' && (settings.has_oauth_client_secret || settings.has_oauth_refresh_token) && (
          <Notice tone="warn">{t('settings.smtpNoAuthClearsOauth')}</Notice>
        )}
        {method === 'password' && (
          <>
            <Input id="set-smtp_username" label={t('settings.smtpUsername')} value={settings.smtp_username || ''}
              onChange={(e) => updateSetting('smtp_username', e.target.value)} />
            <SecretInput id="set-smtp_password" label={t('settings.smtpPassword')}
              value={settings.smtp_password === '********' ? '' : (settings.smtp_password || '')}
              onChange={(e) => updateSetting('smtp_password', e.target.value)} hasExistingValue={settings.smtp_password === '********'}
              {...secretInputProps(t, secretTargets.password)} />
          </>
        )}
        {method === 'oauth2' && (
          <>
            {/* Mailbox / username (XOAUTH2 uses email address as user) */}
            <Input id="set-smtp_username" label={t('settings.smtpUsername')} value={settings.smtp_username || ''}
              onChange={(e) => updateSetting('smtp_username', e.target.value)} />
            {/* Provider: a preset that fills the endpoints */}
            <SegmentedField id="set-smtp_oauth_provider" label={t('settings.smtpOauthProvider')}
              options={['google', 'microsoft', 'microsoft365', 'custom'].map((p) => ({ value: p, label: t(`settings.smtpOauthProvider_${p}`) }))}
              pressed={(p) => provider === p} onPick={applyOAuthProviderPreset} />
            {OAUTH_CONSOLES[provider] && (
              <Notice>
                <strong>{t(`settings.smtpOauthSetup_${provider}_title`)}</strong>{' '}
                <span className="pre-line">{t(`settings.smtpOauthSetup_${provider}_steps`)}</span>{' '}
                <a className="text-link" href={OAUTH_CONSOLES[provider].consoleUrl} target="_blank" rel="noopener noreferrer">
                  {OAUTH_CONSOLES[provider].consoleLabel} ↗
                </a>
              </Notice>
            )}
            {provider === 'microsoft365' && (
              <Input id="set-smtp_oauth_tenant_id" label={t('settings.smtpOauthTenant')} value={settings.smtp_oauth_tenant_id || ''}
                onChange={oauth('smtp_oauth_tenant_id')} placeholder="common" hint={t('settings.smtpOauthTenantHintM365')} />
            )}
            <Input id="set-smtp_oauth_client_id" label={t('settings.smtpOauthClientId')} value={settings.smtp_oauth_client_id || ''}
              onChange={oauth('smtp_oauth_client_id')} />
            <SecretInput id="set-smtp_oauth_client_secret" label={t('settings.smtpOauthClientSecret')}
              value={settings.smtp_oauth_client_secret === '********' ? '' : (settings.smtp_oauth_client_secret || '')}
              onChange={oauth('smtp_oauth_client_secret')} hasExistingValue={settings.has_oauth_client_secret}
              {...secretInputProps(t, secretTargets.oauth)} />
            {provider === 'custom' && (
              <>
                <Input id="set-smtp_oauth_authorize_url" label={t('settings.smtpOauthAuthorizeUrl')} value={settings.smtp_oauth_authorize_url || ''}
                  onChange={oauth('smtp_oauth_authorize_url')} />
                <Input id="set-smtp_oauth_token_url" label={t('settings.smtpOauthTokenUrl')} value={settings.smtp_oauth_token_url || ''}
                  onChange={oauth('smtp_oauth_token_url')} />
                <Input id="set-smtp_oauth_scope" label={t('settings.smtpOauthScope')} value={settings.smtp_oauth_scope || ''}
                  onChange={oauth('smtp_oauth_scope')} />
              </>
            )}
            <Input id="set-smtp_oauth_redirect_uri" full label={t('settings.smtpOauthRedirectUri')} value={settings.smtp_oauth_redirect_uri || ''}
              onChange={oauth('smtp_oauth_redirect_uri')} placeholder={defaultRedirect} hint={t('settings.smtpOauthRedirectUriHint')} />
            <div className="settings-actions">
              <Btn onClick={() => { updateSetting('smtp_oauth_redirect_uri', defaultRedirect); setOauthDirty(true) }}>
                {t('settings.smtpOauthRedirectUriUseDefault')}
              </Btn>
              <Btn tone="quiet" icon="copy" disabled={!settings.smtp_oauth_redirect_uri}
                onClick={async () => {
                  const val = settings.smtp_oauth_redirect_uri || ''
                  // Plain HTTP has no async clipboard API: only say it was copied once it really was.
                  if (val && await copy(val)) showSuccess(t('common.copiedToClipboard'))
                }}>
                {t('common.copy')}
              </Btn>
            </div>
            {/* Unverified-app warning notice, only shown before authorization */}
            {!settings.has_oauth_refresh_token && ['google', 'microsoft', 'microsoft365'].includes(provider) && (
              <Notice tone="warn"><strong>{t('settings.smtpOauthUnverifiedTitle')}</strong>{' '}{t('settings.smtpOauthUnverifiedBody')}</Notice>
            )}
            {/* Authorization status and actions */}
            <div className="settings-actions">
              <Pill tone={settings.has_oauth_refresh_token ? 'good' : 'muted'}
                label={settings.has_oauth_refresh_token ? t('settings.smtpOauthStatusAuthorized') : t('settings.smtpOauthStatusNotAuthorized')} />
              <Btn tone="primary" icon="key" onClick={handleSmtpOAuthAuthorize} disabled={!settings.smtp_oauth_client_id || saving}
                title={oauthDirty ? t('settings.smtpOauthAutoSaveHint') : undefined}>
                {oauthDirty ? t('settings.smtpOauthSaveAndAuthorize') : t('settings.smtpOauthAuthorize')}
              </Btn>
              {settings.has_oauth_refresh_token && (
                <Btn tone="danger" icon="block" onClick={handleSmtpOAuthRevoke}>{t('settings.smtpOauthRevoke')}</Btn>
              )}
            </div>
          </>
        )}
      </SettingsGroup>

      <SettingsGroup legend={t('settings.emailTemplate')} grid={false}>
        <RecordList>
          <RecordRow title={t('settings.emailTemplate')} meta={isMobile ? t('settings.templateDesktopOnly') : t('settings.templateDescription')}
            action={<Btn icon="file" onClick={() => setShowTemplateEditor(true)} disabled={isMobile}>{t('settings.editTemplate')}</Btn>} />
        </RecordList>
      </SettingsGroup>
      {showTemplateEditor && (
        <EmailTemplateDialog onClose={() => setShowTemplateEditor(false)} />
      )}

      <SettingsGroup legend={t('settings.expiryAlerts')}>
        {!settings.smtp_host ? (
          <Notice tone="warn">{t('settings.smtpRequiredForAlerts')}</Notice>
        ) : (
          <>
            <ToggleSwitch id="set-expiry_enabled" checked={expiryAlerts.enabled}
              onChange={(val) => setExpiryAlerts((prev) => ({ ...prev, enabled: val }))} label={t('settings.enableExpiryAlerts')} />
            <SegmentedField id="set-expiry_alert_days" label={t('settings.alertDays')} hint={t('settings.alertDaysHelp')}
              options={ALERT_DAYS.map((d) => ({ value: d, label: t('time.short.days', { count: d }) }))}
              pressed={(d) => expiryAlerts.alert_days.includes(d)}
              onPick={(d) => setExpiryAlerts((prev) => ({
                ...prev,
                alert_days: prev.alert_days.includes(d) ? prev.alert_days.filter((x) => x !== d) : [...prev.alert_days, d].sort((a, b) => b - a),
              }))} />
            <ListInput id="set-expiry_recipients" full label={t('settings.alertRecipients')} value={expiryAlerts.recipients || []}
              onChange={(list) => setExpiryAlerts((prev) => ({ ...prev, recipients: list }))} validate={isEmail}
              invalidMessage={(bad) => t('settings.alertRecipientsInvalid', { list: bad.join(', ') })}
              placeholder={t('settings.alertRecipientsPlaceholder')} hint={t('settings.alertRecipientsHint')} />
            <ToggleSwitch id="set-expiry_include_revoked" checked={expiryAlerts.include_revoked}
              onChange={(val) => setExpiryAlerts((prev) => ({ ...prev, include_revoked: val }))} label={t('settings.includeRevoked')} />
            <ToggleSwitch id="set-expiry_exclude_acme" checked={!!expiryAlerts.exclude_acme}
              onChange={(val) => setExpiryAlerts((prev) => ({ ...prev, exclude_acme: val }))} label={t('settings.excludeAcme')}
              description={t('settings.excludeAcmeDesc')} />
            {canWrite('settings') && (
              <div className="settings-actions">
                <Btn icon="bell" onClick={triggerExpiryCheck}>{t('settings.checkNow')}</Btn>
              </div>
            )}
          </>
        )}
      </SettingsGroup>
      {/* Test of the saved relay, last in the frame as in the mockup: the button and its result */}
      {canWrite('settings') && (
        <SettingsTest id="email" label={t('settings.testEmail')} onTest={handleTestEmail} busy={emailTesting} buttonRef={testButton}
          result={emailTestResult ? { ok: emailTestResult.success, text: emailTestResult.message } : null}
          hint={t('settings.testEmailSavedHint')} />
      )}
    </>
  )
}
