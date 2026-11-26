import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Icon, Pill } from '../../components/atelier'
import { Input, SecretInput, Select, ToggleSwitch, Notice } from '../../components/atelier/Form'
import { FieldError } from '../../components/atelier/SettingsView'
import { changedTargets, secretRequiredForTarget } from '../../lib/secretTarget'

const WEBHOOK_EVENTS = [
  'certificate.issued',
  'certificate.revoked',
  'certificate.unheld',
  'certificate.renewed',
  'certificate.expiring',
  'certificate.expired',
  'certificate.imported',
  'certificate.deleted',
  'certificate.binding_left_behind',
  'ca.created',
  'ca.updated',
  'ca.deleted',
  'csr.submitted',
  'csr.approved',
  'csr.rejected',
  'template.created',
  'template.updated',
  'acme.preflight',
  'acme_order.renewal_failed',
  'acme_order.revocation_failed',
  'system.update_available',
  'system.update_initiated',
  'system.update_installed',
  'system.update_failed',
]

// labelKey pattern: i18n keys stored at module level, resolved with t()
export const WEBHOOK_EVENT_LABEL_KEYS = {
  'certificate.issued': 'webhooks.eventLabels.certificateIssued',
  'certificate.revoked': 'webhooks.eventLabels.certificateRevoked',
  'certificate.unheld': 'webhooks.eventLabels.certificateUnheld',
  'certificate.renewed': 'webhooks.eventLabels.certificateRenewed',
  'certificate.expiring': 'webhooks.eventLabels.certificateExpiring',
  'certificate.expired': 'webhooks.eventLabels.certificateExpired',
  'certificate.imported': 'webhooks.eventLabels.certificateImported',
  'certificate.deleted': 'webhooks.eventLabels.certificateDeleted',
  'certificate.binding_left_behind': 'webhooks.eventLabels.certificateBindingLeftBehind',
  'ca.created': 'webhooks.eventLabels.caCreated',
  'ca.updated': 'webhooks.eventLabels.caUpdated',
  'ca.deleted': 'webhooks.eventLabels.caDeleted',
  'csr.submitted': 'webhooks.eventLabels.csrSubmitted',
  'csr.approved': 'webhooks.eventLabels.csrApproved',
  'csr.rejected': 'webhooks.eventLabels.csrRejected',
  'template.created': 'webhooks.eventLabels.templateCreated',
  'template.updated': 'webhooks.eventLabels.templateUpdated',
  'acme.preflight': 'webhooks.eventLabels.acmePreflight',
  'acme_order.renewal_failed': 'webhooks.eventLabels.acmeOrderRenewalFailed',
  'acme_order.revocation_failed': 'webhooks.eventLabels.acmeOrderRevocationFailed',
  'system.update_available': 'webhooks.eventLabels.systemUpdateAvailable',
  'system.update_initiated': 'webhooks.eventLabels.systemUpdateInitiated',
  'system.update_installed': 'webhooks.eventLabels.systemUpdateInstalled',
  'system.update_failed': 'webhooks.eventLabels.systemUpdateFailed',
}

export const webhookEventLabel = (t, event) =>
  WEBHOOK_EVENT_LABEL_KEYS[event] ? t(WEBHOOK_EVENT_LABEL_KEYS[event]) : event

// labelKey pattern: module-level constant, resolved with t() in component
const AUTH_TYPE_OPTIONS = [
  { value: 'none',    labelKey: 'webhooks.auth.type.options.none' },
  { value: 'bearer',  labelKey: 'webhooks.auth.type.options.bearer' },
  { value: 'basic',   labelKey: 'webhooks.auth.type.options.basic' },
  { value: 'api_key', labelKey: 'webhooks.auth.type.options.api_key' },
  { value: 'custom',  labelKey: 'webhooks.auth.type.options.custom' },
]

const TOKEN_MAX_BYTES = 8192

function byteLength(str) {
  return new TextEncoder().encode(str).length
}

// RFC 7617 charset=UTF-8: user-pass is encoded as UTF-8 before base64
function utf8Base64(str) {
  let binary = ''
  for (const byte of new TextEncoder().encode(str)) binary += String.fromCharCode(byte)
  return btoa(binary)
}

function maskToken(token) {
  if (!token) return '•••••••••'
  if (token.length <= 8) return '•'.repeat(token.length)
  return token.slice(0, 3) + '•••' + token.slice(-3)
}

