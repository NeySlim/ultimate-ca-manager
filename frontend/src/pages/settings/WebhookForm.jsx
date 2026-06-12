import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Eye, EyeSlash, CheckCircle, WarningCircle, X } from '@phosphor-icons/react'
import { Button, Input, Select } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'

const WEBHOOK_EVENTS = [
  'certificate.issued',
  'certificate.revoked',
  'certificate.renewed',
  'certificate.expiring',
  'certificate.expired',
  'certificate.imported',
  'certificate.deleted',
  'ca.created',
  'ca.updated',
  'ca.deleted',
  'csr.submitted',
  'csr.approved',
  'csr.rejected',
  'template.created',
  'template.updated',
]

export const WEBHOOK_EVENT_LABELS = {
  'certificate.issued': 'Issued',
  'certificate.revoked': 'Revoked',
  'certificate.renewed': 'Renewed',
  'certificate.expiring': 'Expiring',
  'certificate.expired': 'Expired',
  'certificate.imported': 'Imported',
  'certificate.deleted': 'Deleted',
  'ca.created': 'CA Created',
  'ca.updated': 'CA Updated',
  'ca.deleted': 'CA Deleted',
  'csr.submitted': 'CSR Submitted',
  'csr.approved': 'CSR Approved',
  'csr.rejected': 'CSR Rejected',
  'template.created': 'Template Created',
  'template.updated': 'Template Updated',
}

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

  // Client-side validation mirroring backend rules
  const validate = () => {
    const errors = {}
    const { auth_type, auth_token, auth_username, auth_header_name, auth_token_set, auth_token_cleared } = formData

    if (auth_type !== 'none') {
      const tokenPresent = auth_token_set && !auth_token_cleared
      const tokenProvided = auth_token.length > 0
      // If user explicitly cleared the token, allow submit (sends null to backend)
      const needsToken = !auth_token_cleared && !tokenPresent && !tokenProvided

      if (needsToken) {
        errors.auth_token = t('webhooks.auth.errors.tokenRequired')
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
    const { auth_token_set: _ignored, auth_token_cleared, auth_token, auth_username, auth_header_name, ...rest } = formData

    const payload = { ...rest }

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
      const maskedB64 = displayToken
        ? btoa(`${user}:${maskToken(displayToken)}`)
        : '•••••••••'
      const revealedB64 = displayToken ? btoa(`${user}:${displayToken}`) : null
      return {
        headerName: 'Authorization',
        maskedValue: `Basic ${maskedB64}`,
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
    formData.auth_token.length === 0

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={t('common.name')}
        value={formData.name}
        onChange={e => handleChange('name', e.target.value)}
        required
        placeholder={t('webhooks.namePlaceholder')}
      />
      <Input
        label="URL"
        value={formData.url}
        onChange={e => handleChange('url', e.target.value)}
        required
        placeholder="https://example.com/webhook"
      />
      <Input
        label={t('webhooks.caFilter')}
        value={formData.ca_filter}
        onChange={e => handleChange('ca_filter', e.target.value)}
        placeholder={t('webhooks.caFilterPlaceholder')}
      />

      {/* Authentication section */}
      <div className="space-y-3 rounded-lg border border-border p-3 bg-tertiary-50">
        <p className="text-sm font-medium text-text-primary">{t('webhooks.auth.title')}</p>

        <Select
          label={t('webhooks.auth.type.label')}
          value={formData.auth_type}
          onChange={handleAuthTypeChange}
          options={AUTH_TYPE_OPTIONS.map(o => ({ value: o.value, label: t(o.labelKey) }))}
        />

        {/* Bearer token */}
        {formData.auth_type === 'bearer' && (
          <div className="space-y-2">
            {showTokenSetBadge ? (
              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-text-secondary">
                  <span className="flex items-center gap-1">
                    {t('webhooks.auth.token.label')}
                    <span className="inline-flex items-center gap-1 px-1.5 text-[10px] font-medium bg-status-success-op20 text-status-success rounded leading-[16px]">
                      <CheckCircle size={10} weight="fill" />
                      {t('common.set')}
                    </span>
                  </span>
                </label>
                <p className="text-xs text-text-tertiary italic">{t('webhooks.auth.token.set')}</p>
                <button
                  type="button"
                  onClick={handleClearToken}
                  className="flex items-center gap-1 text-xs text-accent-danger hover:underline"
                >
                  <X size={12} />{t('webhooks.auth.token.clear')}
                </button>
              </div>
            ) : (
              <Input
                label={t('webhooks.auth.token.label')}
                type="password"
                value={formData.auth_token}
                onChange={e => handleChange('auth_token', e.target.value)}
                placeholder={t('webhooks.auth.token.placeholder')}
                error={validationErrors.auth_token}
                helperText={showTokenByteCount ? `${tokenBytes} / ${TOKEN_MAX_BYTES} bytes` : undefined}
              />
            )}
          </div>
        )}

        {/* Basic auth */}
        {formData.auth_type === 'basic' && (
          <div className="space-y-2">
            <Input
              label={t('webhooks.auth.username.label')}
              value={formData.auth_username}
              onChange={e => handleChange('auth_username', e.target.value)}
              placeholder="username"
              error={validationErrors.auth_username}
            />
            {showTokenSetBadge ? (
              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-text-secondary">
                  <span className="flex items-center gap-1">
                    {t('webhooks.auth.token.label')}
                    <span className="inline-flex items-center gap-1 px-1.5 text-[10px] font-medium bg-status-success-op20 text-status-success rounded leading-[16px]">
                      <CheckCircle size={10} weight="fill" />
                      {t('common.set')}
                    </span>
                  </span>
                </label>
                <p className="text-xs text-text-tertiary italic">{t('webhooks.auth.token.set')}</p>
                <button
                  type="button"
                  onClick={handleClearToken}
                  className="flex items-center gap-1 text-xs text-accent-danger hover:underline"
                >
                  <X size={12} />{t('webhooks.auth.token.clear')}
                </button>
              </div>
            ) : (
              <Input
                label={t('webhooks.auth.token.label')}
                type="password"
                value={formData.auth_token}
                onChange={e => handleChange('auth_token', e.target.value)}
                placeholder={t('webhooks.auth.token.placeholder')}
                error={validationErrors.auth_token}
                helperText={showTokenByteCount ? `${tokenBytes} / ${TOKEN_MAX_BYTES} bytes` : undefined}
              />
            )}
          </div>
        )}

        {/* API Key */}
        {formData.auth_type === 'api_key' && (
          <div className="space-y-2">
            <Input
              label={t('webhooks.auth.headerName.label')}
              value={formData.auth_header_name}
              onChange={e => handleChange('auth_header_name', e.target.value)}
              placeholder={t('webhooks.auth.headerName.placeholder')}
              error={validationErrors.auth_header_name}
            />
            {showHeaderNameAuthorizationWarning && (
              <div className="flex items-start gap-2 text-xs text-accent-warning p-2 rounded-md bg-status-warning-op10 border border-status-warning-op30">
                <WarningCircle size={14} className="flex-shrink-0 mt-0.5" />
                <span>{t('webhooks.auth.apiKey.authorizationWarning')}</span>
              </div>
            )}
            {showTokenSetBadge ? (
              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-text-secondary">
                  <span className="flex items-center gap-1">
                    {t('webhooks.auth.token.label')}
                    <span className="inline-flex items-center gap-1 px-1.5 text-[10px] font-medium bg-status-success-op20 text-status-success rounded leading-[16px]">
                      <CheckCircle size={10} weight="fill" />
                      {t('common.set')}
                    </span>
                  </span>
                </label>
                <p className="text-xs text-text-tertiary italic">{t('webhooks.auth.token.set')}</p>
                <button
                  type="button"
                  onClick={handleClearToken}
                  className="flex items-center gap-1 text-xs text-accent-danger hover:underline"
                >
                  <X size={12} />{t('webhooks.auth.token.clear')}
                </button>
              </div>
            ) : (
              <Input
                label={t('webhooks.auth.token.label')}
                type="password"
                value={formData.auth_token}
                onChange={e => handleChange('auth_token', e.target.value)}
                placeholder={t('webhooks.auth.token.placeholder')}
                error={validationErrors.auth_token}
                helperText={showTokenByteCount ? `${tokenBytes} / ${TOKEN_MAX_BYTES} bytes` : undefined}
              />
            )}
          </div>
        )}

        {/* Custom header */}
        {formData.auth_type === 'custom' && (
          <div className="space-y-2">
            <Input
              label={t('webhooks.auth.headerName.label')}
              value={formData.auth_header_name}
              onChange={e => handleChange('auth_header_name', e.target.value)}
              placeholder="Authorization"
              error={validationErrors.auth_header_name}
            />
            {showTokenSetBadge ? (
              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-text-secondary">
                  <span className="flex items-center gap-1">
                    {t('webhooks.auth.token.label')}
                    <span className="inline-flex items-center gap-1 px-1.5 text-[10px] font-medium bg-status-success-op20 text-status-success rounded leading-[16px]">
                      <CheckCircle size={10} weight="fill" />
                      {t('common.set')}
                    </span>
                  </span>
                </label>
                <p className="text-xs text-text-tertiary italic">{t('webhooks.auth.token.set')}</p>
                <button
                  type="button"
                  onClick={handleClearToken}
                  className="flex items-center gap-1 text-xs text-accent-danger hover:underline"
                >
                  <X size={12} />{t('webhooks.auth.token.clear')}
                </button>
              </div>
            ) : (
              <Input
                label={t('webhooks.auth.token.label')}
                type="password"
                value={formData.auth_token}
                onChange={e => handleChange('auth_token', e.target.value)}
                placeholder={t('webhooks.auth.token.placeholder')}
                error={validationErrors.auth_token}
                helperText={showTokenByteCount ? `${tokenBytes} / ${TOKEN_MAX_BYTES} bytes` : undefined}
              />
            )}
            <p className="text-xs text-text-tertiary">{t('webhooks.auth.custom.helper')}</p>
          </div>
        )}

        {/* Preview panel */}
        {preview && (
          <div className="rounded-md border border-border bg-bg-tertiary p-3 space-y-2" data-testid="auth-preview">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-text-secondary">{t('webhooks.auth.preview.title')}</span>
              {preview.revealedValue && (
                <button
                  type="button"
                  onClick={() => setPreviewRevealed(prev => !prev)}
                  className="flex items-center gap-1 text-xs text-accent-primary hover:underline"
                >
                  {previewRevealed
                    ? <><EyeSlash size={12} />{t('webhooks.auth.preview.hide')}</>
                    : <><Eye size={12} />{t('webhooks.auth.preview.reveal')}</>
                  }
                </button>
              )}
            </div>
            <code className="block text-xs font-mono text-text-primary bg-tertiary-50 rounded px-2 py-1.5 break-all">
              <span className="text-accent-secondary">{preview.headerName}</span>
              <span className="text-text-tertiary">: </span>
              <span>{previewRevealed && preview.revealedValue ? preview.revealedValue : preview.maskedValue}</span>
            </code>
          </div>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-text-primary">{t('webhooks.events')}</label>
          <button type="button" onClick={toggleAllEvents} className="text-xs text-accent-primary hover:underline">
            {formData.events.length === WEBHOOK_EVENTS.length ? t('common.deselectAll') : t('common.selectAll')}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {WEBHOOK_EVENTS.map(event => (
            <label key={event} className="flex items-center gap-2 p-2 rounded-lg bg-tertiary-50 border border-border-op30 cursor-pointer hover:border-accent-primary-op50 transition-colors">
              <input
                type="checkbox"
                checked={formData.events.includes(event)}
                onChange={() => toggleEvent(event)}
                className="rounded border-border bg-bg-tertiary"
              />
              <span className="text-xs text-text-primary">{WEBHOOK_EVENT_LABELS[event] || event}</span>
            </label>
          ))}
        </div>
      </div>

      <ToggleSwitch
        checked={formData.enabled}
        onChange={(val) => handleChange('enabled', val)}
        label={t('webhooks.enableOnCreate')}
      />

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>{t('common.cancel')}</Button>
        <Button type="submit">
          {isEditing ? t('common.save') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}