export default function WebhookForm({ webhook, onSave, onCancel }) {
  const { t } = useTranslation()
  const isEditing = Boolean(webhook)

  const [formData, setFormData] = useState({
    name: webhook?.name || '',
    url: webhook?.url || '',
    events: webhook?.events || [],
    ca_filter: webhook?.ca_filter || '',
    enabled: webhook?.enabled ?? true,
    // Auth fields — Radix Select drives these, NOT FormData
    auth_type: webhook?.auth_type || 'none',
    auth_username: webhook?.auth_username || '',
    auth_header_name: webhook?.auth_header_name || '',
    auth_token: '',           // never pre-filled (server never returns plaintext)
    auth_token_set: webhook?.auth_token_set || false,
    auth_token_cleared: false, // tracks explicit "clear" action
    drop_custom_headers: false,
  })

  const [validationErrors, setValidationErrors] = useState({})
  const [previewRevealed, setPreviewRevealed] = useState(false)

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    if (validationErrors[field]) {
      setValidationErrors(prev => { const next = { ...prev }; delete next[field]; return next })
    }
  }

  const handleAuthTypeChange = (value) => {
    setFormData(prev => ({
      ...prev,
      auth_type: value,
      // reset dependent fields when type changes
      auth_token: '',
      auth_token_cleared: false,
    }))
    setValidationErrors({})
    setPreviewRevealed(false)
  }

  const handleClearToken = () => {
    setFormData(prev => ({ ...prev, auth_token: '', auth_token_set: false, auth_token_cleared: true }))
  }

  const toggleEvent = (event) => {
    setFormData(prev => ({
      ...prev,
      events: prev.events.includes(event)
        ? prev.events.filter(e => e !== event)
        : [...prev.events, event]
    }))
  }

  const toggleAllEvents = () => {
    setFormData(prev => ({
      ...prev,
      events: prev.events.length === WEBHOOK_EVENTS.length ? [] : [...WEBHOOK_EVENTS]
    }))
  }

  // A moved URL needs the token typed again: show the field, with the reason
  const tokenMustRetype = formData.auth_type !== 'none' && secretRequiredForTarget({
    saved: webhook, current: formData, fields: ['url'], secret: formData.auth_token,
    secretSaved: formData.auth_token_set && !formData.auth_token_cleared,
  })

  // Headers set through the API can't be retyped here: a moved URL drops them
  const urlMoved = Boolean(webhook) && changedTargets(webhook, formData, ['url']).length > 0
  const headersMustGo = Boolean(webhook?.custom_headers_set) && urlMoved && !formData.drop_custom_headers

  // Client-side validation mirroring backend rules
  const validate = () => {
    const errors = {}
    if (headersMustGo) errors.custom_headers = t('webhooks.customHeadersFollowUrl')
    const { auth_type, auth_token, auth_username, auth_header_name, auth_token_set, auth_token_cleared } = formData

    if (auth_type !== 'none') {
      const tokenPresent = auth_token_set && !auth_token_cleared
      const tokenProvided = auth_token.length > 0
      // If user explicitly cleared the token, allow submit (sends null to backend)
      const needsToken = !auth_token_cleared && !tokenPresent && !tokenProvided

      if (needsToken) {
        errors.auth_token = t('webhooks.auth.errors.tokenRequired')
      } else if (tokenMustRetype) {
        errors.auth_token = t('common.secretRequiredForTarget')
      } else if (tokenProvided && byteLength(auth_token) > TOKEN_MAX_BYTES) {
        errors.auth_token = t('webhooks.auth.errors.tokenTooLong')
      }

      if (auth_type === 'basic' && !auth_username.trim()) {
        errors.auth_username = t('webhooks.auth.errors.usernameRequired')
      }

      if ((auth_type === 'api_key' || auth_type === 'custom') && !auth_header_name.trim()) {
        errors.auth_header_name = t('webhooks.auth.errors.headerNameRequired')
      }

      if (auth_type === 'api_key' && auth_header_name.trim().toLowerCase() === 'authorization') {
        errors.auth_header_name = t('webhooks.auth.errors.authorizationBlocked')
      }
    }

    return errors
  }

  const handleSubmit = (e) => {
    e.preventDefault()

    const errors = validate()
    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors)
      return
    }

    // Build payload — handle auth field semantics:
    // Empty strings ("") trigger 400 from backend ("cannot be empty, use null to clear").
    // Convert empty strings → null so the backend clears the field.
    const { auth_token_set: _ignored, auth_token_cleared, auth_token, auth_username, auth_header_name,
      drop_custom_headers, ...rest } = formData

    const payload = { ...rest }
    if (drop_custom_headers && urlMoved) payload.custom_headers = {}

    // auth_token: cleared → null, new value → include, otherwise omit (preserve)
    if (auth_token_cleared) {
      payload.auth_token = null
    } else if (auth_token.length > 0) {
      payload.auth_token = auth_token
    }

    // auth_username: empty → null (clear), non-empty → include, otherwise omit
    if (auth_username.trim().length > 0) {
      payload.auth_username = auth_username
    } else {
      payload.auth_username = null
    }

    // auth_header_name: same logic as auth_username
    if (auth_header_name.trim().length > 0) {
      payload.auth_header_name = auth_header_name
    } else {
      payload.auth_header_name = null
    }

    onSave(payload)
  }

  // Preview logic: compute outgoing header from current form state
  const preview = useMemo(() => {
    const { auth_type, auth_token, auth_username, auth_header_name, auth_token_set, auth_token_cleared } = formData
    if (auth_type === 'none') return null

    const hasToken = (auth_token.length > 0) || (auth_token_set && !auth_token_cleared)
    if (!hasToken) return null

    const displayToken = auth_token.length > 0 ? auth_token : null // null = stored but unknown

    if (auth_type === 'bearer') {
      return {
        headerName: 'Authorization',
        maskedValue: `Bearer ${displayToken ? maskToken(displayToken) : '•••••••••'}`,
        revealedValue: displayToken ? `Bearer ${displayToken}` : null,
      }
    }
    if (auth_type === 'basic') {
      const user = auth_username || 'user'
      // The mask is never base64-encoded (U+2022 is outside Latin-1, btoa throws)
      const revealedB64 = displayToken ? utf8Base64(`${user}:${displayToken}`) : null
      return {
        headerName: 'Authorization',
        maskedValue: 'Basic •••••••••',
        revealedValue: revealedB64 ? `Basic ${revealedB64}` : null,
      }
    }
    if (auth_type === 'api_key') {
      const header = auth_header_name.trim() || 'X-API-Key'
      return {
        headerName: header,
        maskedValue: displayToken ? maskToken(displayToken) : '•••••••••',
        revealedValue: displayToken || null,
      }
    }
    if (auth_type === 'custom') {
      const header = auth_header_name.trim() || 'Authorization'
      return {
        headerName: header,
        maskedValue: displayToken ? maskToken(displayToken) : '•••••••••',
        revealedValue: displayToken || null,
      }
    }
    return null
  }, [formData])

  const tokenBytes = byteLength(formData.auth_token)
  const showTokenByteCount = formData.auth_token.length > 0 && tokenBytes > TOKEN_MAX_BYTES * 0.8

  const showHeaderNameAuthorizationWarning =
    formData.auth_type === 'api_key' &&
    formData.auth_header_name.trim().toLowerCase() === 'authorization'

  const showTokenSetBadge =
    formData.auth_token_set &&
    !formData.auth_token_cleared &&
    formData.auth_token.length === 0 &&
    !tokenMustRetype

  const tokenError = validationErrors.auth_token || (tokenMustRetype ? t('common.secretRequiredForTarget') : undefined)
  // The token: « set » with its clear action while one is stored and nothing is typed, else the field
  const tokenField = showTokenSetBadge ? (
    <div className="field">
      <span>{t('webhooks.auth.token.label')}{' '}<Pill tone="good" label={t('common.set')} /></span>
      <small>{t('webhooks.auth.token.set')}</small>
      <button type="button" className="text-link bad" onClick={handleClearToken}>
        <Icon name="close" />{t('webhooks.auth.token.clear')}
      </button>
    </div>
  ) : (
    <SecretInput id="webhook-token" label={t('webhooks.auth.token.label')} value={formData.auth_token}
      onChange={e => handleChange('auth_token', e.target.value)} placeholder={t('webhooks.auth.token.placeholder')}
      error={tokenError} hint={showTokenByteCount ? `${tokenBytes} / ${TOKEN_MAX_BYTES} bytes` : undefined} />
  )

  // The mockup's dialog form: the endpoint, its authentication and its events in `.form-fields`, then the actions
  return (
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
        <Input id="webhook-name" label={t('common.name')} value={formData.name} onChange={e => handleChange('name', e.target.value)}
          required placeholder={t('webhooks.namePlaceholder')} data-autofocus="" />
        <Input id="webhook-url" label="URL" value={formData.url} onChange={e => handleChange('url', e.target.value)}
          required placeholder="https://example.com/webhook" />
        {webhook?.custom_headers_set && (
          <div className="field full">
            <small>{t('webhooks.customHeadersSet')}</small>
            {urlMoved && (
              <label className="checkbox-line">
                <input type="checkbox" checked={formData.drop_custom_headers} onChange={e => handleChange('drop_custom_headers', e.target.checked)} />
                {t('webhooks.dropCustomHeaders')}
              </label>
            )}
            {headersMustGo && <FieldError id="err-webhook-headers" message={t('webhooks.customHeadersFollowUrl')} />}
          </div>
        )}
        <Input id="webhook-ca-filter" full label={t('webhooks.caFilter')} value={formData.ca_filter} onChange={e => handleChange('ca_filter', e.target.value)}
          placeholder={t('webhooks.caFilterPlaceholder')} />

        {/* Authentication */}
        <fieldset className="field full">
          <legend>{t('webhooks.auth.title')}</legend>
          <div className="form-fields">
            <Select id="webhook-auth-type" label={t('webhooks.auth.type.label')} value={formData.auth_type} onChange={handleAuthTypeChange}
              options={AUTH_TYPE_OPTIONS.map(o => ({ value: o.value, label: t(o.labelKey) }))} />
            {formData.auth_type === 'basic' && (
              <Input id="webhook-auth-user" label={t('webhooks.auth.username.label')} value={formData.auth_username}
                onChange={e => handleChange('auth_username', e.target.value)} placeholder="username" error={validationErrors.auth_username} />
            )}
            {(formData.auth_type === 'api_key' || formData.auth_type === 'custom') && (
              <Input id="webhook-auth-header" label={t('webhooks.auth.headerName.label')} value={formData.auth_header_name}
                onChange={e => handleChange('auth_header_name', e.target.value)}
                placeholder={formData.auth_type === 'custom' ? 'Authorization' : t('webhooks.auth.headerName.placeholder')}
                error={validationErrors.auth_header_name} />
            )}
            {showHeaderNameAuthorizationWarning && <Notice tone="warn">{t('webhooks.auth.apiKey.authorizationWarning')}</Notice>}
            {formData.auth_type !== 'none' && tokenField}
            {formData.auth_type === 'custom' && <Notice>{t('webhooks.auth.custom.helper')}</Notice>}

            {/* The header the request will carry, masked unless revealed */}
            {preview && (
              <div className="field full" data-testid="auth-preview">
                <div className="label-row">
                  <span>{t('webhooks.auth.preview.title')}</span>
                  {preview.revealedValue && (
                    <button type="button" className="text-link" onClick={() => setPreviewRevealed(prev => !prev)}>
                      <Icon name={previewRevealed ? 'hide' : 'eye'} />{previewRevealed ? t('webhooks.auth.preview.hide') : t('webhooks.auth.preview.reveal')}
                    </button>
                  )}
                </div>
                <div className="command-line"><code>
                  <span>{preview.headerName}</span><span className="muted">: </span>
                  <span>{previewRevealed && preview.revealedValue ? preview.revealedValue : preview.maskedValue}</span>
                </code></div>
              </div>
            )}
          </div>
        </fieldset>

        <fieldset className="field full">
          <legend className="label-row">
            <span>{t('webhooks.events')}</span>
            <button type="button" className="text-link" onClick={toggleAllEvents}>
              {formData.events.length === WEBHOOK_EVENTS.length ? t('common.deselectAll') : t('common.selectAll')}
            </button>
          </legend>
          <div className="eku-list two-columns">
            {WEBHOOK_EVENTS.map(event => (
              <label key={event} className="checkbox-line">
                <input type="checkbox" checked={formData.events.includes(event)} onChange={() => toggleEvent(event)} />
                <span>{webhookEventLabel(t, event)}<small className="mono">{event}</small></span>
              </label>
            ))}
          </div>
        </fieldset>

        <ToggleSwitch checked={formData.enabled} onChange={(val) => handleChange('enabled', val)} label={t('webhooks.enableOnCreate')} />
      </div>

      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <Btn type="submit" tone="primary" icon="check">{isEditing ? t('common.save') : t('common.create')}</Btn>
      </div>
    </form>
  )
}
