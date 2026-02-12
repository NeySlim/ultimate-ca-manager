/**
 * Settings Page - Horizontal tabs for desktop, scrollable for mobile
 * Uses DetailCard design system
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { 
  Gear, EnvelopeSimple, ShieldCheck, Database, ListBullets, FloppyDisk, 
  Envelope, Download, Trash, HardDrives, Lock, Key, Palette, Sun, Moon, Desktop, Info,
  Timer, Clock, WarningCircle, UploadSimple, Certificate, Eye, ArrowsClockwise, Rocket,
  Plus, PencilSimple, TestTube, Lightning, Globe, Shield, CheckCircle, XCircle, MagnifyingGlass,
  Bell, Copy, Power, ArrowClockwise
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  Button, Input, Select, Badge, Textarea, Card, EmptyState, ConfirmModal,
  LoadingSpinner, FileUpload, Modal, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent,
  UpdateChecker, ServiceReconnectOverlay
} from '../components'
import { SmartImportModal } from '../components/SmartImport'
import LanguageSelector from '../components/ui/LanguageSelector'
import { settingsService, systemService, casService, certificatesService } from '../services'
import { useNotification, useMobile } from '../contexts'
import { useServiceReconnect } from '../hooks'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'
import { ERRORS, SUCCESS } from '../lib/messages'
import { useTheme } from '../contexts/ThemeContext'
import { apiClient } from '../services/apiClient'

// Settings categories with colors for visual distinction
const BASE_SETTINGS_CATEGORIES = [
  { id: 'general', labelKey: 'settings.tabs.general', icon: Gear, color: 'icon-bg-blue' },
  { id: 'appearance', labelKey: 'settings.tabs.appearance', icon: Palette, color: 'icon-bg-violet' },
  { id: 'email', labelKey: 'settings.tabs.email', icon: EnvelopeSimple, color: 'icon-bg-teal' },
  { id: 'security', labelKey: 'settings.tabs.security', icon: ShieldCheck, color: 'icon-bg-amber' },
  { id: 'sso', labelKey: 'settings.tabs.sso', icon: Key, color: 'icon-bg-purple' },
  { id: 'backup', labelKey: 'settings.tabs.backup', icon: Database, color: 'icon-bg-emerald' },
  { id: 'audit', labelKey: 'settings.tabs.audit', icon: ListBullets, color: 'icon-bg-orange' },
  { id: 'database', labelKey: 'settings.tabs.database', icon: HardDrives, color: 'icon-bg-blue' },
  { id: 'https', labelKey: 'settings.tabs.https', icon: Lock, color: 'icon-bg-emerald' },
  { id: 'updates', labelKey: 'settings.tabs.updates', icon: Rocket, color: 'icon-bg-violet' },
  { id: 'webhooks', labelKey: 'settings.tabs.webhooks', icon: Bell, color: 'icon-bg-rose' },
]

// SSO Provider type icons
const SSO_PROVIDER_ICONS = {
  ldap: Database,
  oauth2: Globe,
  saml: Shield,
}

// Service Status Widget Component
function ServiceStatusWidget() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite } = usePermission()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [restarting, setRestarting] = useState(false)
  const { reconnecting, status: reconnectStatus, attempt, waitForRestart, cancel } = useServiceReconnect()

  const fetchStatus = async () => {
    try {
      const response = await systemService.getServiceStatus()
      setStatus(response.data)
    } catch {
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  const formatUptime = (seconds) => {
    if (!seconds) return '-'
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    if (days > 0) return `${days}d ${hours}h ${mins}m`
    if (hours > 0) return `${hours}h ${mins}m`
    return `${mins}m`
  }

  const handleRestart = async () => {
    const confirmed = await showConfirm(t('settings.restartConfirmMessage'), {
      title: t('settings.restartService'),
      confirmText: t('settings.restartNow'),
      variant: 'danger'
    })
    if (!confirmed) return

    setRestarting(true)
    try {
      await systemService.restartService()
      waitForRestart({ delay: 3000 })
    } catch {
      showError(t('settings.restartFailed'))
      setRestarting(false)
    }
  }

  return (
    <>
      {reconnecting && (
        <ServiceReconnectOverlay status={reconnectStatus} attempt={attempt} onCancel={cancel} />
      )}
      <DetailSection title={t('settings.serviceStatus')} icon={Power} iconClass="icon-bg-orange" className="mt-4">
      {loading ? (
        <LoadingSpinner size="sm" />
      ) : status ? (
        <div className="space-y-3">
          <DetailGrid columns={2}>
            <DetailField label={t('settings.version')} value={`v${status.version}`} />
            <DetailField label="PID" value={status.pid} />
            <DetailField label={t('settings.uptime')} value={formatUptime(status.uptime_seconds)} />
            <DetailField label={t('settings.memory')} value={`${status.memory_mb} MB`} />
            <DetailField label="Python" value={status.python_version} />
            <DetailField label={t('settings.environment')} value={status.is_docker ? 'Docker' : 'System'} />
          </DetailGrid>
          {canWrite('settings') && (
            <div className="pt-2">
              <Button variant="outline" onClick={handleRestart} disabled={restarting}>
                <ArrowClockwise size={16} className={restarting ? 'spin' : ''} />
                {restarting ? t('settings.restarting') : t('settings.restartService')}
              </Button>
            </div>
          )}
        </div>
      ) : (
        <p className="text-secondary">{t('settings.serviceStatusUnavailable')}</p>
      )}
    </DetailSection>
    </>
  )
}
function AppearanceSettings() {
  const { t } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const { forceDesktop, setForceDesktop, screenWidth, breakpoints } = useMobile()
  
  const modeOptions = [
    { id: 'system', label: t('settings.followSystem'), icon: Desktop, description: t('settings.followSystemDesc') },
    { id: 'light', label: t('settings.light'), icon: Sun, description: t('settings.lightDesc') },
    { id: 'dark', label: t('settings.dark'), icon: Moon, description: t('settings.darkDesc') },
  ]
  
  return (
    <DetailContent>
      <DetailHeader
        icon={Palette}
        title={t('settings.tabs.appearance')}
        subtitle={t('settings.appearanceSubtitle')}
      />
      
      <DetailSection title={t('settings.colorTheme')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.colorThemeDesc')}
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {themes.map(theme => (
            <button
              key={theme.id}
              onClick={() => setThemeFamily(theme.id)}
              className={`
                p-4 rounded-lg border-2 transition-all text-left
                ${themeFamily === theme.id 
                  ? 'border-accent-primary bg-accent-primary/10' 
                  : 'border-border hover:border-text-tertiary bg-bg-tertiary/50'
                }
              `}
            >
              <div className="flex items-center gap-3 mb-2">
                <div 
                  className="w-5 h-5 rounded-full shadow-inner"
                  style={{ background: theme.accent }}
                />
                <span className="font-medium text-sm text-text-primary">{theme.name}</span>
              </div>
              <div className="flex gap-1">
                {/* Preview colors - show accent and distinct bg colors */}
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.accent }} />
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.dark['bg-tertiary'] }} />
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.light['bg-tertiary'] }} />
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.light['accent-primary'] || theme.accent }} />
              </div>
            </button>
          ))}
        </div>
      </DetailSection>
      
      <DetailSection title={t('settings.appearanceMode')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.appearanceModeDesc')}
        </p>
        <div className="space-y-2">
          {modeOptions.map(opt => {
            const Icon = opt.icon
            return (
              <button
                key={opt.id}
                onClick={() => setMode(opt.id)}
                className={`
                  w-full p-4 rounded-lg border-2 transition-all text-left flex items-center gap-4
                  ${mode === opt.id 
                    ? 'border-accent-primary bg-accent-primary/10' 
                    : 'border-border hover:border-text-tertiary bg-bg-tertiary/50'
                  }
                `}
              >
                <div className={`
                  w-10 h-10 rounded-lg flex items-center justify-center
                  ${mode === opt.id ? 'bg-accent-primary text-white' : 'bg-bg-secondary text-text-secondary'}
                `}>
                  <Icon size={20} weight={mode === opt.id ? 'fill' : 'regular'} />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-text-primary">{opt.label}</div>
                  <div className="text-xs text-text-tertiary">{opt.description}</div>
                </div>
                {mode === opt.id && (
                  <div className="w-5 h-5 rounded-full bg-accent-primary flex items-center justify-center">
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </DetailSection>
      
      <DetailSection title={t('settings.layoutMode')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.layoutModeDesc')}
        </p>
        <button
          onClick={() => setForceDesktop(!forceDesktop)}
          className={`
            w-full p-4 rounded-lg border-2 transition-all text-left flex items-center gap-4
            ${forceDesktop 
              ? 'border-accent-primary bg-accent-primary/10' 
              : 'border-border hover:border-text-tertiary bg-bg-tertiary/50'
            }
          `}
        >
          <div className={`
            w-10 h-10 rounded-lg flex items-center justify-center
            ${forceDesktop ? 'bg-accent-primary text-white' : 'bg-bg-secondary text-text-secondary'}
          `}>
            <Desktop size={20} weight={forceDesktop ? 'fill' : 'regular'} />
          </div>
          <div className="flex-1">
            <div className="font-medium text-text-primary">{t('settings.forceDesktopLayout')}</div>
            <div className="text-xs text-text-tertiary">
              {forceDesktop 
                ? t('settings.desktopLayoutEnabled') 
                : t('settings.mobileLayoutActivates', { breakpoint: breakpoints.lg, current: screenWidth })
              }
            </div>
          </div>
          <div className={`
            w-12 h-6 rounded-full transition-colors relative
            ${forceDesktop ? 'bg-accent-primary' : 'bg-bg-secondary border border-border'}
          `}>
            <div className={`
              absolute top-1 w-4 h-4 rounded-full transition-transform
              ${forceDesktop 
                ? 'bg-white translate-x-6' 
                : 'bg-text-tertiary translate-x-1'
              }
            `} />
          </div>
        </button>
        {forceDesktop && (
          <p className="text-xs text-text-tertiary mt-2 flex items-center gap-1">
            <Info size={12} />
            {t('settings.settingSavedInBrowser')}
          </p>
        )}
      </DetailSection>
      
      <DetailSection title={t('settings.language')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.languageDesc')}
        </p>
        <LanguageSelector />
      </DetailSection>
      
      <DetailSection title={t('settings.preview')}>
        <div className="p-4 rounded-lg bg-bg-tertiary border border-border">
          <p className="text-sm text-text-secondary mb-2">{t('settings.currentSettings')}:</p>
          <p className="text-text-primary">
            <span className="font-medium">{themes.find(th => th.id === themeFamily)?.name}</span>
            {' · '}
            <span className="text-text-secondary">
              {mode === 'system' ? t('settings.followingSystemPreference') : mode === 'dark' ? t('settings.darkMode') : t('settings.lightMode')}
            </span>
            {forceDesktop && (
              <>
                {' · '}
                <span className="text-accent-primary">{t('settings.desktopForced')}</span>
              </>
            )}
          </p>
        </div>
      </DetailSection>
    </DetailContent>
  )
}

// SSO Provider Form Component
function SsoProviderForm({ provider, onSave, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    name: provider?.name || '',
    display_name: provider?.display_name || '',
    provider_type: provider?.provider_type || 'ldap',
    enabled: provider?.enabled ?? false,
    default_role: provider?.default_role || 'viewer',
    auto_create_users: provider?.auto_create_users ?? true,
    auto_update_users: provider?.auto_update_users ?? true,
    // LDAP
    ldap_server: provider?.ldap_server || '',
    ldap_port: provider?.ldap_port || 389,
    ldap_use_ssl: provider?.ldap_use_ssl ?? false,
    ldap_bind_dn: provider?.ldap_bind_dn || '',
    ldap_bind_password: '',
    ldap_base_dn: provider?.ldap_base_dn || '',
    ldap_user_filter: provider?.ldap_user_filter || '(uid={username})',
    // OAuth2
    oauth2_client_id: provider?.oauth2_client_id || '',
    oauth2_client_secret: '',
    oauth2_auth_url: provider?.oauth2_auth_url || '',
    oauth2_token_url: provider?.oauth2_token_url || '',
    oauth2_userinfo_url: provider?.oauth2_userinfo_url || '',
    oauth2_scopes: provider?.oauth2_scopes?.join(' ') || 'openid profile email',
    // SAML
    saml_entity_id: provider?.saml_entity_id || '',
    saml_sso_url: provider?.saml_sso_url || '',
    saml_slo_url: provider?.saml_slo_url || '',
    saml_certificate: provider?.saml_certificate || '',
  })

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = { ...formData }
    if (data.provider_type === 'oauth2') {
      data.oauth2_scopes = data.oauth2_scopes.split(/\s+/).filter(Boolean)
    }
    onSave(data)
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-6">
      {/* General Settings */}
      <div className="space-y-4">
        <h4 className="text-sm font-medium text-text-primary border-b border-border pb-2">{t('common.general')}</h4>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label={t('common.providerName')}
            value={formData.name}
            onChange={e => handleChange('name', e.target.value)}
            required
            placeholder={t('sso.providerNamePlaceholder')}
          />
          <Input
            label={t('sso.displayName')}
            value={formData.display_name}
            onChange={e => handleChange('display_name', e.target.value)}
            placeholder={t('sso.displayNamePlaceholder')}
          />
        </div>
        {!provider && (
          <Select
            label={t('common.providerType')}
            value={formData.provider_type}
            onChange={value => handleChange('provider_type', value)}
            options={[
              { value: 'ldap', label: t('sso.ldap') },
              { value: 'oauth2', label: t('sso.oauth2') },
              { value: 'saml', label: t('sso.saml') },
            ]}
          />
        )}
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={formData.enabled}
            onChange={e => handleChange('enabled', e.target.checked)}
            className="rounded border-border bg-bg-tertiary"
          />
          <span className="text-sm text-text-primary">{t('common.enableProvider')}</span>
        </label>
      </div>

      {/* Connection Settings */}
      <div className="space-y-4">
        <h4 className="text-sm font-medium text-text-primary border-b border-border pb-2">{t('sso.tabs.connection')}</h4>
        
        {formData.provider_type === 'ldap' && (
          <>
            <div className="grid grid-cols-3 gap-4">
              <Input
                label={t('sso.ldapServer')}
                value={formData.ldap_server}
                onChange={e => handleChange('ldap_server', e.target.value)}
                placeholder="ldap.example.com"
                className="col-span-2"
              />
              <Input
                label={t('common.portLabel')}
                type="number"
                value={formData.ldap_port}
                onChange={e => handleChange('ldap_port', parseInt(e.target.value))}
              />
            </div>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.ldap_use_ssl}
                onChange={e => handleChange('ldap_use_ssl', e.target.checked)}
                className="rounded border-border bg-bg-tertiary"
              />
              <span className="text-sm text-text-primary">{t('sso.ldapUseSsl')}</span>
            </label>
            <Input
              label={t('sso.bindDn')}
              value={formData.ldap_bind_dn}
              onChange={e => handleChange('ldap_bind_dn', e.target.value)}
              placeholder={t('sso.bindDnPlaceholder')}
            />
            <Input
              label={t('sso.bindPassword')}
              type="password"
              value={formData.ldap_bind_password}
              onChange={e => handleChange('ldap_bind_password', e.target.value)}
              hasExistingValue={!!provider?.ldap_bind_password}
            />
            <Input
              label={t('sso.baseDn')}
              value={formData.ldap_base_dn}
              onChange={e => handleChange('ldap_base_dn', e.target.value)}
              placeholder={t('sso.baseDnPlaceholder')}
            />
            <Input
              label={t('sso.userFilter')}
              value={formData.ldap_user_filter}
              onChange={e => handleChange('ldap_user_filter', e.target.value)}
              placeholder={t('sso.userFilterPlaceholder')}
            />
          </>
        )}

        {formData.provider_type === 'oauth2' && (
          <>
            <Input
              label={t('common.clientId')}
              value={formData.oauth2_client_id}
              onChange={e => handleChange('oauth2_client_id', e.target.value)}
            />
            <Input
              label={t('common.clientSecret')}
              type="password"
              value={formData.oauth2_client_secret}
              onChange={e => handleChange('oauth2_client_secret', e.target.value)}
              hasExistingValue={!!provider?.oauth2_client_secret}
            />
            <Input
              label={t('sso.authUrl')}
              value={formData.oauth2_auth_url}
              onChange={e => handleChange('oauth2_auth_url', e.target.value)}
              placeholder={t('sso.authUrlPlaceholder')}
            />
            <Input
              label={t('sso.tokenUrl')}
              value={formData.oauth2_token_url}
              onChange={e => handleChange('oauth2_token_url', e.target.value)}
              placeholder={t('sso.tokenUrlPlaceholder')}
            />
            <Input
              label={t('sso.scopes')}
              value={formData.oauth2_scopes}
              onChange={e => handleChange('oauth2_scopes', e.target.value)}
              placeholder={t('sso.scopesPlaceholder')}
            />
          </>
        )}

        {formData.provider_type === 'saml' && (
          <>
            <Input
              label={t('sso.entityId')}
              value={formData.saml_entity_id}
              onChange={e => handleChange('saml_entity_id', e.target.value)}
              placeholder="https://idp.example.com/saml/metadata"
            />
            <Input
              label={t('sso.ssoURL')}
              value={formData.saml_sso_url}
              onChange={e => handleChange('saml_sso_url', e.target.value)}
              placeholder="https://idp.example.com/saml/sso"
            />
            <Input
              label={t('sso.sloURL')}
              value={formData.saml_slo_url}
              onChange={e => handleChange('saml_slo_url', e.target.value)}
              placeholder="https://idp.example.com/saml/slo"
            />
            <Textarea
              label={t('sso.certificate')}
              value={formData.saml_certificate}
              onChange={e => handleChange('saml_certificate', e.target.value)}
              rows={6}
              placeholder="-----BEGIN CERTIFICATE-----..."
              className="font-mono text-xs"
            />
          </>
        )}
      </div>

      {/* Provisioning Settings */}
      <div className="space-y-4">
        <h4 className="text-sm font-medium text-text-primary border-b border-border pb-2">{t('sso.tabs.provisioning')}</h4>
        <Select
          label={t('sso.defaultRole')}
          value={formData.default_role}
          onChange={value => handleChange('default_role', value)}
          options={[
            { value: 'admin', label: t('common.admin') },
            { value: 'operator', label: t('common.operator') },
            { value: 'viewer', label: t('common.viewer') },
          ]}
        />
        <div className="space-y-2">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.auto_create_users}
              onChange={e => handleChange('auto_create_users', e.target.checked)}
              className="rounded border-border bg-bg-tertiary"
            />
            <span className="text-sm text-text-primary">{t('sso.autoCreateUsers')}</span>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.auto_update_users}
              onChange={e => handleChange('auto_update_users', e.target.checked)}
              className="rounded border-border bg-bg-tertiary"
            />
            <span className="text-sm text-text-primary">{t('sso.autoUpdateUsers')}</span>
          </label>
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          {provider ? t('common.save') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}

// Webhook Form Component
const WEBHOOK_EVENTS = [
  'certificate.issued',
  'certificate.revoked',
  'certificate.renewed',
  'certificate.expiring',
  'ca.created',
  'ca.updated',
  'csr.submitted',
  'csr.approved',
  'csr.rejected',
]

const WEBHOOK_EVENT_LABELS = {
  'certificate.issued': 'Issued',
  'certificate.revoked': 'Revoked',
  'certificate.renewed': 'Renewed',
  'certificate.expiring': 'Expiring',
  'ca.created': 'CA Created',
  'ca.updated': 'CA Updated',
  'csr.submitted': 'CSR Submitted',
  'csr.approved': 'CSR Approved',
  'csr.rejected': 'CSR Rejected',
}

function WebhookForm({ webhook, onSave, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    name: webhook?.name || '',
    url: webhook?.url || '',
    events: webhook?.events || [],
    ca_filter: webhook?.ca_filter || '',
    enabled: webhook?.enabled ?? true,
  })

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
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

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(formData)
  }

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

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-text-primary">{t('webhooks.events')}</label>
          <button type="button" onClick={toggleAllEvents} className="text-xs text-accent-primary hover:underline">
            {formData.events.length === WEBHOOK_EVENTS.length ? t('common.deselectAll') : t('common.selectAll')}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {WEBHOOK_EVENTS.map(event => (
            <label key={event} className="flex items-center gap-2 p-2 rounded-lg bg-bg-tertiary/50 border border-border/30 cursor-pointer hover:border-accent-primary/50 transition-colors">
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

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={formData.enabled}
          onChange={e => handleChange('enabled', e.target.checked)}
          className="rounded border-border bg-bg-tertiary"
        />
        <span className="text-sm text-text-primary">{t('webhooks.enableOnCreate')}</span>
      </label>

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>{t('common.cancel')}</Button>
        <Button type="submit">
          {webhook ? t('common.save') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}

export default function SettingsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm, showPrompt } = useNotification()
  const { canWrite, hasPermission } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState({})
  const [backups, setBackups] = useState([])
  const [dbStats, setDbStats] = useState(null)
  const [httpsInfo, setHttpsInfo] = useState(null)
  const [certificates, setCertificates] = useState([])
  const [selectedHttpsCert, setSelectedHttpsCert] = useState('')
  const [cas, setCas] = useState([])
  
  // Selected category - read from URL param or default to 'general'
  const [selectedCategory, setSelectedCategory] = useState(
    searchParams.get('tab') || 'general'
  )
  
  // Update URL when category changes
  const handleCategoryChange = (categoryId) => {
    setSelectedCategory(categoryId)
    if (categoryId === 'general') {
      searchParams.delete('tab')
    } else {
      searchParams.set('tab', categoryId)
    }
    setSearchParams(searchParams, { replace: true })
  }
  
  // Backup modal states
  const [showBackupModal, setShowBackupModal] = useState(false)
  const [showRestoreModal, setShowRestoreModal] = useState(false)
  const [backupPassword, setBackupPassword] = useState('')
  const [restorePassword, setRestorePassword] = useState('')
  const [restoreFile, setRestoreFile] = useState(null)
  const [backupLoading, setBackupLoading] = useState(false)
  
  // HTTPS import modal
  const [showHttpsImportModal, setShowHttpsImportModal] = useState(false)

  // SSO states
  const [ssoProviders, setSsoProviders] = useState([])
  const [ssoLoading, setSsoLoading] = useState(false)
  const [showSsoModal, setShowSsoModal] = useState(false)
  const [editingSsoProvider, setEditingSsoProvider] = useState(null)
  const [ssoTesting, setSsoTesting] = useState(false)
  const [ssoConfirmDelete, setSsoConfirmDelete] = useState(null)

  // Webhook states
  const [webhooks, setWebhooks] = useState([])
  const [webhooksLoading, setWebhooksLoading] = useState(false)
  const [showWebhookModal, setShowWebhookModal] = useState(false)
  const [editingWebhook, setEditingWebhook] = useState(null)
  const [webhookTesting, setWebhookTesting] = useState(null)
  const [webhookConfirmDelete, setWebhookConfirmDelete] = useState(null)

  // All settings categories (SSO now integrated directly)
  const SETTINGS_CATEGORIES = BASE_SETTINGS_CATEGORIES

  useEffect(() => {
    loadSettings()
    loadBackups()
    loadHttpsInfo()
    loadCAs()
    loadCertificates()
    loadDbStats()
    loadSsoProviders()
    loadWebhooks()
  }, [])

  const loadSettings = async () => {
    setLoading(true)
    try {
      const [generalRes, emailRes] = await Promise.all([
        settingsService.getAll(),
        settingsService.getEmailSettings().catch(() => ({ data: {} }))
      ])
      const generalSettings = generalRes.data || generalRes || {}
      const emailSettings = emailRes.data || {}
      
      // Merge email settings with mapped field names
      setSettings({
        ...generalSettings,
        smtp_host: emailSettings.smtp_host,
        smtp_port: emailSettings.smtp_port,
        smtp_username: emailSettings.smtp_username,
        smtp_password: emailSettings.smtp_password,
        smtp_use_tls: emailSettings.smtp_tls,
        smtp_from_email: emailSettings.from_email,
        smtp_from_name: emailSettings.from_name,
      })
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.SETTINGS)
    } finally {
      setLoading(false)
    }
  }

  const loadCAs = async () => {
    try {
      const data = await casService.getAll()
      setCas(data.data || [])
    } catch (error) {
      console.error('Failed to load CAs:', error)
    }
  }

  const loadBackups = async () => {
    try {
      const data = await systemService.listBackups()
      setBackups(data.data || [])
    } catch (error) {
      console.error('Failed to load backups:', error)
    }
  }

  const loadHttpsInfo = async () => {
    try {
      const data = await systemService.getHttpsCertInfo()
      setHttpsInfo(data.data || {})
    } catch (error) {
      console.error('Failed to load HTTPS cert info:', error)
    }
  }

  const loadDbStats = async () => {
    try {
      const data = await systemService.getDatabaseStats()
      const stats = data.data || {}
      setDbStats({
        certificates: stats.counts?.certificates || 0,
        cas: stats.counts?.cas || 0,
        size: stats.size_mb ? `${stats.size_mb} MB` : '-',
        last_optimized: stats.last_vacuum || 'Never'
      })
    } catch (error) {
      console.error('Failed to load database stats:', error)
    }
  }

  // SSO Functions
  const loadSsoProviders = async () => {
    setSsoLoading(true)
    try {
      const response = await apiClient.get('/sso/providers')
      setSsoProviders(response.data || [])
    } catch (error) {
      console.error('Failed to load SSO providers:', error)
    } finally {
      setSsoLoading(false)
    }
  }

  const handleSsoCreate = () => {
    setEditingSsoProvider(null)
    setShowSsoModal(true)
  }

  const handleSsoEdit = (provider) => {
    setEditingSsoProvider(provider)
    setShowSsoModal(true)
  }

  const handleSsoSave = async (formData) => {
    try {
      if (editingSsoProvider) {
        await apiClient.put(`/sso/providers/${editingSsoProvider.id}`, formData)
        showSuccess(t('sso.updateSuccess'))
      } else {
        await apiClient.post('/sso/providers', formData)
        showSuccess(t('sso.createSuccess'))
      }
      setShowSsoModal(false)
      loadSsoProviders()
    } catch (error) {
      showError(error.message || t('sso.saveFailed'))
    }
  }

  const handleSsoDelete = async () => {
    if (!ssoConfirmDelete) return
    try {
      await apiClient.delete(`/sso/providers/${ssoConfirmDelete.id}`)
      showSuccess(t('sso.deleteSuccess'))
      loadSsoProviders()
    } catch (error) {
      showError(t('sso.deleteFailed'))
    } finally {
      setSsoConfirmDelete(null)
    }
  }

  const handleSsoToggle = async (provider) => {
    try {
      await apiClient.post(`/sso/providers/${provider.id}/toggle`)
      showSuccess(t('sso.toggleSuccess', { action: provider.enabled ? t('common.disabled').toLowerCase() : t('common.enabled').toLowerCase() }))
      loadSsoProviders()
    } catch (error) {
      showError(t('sso.toggleFailed'))
    }
  }

  const handleSsoTest = async (provider) => {
    setSsoTesting(true)
    try {
      const response = await apiClient.post(`/sso/providers/${provider.id}/test`)
      if (response.data?.status === 'success') {
        showSuccess(response.data.message || t('sso.testSuccess'))
      } else {
        showError(response.message || t('common.dnsProviderTestFailed'))
      }
    } catch (error) {
      showError(error.message || t('common.dnsProviderTestFailed'))
    } finally {
      setSsoTesting(false)
    }
  }

  // Webhook handlers
  const loadWebhooks = async () => {
    setWebhooksLoading(true)
    try {
      const response = await apiClient.get('/webhooks')
      setWebhooks(response.data || [])
    } catch (error) {
      console.error('Failed to load webhooks:', error)
    } finally {
      setWebhooksLoading(false)
    }
  }

  const handleWebhookCreate = () => {
    setEditingWebhook(null)
    setShowWebhookModal(true)
  }

  const handleWebhookEdit = (webhook) => {
    setEditingWebhook(webhook)
    setShowWebhookModal(true)
  }

  const handleWebhookSave = async (formData) => {
    try {
      if (editingWebhook) {
        await apiClient.put(`/webhooks/${editingWebhook.id}`, formData)
        showSuccess(t('webhooks.updateSuccess'))
      } else {
        await apiClient.post('/webhooks', formData)
        showSuccess(t('webhooks.createSuccess'))
      }
      setShowWebhookModal(false)
      loadWebhooks()
    } catch (error) {
      showError(error.message || t('webhooks.saveFailed'))
    }
  }

  const handleWebhookDelete = async () => {
    if (!webhookConfirmDelete) return
    try {
      await apiClient.delete(`/webhooks/${webhookConfirmDelete.id}`)
      showSuccess(t('webhooks.deleteSuccess'))
      loadWebhooks()
    } catch (error) {
      showError(t('webhooks.deleteFailed'))
    } finally {
      setWebhookConfirmDelete(null)
    }
  }

  const handleWebhookToggle = async (webhook) => {
    try {
      await apiClient.post(`/webhooks/${webhook.id}/toggle`)
      showSuccess(t('webhooks.toggleSuccess', { action: webhook.enabled ? t('common.disabled').toLowerCase() : t('common.enabled').toLowerCase() }))
      loadWebhooks()
    } catch (error) {
      showError(t('webhooks.toggleFailed'))
    }
  }

  const handleWebhookTest = async (webhook) => {
    setWebhookTesting(webhook.id)
    try {
      await apiClient.post(`/webhooks/${webhook.id}/test`)
      showSuccess(t('webhooks.testSuccess'))
    } catch (error) {
      showError(error.message || t('webhooks.testFailed'))
    } finally {
      setWebhookTesting(null)
    }
  }

  const loadCertificates = async () => {
    try {
      const data = await certificatesService.getAll({ status: 'valid' })
      const validCerts = (data.data || []).filter(cert => 
        cert.has_private_key && 
        cert.status === 'valid' &&
        new Date(cert.valid_to) > new Date()
      )
      setCertificates(validCerts)
    } catch (error) {
      console.error('Failed to load certificates:', error)
    }
  }

  const handleSave = async (section) => {
    setSaving(true)
    try {
      if (section === 'email') {
        // Email settings go to a different endpoint with mapped field names
        await settingsService.updateEmailSettings({
          smtp_host: settings.smtp_host,
          smtp_port: settings.smtp_port,
          smtp_username: settings.smtp_username,
          smtp_password: settings.smtp_password,
          smtp_tls: settings.smtp_use_tls,
          from_email: settings.smtp_from_email,
          from_name: settings.smtp_from_name,
          enabled: true
        })
      } else {
        await settingsService.updateBulk(settings)
      }
      showSuccess(SUCCESS.UPDATE.SETTINGS)
      await loadSettings()
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.SETTINGS)
    } finally {
      setSaving(false)
    }
  }

  const handleTestEmail = async () => {
    const testEmail = settings.smtp_from_email || settings.admin_email
    if (!testEmail) {
      showError(t('common.emailRequired'))
      return
    }
    try {
      await settingsService.testEmail(testEmail)
      showSuccess(SUCCESS.EMAIL.TEST_SENT)
    } catch (error) {
      showError(error.message || ERRORS.EMAIL.TEST_FAILED)
    }
  }

  const handleBackup = async () => {
    if (!backupPassword || backupPassword.length < 12) {
      showError(t('settings.passwordMinLength'))
      return
    }
    
    setBackupLoading(true)
    try {
      const response = await systemService.backup(backupPassword)
      if (response.data) {
        const blob = await systemService.downloadBackup(response.data.filename)
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = response.data.filename
        a.click()
        URL.revokeObjectURL(url)
        showSuccess(SUCCESS.BACKUP.CREATED)
        setShowBackupModal(false)
        setBackupPassword('')
        loadBackups()
      }
    } catch (error) {
      showError(error.message || ERRORS.BACKUP.CREATE_FAILED)
    } finally {
      setBackupLoading(false)
    }
  }

  const handleDownloadBackup = async (filename) => {
    try {
      const blob = await systemService.downloadBackup(filename)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(SUCCESS.BACKUP.DOWNLOADED)
    } catch (error) {
      showError(error.message || ERRORS.BACKUP.DOWNLOAD_FAILED)
    }
  }

  const handleDeleteBackup = async (filename) => {
    const confirmed = await showConfirm(t('settings.confirmDeleteBackup', { filename }), {
      title: t('settings.deleteBackup'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await systemService.deleteBackup(filename)
      showSuccess(SUCCESS.BACKUP.DELETED)
      loadBackups()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.BACKUP)
    }
  }

  const handleRestoreBackup = async () => {
    if (!restoreFile) {
      showError(t('settings.selectBackupFile'))
      return
    }
    if (!restorePassword || restorePassword.length < 12) {
      showError(t('settings.passwordMinLength'))
      return
    }
    
    setBackupLoading(true)
    try {
      const result = await systemService.restore(restoreFile, restorePassword)
      showSuccess(t('settings.backupRestored', { users: result.data?.users || 0, cas: result.data?.cas || 0, certs: result.data?.certificates || 0 }))
      setShowRestoreModal(false)
      setRestorePassword('')
      setRestoreFile(null)
      setTimeout(() => window.location.reload(), 2000)
    } catch (error) {
      showError(error.message || ERRORS.BACKUP.RESTORE_FAILED)
    } finally {
      setBackupLoading(false)
    }
  }

  const handleOptimizeDb = async () => {
    try {
      await systemService.optimizeDatabase()
      showSuccess(SUCCESS.DATABASE.OPTIMIZED)
    } catch (error) {
      showError(error.message || ERRORS.DATABASE.OPTIMIZE_FAILED)
    }
  }

  const handleIntegrityCheck = async () => {
    try {
      const result = await systemService.integrityCheck()
      if (result.passed) {
        showSuccess(SUCCESS.DATABASE.INTEGRITY_PASSED)
      } else {
        showError(t('settings.integrityErrors', { count: result.errors }))
      }
    } catch (error) {
      showError(error.message || ERRORS.DATABASE.INTEGRITY_FAILED)
    }
  }

  const handleExportDb = async () => {
    try {
      const blob = await systemService.exportDatabase()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ucm-database-${new Date().toISOString().split('T')[0]}.sql`
      a.click()
      showSuccess(SUCCESS.EXPORT.DATABASE)
    } catch (error) {
      showError(error.message || ERRORS.DATABASE.EXPORT_FAILED)
    }
  }

  const handleResetDb = async () => {
    const confirmed1 = await showConfirm(t('settings.resetDbWarning'), {
      title: t('settings.resetDatabase'),
      confirmText: t('common.next'),
      variant: 'danger'
    })
    if (!confirmed1) return

    const confirmation = await showPrompt(t('settings.typeYesToConfirm'), {
      title: t('settings.finalConfirmation'),
      placeholder: 'YES'
    })
    if (confirmation !== 'YES') {
      showError(t('settings.resetDbCancelled'))
      return
    }

    try {
      await systemService.resetDatabase()
      showSuccess(SUCCESS.DATABASE.RESET)
      setTimeout(() => window.location.reload(), 2000)
    } catch (error) {
      showError(error.message || ERRORS.DATABASE.RESET_FAILED)
    }
  }

  const handleApplyUcmCert = async () => {
    if (!selectedHttpsCert) {
      showError(t('settings.selectCertificate'))
      return
    }

    const confirmed = await showConfirm(t('settings.applyHttpsCertConfirm'), {
      title: t('settings.applyCertificate'),
      confirmText: t('settings.applyAndRestart')
    })
    if (!confirmed) return
    
    try {
      await systemService.applyHttpsCert({
        cert_id: selectedHttpsCert
      })
      showSuccess(SUCCESS.HTTPS.APPLIED)
      setTimeout(() => window.location.reload(), 3000)
    } catch (error) {
      showError(error.message || ERRORS.HTTPS.APPLY_FAILED)
    }
  }

  const handleRegenerateHttpsCert = async () => {
    const confirmed = await showConfirm(t('settings.regenerateCertConfirm'), {
      title: t('settings.regenerateCert'),
      confirmText: t('settings.regenerateAndRestart')
    })
    if (!confirmed) return
    
    try {
      await systemService.regenerateHttpsCert({
        common_name: window.location.hostname,
        validity_days: 365
      })
      showSuccess(SUCCESS.HTTPS.REGENERATED)
      setTimeout(() => window.location.reload(), 3000)
    } catch (error) {
      showError(error.message || ERRORS.HTTPS.REGENERATE_FAILED)
    }
  }

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  // Render content for each category
  const renderCategoryContent = () => {
    switch (selectedCategory) {
      case 'general':
        return (
          <DetailContent>
            <DetailHeader
              icon={Gear}
              title={t('settings.helpGeneral')}
              subtitle={t('settings.generalSubtitle')}
            />
            <DetailSection title={t('settings.subtitle')} icon={Gear} iconClass="icon-bg-blue">
              <div className="space-y-4">
                <Input
                  label={t('settings.systemName')}
                  value={settings.system_name || ''}
                  onChange={(e) => updateSetting('system_name', e.target.value)}
                  helperText={t('settings.systemNameHelper')}
                />
                <Input
                  label={t('settings.baseUrl')}
                  value={settings.base_url || ''}
                  onChange={(e) => updateSetting('base_url', e.target.value)}
                  placeholder={t('settings.baseUrlPlaceholder')}
                  helperText={t('settings.baseUrlHelper')}
                />
              </div>
            </DetailSection>
            <DetailSection title={t('settings.sessionTimezone')} icon={Clock} iconClass="icon-bg-teal">
              <div className="space-y-4">
                <Input
                  label={t('settings.sessionTimeout')}
                  type="number"
                  value={settings.session_timeout || 30}
                  onChange={(e) => updateSetting('session_timeout', parseInt(e.target.value))}
                  min="5"
                  max="1440"
                />
                <Select
                  label={t('settings.timezone')}
                  options={[
                    { value: 'UTC', label: 'UTC' },
                    { value: 'America/New_York', label: 'America/New York' },
                    { value: 'Europe/Paris', label: 'Europe/Paris' },
                    { value: 'Asia/Tokyo', label: 'Asia/Tokyo' },
                  ]}
                  value={settings.timezone || 'UTC'}
                  onChange={(val) => updateSetting('timezone', val)}
                />
                {canWrite('settings') && (
                  <div className="pt-2">
                    <Button onClick={() => handleSave('general')} disabled={saving}>
                      <FloppyDisk size={16} />
                      {t('common.saveChanges')}
                    </Button>
                  </div>
                )}
              </div>
            </DetailSection>
            <ServiceStatusWidget />
          </DetailContent>
        )

      case 'appearance':
        return <AppearanceSettings />

      case 'email':
        return (
          <DetailContent>
            <DetailHeader
              icon={EnvelopeSimple}
              title={t('settings.emailTitle')}
              subtitle={t('settings.emailSubtitle')}
            />
            <DetailSection title={t('settings.smtpHost')} icon={Envelope} iconClass="icon-bg-violet">
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
            </DetailSection>
            <DetailSection title={t('settings.authentication')} icon={Key} iconClass="icon-bg-amber">
              <div className="space-y-4">
                <Input
                  label={t('settings.smtpUsername')}
                  value={settings.smtp_username || ''}
                  onChange={(e) => updateSetting('smtp_username', e.target.value)}
                />
                <Input
                  label={t('settings.smtpPassword')}
                  type="password"
                  value={settings.smtp_password === '********' ? '' : (settings.smtp_password || '')}
                  onChange={(e) => updateSetting('smtp_password', e.target.value)}
                  hasExistingValue={settings.smtp_password === '********'}
                />
              </div>
            </DetailSection>
            <DetailSection title={t('settings.emailOptions')} icon={EnvelopeSimple} iconClass="icon-bg-blue">
              <div className="space-y-4">
                <Input
                  label={t('settings.fromEmail')}
                  type="email"
                  value={settings.smtp_from_email || ''}
                  onChange={(e) => updateSetting('smtp_from_email', e.target.value)}
                  placeholder={t('settings.fromEmailPlaceholder')}
                />
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.smtp_use_tls || false}
                    onChange={(e) => updateSetting('smtp_use_tls', e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                  <span className="text-sm text-text-primary">{t('settings.useTls')}</span>
                </label>
                {canWrite('settings') && (
                  <div className="flex gap-2 pt-2">
                    <Button variant="secondary" onClick={handleTestEmail}>
                      <Envelope size={16} />
                      {t('settings.testEmail')}
                    </Button>
                    <Button onClick={() => handleSave('email')} disabled={saving}>
                      <FloppyDisk size={16} />
                      {t('common.saveChanges')}
                    </Button>
                  </div>
                )}
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'security':
        return (
          <DetailContent>
            <DetailHeader
              icon={ShieldCheck}
              title={t('common.securitySettings')}
              subtitle={t('settings.securitySubtitle')}
            />
            <DetailSection title={t('common.twoFactorAuth')} icon={ShieldCheck} iconClass="icon-bg-emerald">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.enforce_2fa || false}
                  onChange={(e) => updateSetting('enforce_2fa', e.target.checked)}
                  className="rounded border-border bg-bg-tertiary"
                />
                <div>
                  <p className="text-sm text-text-primary font-medium">{t('settings.enforce2fa')}</p>
                  <p className="text-xs text-text-secondary">{t('settings.enforce2faDesc')}</p>
                </div>
              </label>
            </DetailSection>
            <DetailSection title={t('settings.passwordPolicy')} icon={Lock} iconClass="icon-bg-violet">
              <div className="space-y-4">
                <Input
                  label={t('settings.minPasswordLength')}
                  type="number"
                  value={settings.min_password_length || 8}
                  onChange={(e) => updateSetting('min_password_length', parseInt(e.target.value))}
                  min="6"
                  max="32"
                />
                <div className="space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.password_require_uppercase || false}
                      onChange={(e) => updateSetting('password_require_uppercase', e.target.checked)}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{t('settings.requireUppercase')}</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.password_require_numbers || false}
                      onChange={(e) => updateSetting('password_require_numbers', e.target.checked)}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{t('settings.requireNumbers')}</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.password_require_special || false}
                      onChange={(e) => updateSetting('password_require_special', e.target.checked)}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{t('settings.requireSpecial')}</span>
                  </label>
                </div>
              </div>
            </DetailSection>
            <DetailSection title={t('settings.sessionRateLimits')} icon={Timer} iconClass="icon-bg-teal">
              <DetailGrid>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label={t('settings.sessionDuration')}
                    type="number"
                    value={settings.session_duration || 24}
                    onChange={(e) => updateSetting('session_duration', parseInt(e.target.value))}
                    min="1"
                    max="720"
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input
                    label={t('settings.apiRateLimit')}
                    type="number"
                    value={settings.api_rate_limit || 60}
                    onChange={(e) => updateSetting('api_rate_limit', parseInt(e.target.value))}
                    min="10"
                    max="1000"
                  />
                </div>
              </DetailGrid>
              {hasPermission('admin:system') && (
                <div className="pt-4">
                  <Button onClick={() => handleSave('security')} disabled={saving}>
                    <FloppyDisk size={16} />
                    {t('common.saveChanges')}
                  </Button>
                </div>
              )}
            </DetailSection>
          </DetailContent>
        )

      case 'sso':
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
                <div className="w-6 h-6 border-2 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
              </div>
            ) : ssoProviders.length === 0 ? (
              <EmptyState
                icon={Key}
                title={t('sso.noProviders')}
                description={t('sso.noProvidersDescription')}
                action={{ label: t('common.addDnsProvider'), onClick: handleSsoCreate }}
              />
            ) : (
              <DetailSection title={t('sso.configuredProviders')} icon={Key} iconClass="icon-bg-purple">
                <div className="space-y-3">
                  {ssoProviders.map(provider => {
                    const ProviderIcon = SSO_PROVIDER_ICONS[provider.provider_type] || Key
                    return (
                      <div key={provider.id} className="flex items-center justify-between p-4 bg-bg-tertiary/50 border border-border/50 rounded-lg">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-accent-primary/10 flex items-center justify-center">
                            <ProviderIcon size={20} className="text-accent-primary" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-text-primary">{provider.display_name || provider.name}</span>
                              <Badge variant={provider.enabled ? 'success' : 'secondary'} size="sm">
                                {provider.enabled ? t('common.enabled') : t('common.disabled')}
                              </Badge>
                            </div>
                            <p className="text-xs text-text-secondary">{provider.provider_type?.toUpperCase()}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button size="sm" variant="secondary" onClick={() => handleSsoTest(provider)} disabled={ssoTesting}>
                            {ssoTesting ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => handleSsoToggle(provider)}>
                            <Lightning size={14} />
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => handleSsoEdit(provider)}>
                            <PencilSimple size={14} />
                          </Button>
                          <Button size="sm" variant="danger" onClick={() => setSsoConfirmDelete(provider)}>
                            <Trash size={14} />
                          </Button>
                        </div>
                      </div>
                    )
                  })}
                  {hasPermission('admin:system') && (
                    <div className="pt-2">
                      <Button onClick={handleSsoCreate}>
                        <Plus size={16} />
                        {t('common.addDnsProvider')}
                      </Button>
                    </div>
                  )}
                </div>
              </DetailSection>
            )}
          </DetailContent>
        )

      case 'backup':
        return (
          <DetailContent>
            <DetailHeader
              icon={Database}
              title={t('settings.helpBackup')}
              subtitle={t('settings.backupSubtitle')}
            />
            <DetailSection title={t('settings.automaticBackups')} icon={Database} iconClass="icon-bg-emerald">
              <div className="space-y-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.auto_backup_enabled || false}
                    onChange={(e) => updateSetting('auto_backup_enabled', e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                  <div>
                    <p className="text-sm text-text-primary font-medium">{t('settings.enableAutoBackups')}</p>
                    <p className="text-xs text-text-secondary">{t('settings.autoBackupsDesc')}</p>
                  </div>
                </label>

                {settings.auto_backup_enabled && (
                  <>
                    <Select
                      label={t('settings.backupFrequency')}
                      options={[
                        { value: 'daily', label: t('settings.daily') },
                        { value: 'weekly', label: t('settings.weekly') },
                        { value: 'monthly', label: t('settings.monthly') },
                      ]}
                      value={settings.backup_frequency || 'daily'}
                      onChange={(val) => updateSetting('backup_frequency', val)}
                    />
                    <Input
                      label={t('settings.autoBackupPassword')}
                      type="password"
                      value={settings.backup_password || ''}
                      onChange={(e) => updateSetting('backup_password', e.target.value)}
                      placeholder={t('settings.min12Characters')}
                      helperText={t('settings.autoBackupPasswordHelper')}
                      showStrength
                    />
                    <Input
                      label={t('settings.retentionPeriod')}
                      type="number"
                      value={settings.backup_retention_days || 30}
                      onChange={(e) => updateSetting('backup_retention_days', parseInt(e.target.value))}
                      min="1"
                      max="365"
                    />
                  </>
                )}

                {hasPermission('admin:system') && (
                  <div className="flex gap-2">
                    <Button onClick={() => handleSave('backup')} disabled={saving}>
                      <FloppyDisk size={16} />
                      {t('settings.saveSettings')}
                    </Button>
                    <Button variant="secondary" onClick={() => setShowBackupModal(true)}>
                      <Database size={16} />
                      {t('settings.createBackup')}
                    </Button>
                  </div>
                )}
              </div>
            </DetailSection>

            <DetailSection title={t('settings.availableBackups')} icon={Download} iconClass="icon-bg-blue">
              {backups.length === 0 ? (
                <div className="p-6 text-center">
                  <p className="text-sm text-text-secondary">{t('settings.noBackups')}</p>
                  <p className="text-xs text-text-tertiary mt-1">{t('settings.noBackupsHint')}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {backups.map((backup) => (
                    <div key={backup.filename} className="flex items-center justify-between p-3 bg-bg-tertiary/50 border border-white/5 rounded-lg">
                      <div>
                        <p className="text-sm font-medium text-text-primary">{backup.filename}</p>
                        <div className="flex gap-4 mt-1">
                          <p className="text-xs text-text-secondary">{backup.size}</p>
                          <p className="text-xs text-text-secondary">{backup.created_at}</p>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="secondary" onClick={() => handleDownloadBackup(backup.filename)}>
                          <Download size={14} />
                        </Button>
                        <Button size="sm" variant="danger" onClick={() => handleDeleteBackup(backup.filename)}>
                          <Trash size={14} />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </DetailSection>

            <DetailSection title={t('settings.restoreFromBackup')} icon={UploadSimple} iconClass="icon-bg-orange">
              <div>
                <p className="text-xs text-text-secondary mb-4">{t('settings.restoreFromBackupDesc')}</p>
                <FileUpload
                  accept=".ucmbkp,.tar.gz"
                  onFileSelect={(file) => { setRestoreFile(file); setShowRestoreModal(true) }}
                  helperText={t('settings.selectBackupFile')}
                />
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'audit':
        return (
          <DetailContent>
            <DetailHeader
              icon={ListBullets}
              title={t('settings.auditTitle')}
              subtitle={t('settings.auditSubtitle')}
            />
            <DetailSection title={t('settings.auditLogging')} icon={ListBullets} iconClass="icon-bg-orange">
              <div className="space-y-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.audit_enabled || true}
                    onChange={(e) => updateSetting('audit_enabled', e.target.checked)}
                    className="rounded border-border bg-bg-tertiary"
                  />
                  <div>
                    <p className="text-sm text-text-primary font-medium">{t('settings.enableAuditLogging')}</p>
                    <p className="text-xs text-text-secondary">{t('settings.enableAuditLoggingDesc')}</p>
                  </div>
                </label>

                <Input
                  label={t('settings.logRetention')}
                  type="number"
                  value={settings.audit_retention_days || 90}
                  onChange={(e) => updateSetting('audit_retention_days', parseInt(e.target.value))}
                  min="7"
                  max="730"
                  disabled={!settings.audit_enabled}
                />
              </div>
            </DetailSection>
            <DetailSection title={t('settings.eventsToLog')} icon={Eye} iconClass="icon-bg-blue">
              <div className="space-y-2">
                {[
                  { key: 'userLoginLogout', label: t('settings.eventUserLoginLogout') },
                  { key: 'certIssueRevoke', label: t('settings.eventCertIssueRevoke') },
                  { key: 'caCreateDelete', label: t('settings.eventCaCreateDelete') },
                  { key: 'settingsChanges', label: t('settings.eventSettingsChanges') },
                  { key: 'userManagement', label: t('common.eventUserManagement') },
                ].map(event => (
                  <label key={event.key} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={true}
                      disabled={!settings.audit_enabled}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{event.label}</span>
                  </label>
                ))}
                {hasPermission('admin:system') && (
                  <div className="pt-4">
                    <Button onClick={() => handleSave('audit')} disabled={saving}>
                      <FloppyDisk size={16} />
                      {t('common.saveChanges')}
                    </Button>
                  </div>
                )}
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'database':
        return (
          <DetailContent>
            <DetailHeader
              icon={HardDrives}
              title={t('settings.helpDatabase')}
              subtitle={t('settings.databaseSubtitle')}
            />
            <DetailSection title={t('settings.databaseStatistics')} icon={HardDrives} iconClass="icon-bg-blue">
              <DetailGrid>
                <DetailField
                  label={t('settings.totalCertificates')}
                  value={dbStats?.certificates || '-'}
                />
                <DetailField
                  label={t('common.cas')}
                  value={dbStats?.cas || '-'}
                />
                <DetailField
                  label={t('settings.databaseSize')}
                  value={dbStats?.size || '-'}
                />
                <DetailField
                  label={t('settings.lastOptimized')}
                  value={dbStats?.last_optimized || '-'}
                />
              </DetailGrid>
            </DetailSection>

            <DetailSection title={t('settings.maintenance')} icon={Gear} iconClass="icon-bg-teal">
              <div className="space-y-3">
                <div className="flex flex-wrap gap-3">
                  <Button size="sm" variant="secondary" onClick={handleOptimizeDb}>
                    <Database size={16} />
                    {t('settings.optimizeDatabase')}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={handleIntegrityCheck}>
                    <ShieldCheck size={16} />
                    {t('settings.integrityCheck')}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={handleExportDb}>
                    <Download size={16} />
                    {t('settings.exportDatabase')}
                  </Button>
                </div>
              </div>
            </DetailSection>

            <DetailSection title={t('settings.dangerZone')} icon={WarningCircle} iconClass="icon-bg-orange" className="mt-4">
              <div className="p-4 status-danger-bg status-danger-border border rounded-lg">
                <h4 className="text-sm font-semibold text-status-danger mb-2">⚠️ {t('settings.databaseReset')}</h4>
                <p className="text-xs text-text-secondary mb-3">
                  {t('settings.databaseResetDesc')}
                </p>
                <Button variant="danger" size="sm" onClick={handleResetDb}>
                  <Trash size={16} />
                  {t('settings.resetDatabase')}
                </Button>
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'https':
        return (
          <DetailContent>
            <DetailHeader
              icon={Lock}
              title={t('settings.httpsTitle')}
              subtitle={t('settings.httpsSubtitle')}
              badge={httpsInfo?.type && (
                <Badge variant={httpsInfo?.type === 'CA-Signed' ? 'success' : httpsInfo?.type === 'Self-Signed' ? 'warning' : 'secondary'}>
                  {httpsInfo?.type}
                </Badge>
              )}
            />
            <DetailSection title={t('settings.currentCertificate')} icon={Certificate} iconClass="icon-bg-blue">
              <DetailGrid>
                <DetailField
                  label={t('common.commonName')}
                  value={httpsInfo?.common_name || window.location.hostname}
                />
                <DetailField
                  label={t('common.issuer')}
                  value={httpsInfo?.issuer || '-'}
                />
                <DetailField
                  label={t('common.validFrom')}
                  value={formatDate(httpsInfo?.valid_from)}
                />
                <DetailField
                  label={t('common.validUntil')}
                  value={formatDate(httpsInfo?.valid_to)}
                />
                <DetailField
                  label={t('settings.fingerprintSha256')}
                  value={httpsInfo?.fingerprint || '-'}
                  mono
                  copyable
                  fullWidth
                />
              </DetailGrid>
            </DetailSection>

            <DetailSection title={t('settings.useUCMCert')} icon={Certificate} iconClass="icon-bg-violet">
              <div className="space-y-4">
                <p className="text-xs text-text-secondary">
                  {t('settings.useUcmCertificateDesc')}
                </p>
                <Select
                  label={t('settings.selectCertificate')}
                  value={selectedHttpsCert}
                  onChange={setSelectedHttpsCert}
                  placeholder={t('settings.chooseCertificate')}
                  options={certificates.map(cert => ({
                    value: cert.id,
                    label: `${cert.common_name || t('common.certificate')} (${t('common.expires')} ${formatDate(cert.valid_to)})`
                  }))}
                />
                {certificates.length === 0 && (
                  <p className="text-xs text-text-secondary">
                    {t('settings.noValidCertificates')}
                  </p>
                )}
                <Button 
                  variant="secondary" 
                  size="sm"
                  onClick={handleApplyUcmCert}
                  disabled={!selectedHttpsCert}
                >
                  <ShieldCheck size={16} />
                  {t('settings.applySelectedCertificate')}
                </Button>
              </div>
            </DetailSection>

            <DetailSection title={t('settings.regenerateCert')} icon={ArrowsClockwise} iconClass="icon-bg-emerald">
              <div className="space-y-3">
                <p className="text-xs text-text-secondary">
                  {t('settings.regenerateCertificateDesc')}
                </p>
                <Button variant="secondary" size="sm" onClick={handleRegenerateHttpsCert}>
                  <Key size={16} />
                  {t('settings.regenerateSelfSigned')}
                </Button>
              </div>
            </DetailSection>

            <DetailSection title={t('settings.applyCustomCert')} icon={Lock} iconClass="icon-bg-amber">
              <div className="space-y-3">
                <p className="text-xs text-text-secondary">
                  {t('settings.applyCustomCertificateDesc')}
                </p>
                <Button
                  variant="secondary"
                  onClick={() => setShowHttpsImportModal(true)}
                >
                  <UploadSimple size={16} className="mr-2" />
                  {t('common.importCertificate')}
                </Button>
              </div>
            </DetailSection>
          </DetailContent>
        )

      case 'updates':
        return (
          <DetailContent>
            <DetailHeader
              icon={Rocket}
              title={t('settings.updatesTitle')}
              subtitle={t('settings.updatesSubtitle')}
            />
            <UpdateChecker />
          </DetailContent>
        )

      case 'webhooks':
        return (
          <DetailContent>
            <DetailHeader
              icon={Bell}
              title={t('webhooks.title')}
              subtitle={t('webhooks.subtitle')}
            />

            <HelpCard variant="info" title={t('webhooks.helpTitle')} className="mb-4">
              {t('webhooks.helpDescription')}
            </HelpCard>

            {webhooksLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="w-6 h-6 border-2 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
              </div>
            ) : webhooks.length === 0 ? (
              <EmptyState
                icon={Bell}
                title={t('webhooks.noWebhooks')}
                description={t('webhooks.noWebhooksDescription')}
                action={{ label: t('webhooks.addWebhook'), onClick: handleWebhookCreate }}
              />
            ) : (
              <DetailSection title={t('webhooks.configuredWebhooks')} icon={Bell} iconClass="icon-bg-rose">
                <div className="space-y-3">
                  {webhooks.map(webhook => (
                    <div key={webhook.id} className="flex items-center justify-between p-4 bg-bg-tertiary/50 border border-border/50 rounded-lg">
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="w-10 h-10 rounded-lg bg-accent-primary/10 flex items-center justify-center flex-shrink-0">
                          <Bell size={20} className="text-accent-primary" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-text-primary truncate">{webhook.name}</span>
                            <Badge variant={webhook.enabled ? 'success' : 'secondary'} size="sm">
                              {webhook.enabled ? t('common.enabled') : t('common.disabled')}
                            </Badge>
                          </div>
                          <p className="text-xs text-text-secondary truncate">{webhook.url}</p>
                          <div className="flex items-center gap-1 mt-1">
                            {(webhook.events || []).slice(0, 3).map(ev => (
                              <Badge key={ev} variant="outline" size="sm">{WEBHOOK_EVENT_LABELS[ev] || ev}</Badge>
                            ))}
                            {(webhook.events || []).length > 3 && (
                              <Badge variant="outline" size="sm">+{webhook.events.length - 3}</Badge>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                        <Button size="sm" variant="secondary" onClick={() => handleWebhookTest(webhook)} disabled={webhookTesting === webhook.id}>
                          {webhookTesting === webhook.id ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => handleWebhookToggle(webhook)}>
                          <Lightning size={14} />
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => handleWebhookEdit(webhook)}>
                          <PencilSimple size={14} />
                        </Button>
                        <Button size="sm" variant="danger" onClick={() => setWebhookConfirmDelete(webhook)}>
                          <Trash size={14} />
                        </Button>
                      </div>
                    </div>
                  ))}
                  {hasPermission('admin:system') && (
                    <div className="pt-2">
                      <Button onClick={handleWebhookCreate}>
                        <Plus size={16} />
                        {t('webhooks.addWebhook')}
                      </Button>
                    </div>
                  )}
                </div>
              </DetailSection>
            )}
          </DetailContent>
        )

      default:
        return null
    }
  }

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      <HelpCard variant="info" title={t('settings.helpGeneral')}>
        Configure your UCM instance name, base URL, session timeout, and timezone.
        These settings affect all users and system behavior.
      </HelpCard>
      
      <HelpCard variant="tip" title={t('settings.helpEmail')}>
        Configure SMTP settings to enable email notifications for certificate
        expiration alerts and system events. Test your configuration before saving.
      </HelpCard>

      <HelpCard variant="warning" title={t('common.securitySettings')}>
        Security settings like 2FA enforcement and password policies affect all users.
        Changes take effect immediately - users may need to update their credentials.
      </HelpCard>

      <HelpCard variant="info" title={t('settings.helpBackup')}>
        Create encrypted backups of all data including certificates, CAs, users, 
        and settings. Store backup passwords securely - they cannot be recovered.
      </HelpCard>

      <HelpCard variant="tip" title={t('settings.helpDatabase')}>
        Optimize database performance, check integrity, or export data.
        The danger zone allows complete database reset - use with extreme caution.
      </HelpCard>

      <HelpCard variant="info" title={t('settings.https')}>
        Manage the SSL/TLS certificate used by UCM. You can use a certificate
        from your PKI or generate a self-signed certificate for testing.
      </HelpCard>
    </div>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message={t('settings.loadingSettings')} />
      </div>
    )
  }

  // Transform categories to tabs format with translations
  const tabs = SETTINGS_CATEGORIES.map(cat => ({
    id: cat.id,
    label: t(cat.labelKey),
    icon: cat.icon,
    color: cat.color,
    badge: undefined  // All features now community
  }))

  return (
    <>
      <ResponsiveLayout
        title={t('common.settings')}
        subtitle={t('settings.subtitle')}
        icon={Gear}
        tabs={tabs}
        activeTab={selectedCategory}
        onTabChange={handleCategoryChange}
        tabLayout="sidebar"
        tabGroups={[
          { labelKey: 'settings.groups.system', tabs: ['general', 'updates', 'database', 'https', 'backup'], color: 'icon-bg-blue' },
          { labelKey: 'settings.groups.security', tabs: ['security', 'sso'], color: 'icon-bg-amber' },
          { labelKey: 'settings.groups.notifications', tabs: ['email', 'webhooks'], color: 'icon-bg-teal' },
          { labelKey: 'settings.groups.interface', tabs: ['appearance', 'audit'], color: 'icon-bg-violet' },
        ]}
        helpPageKey="settings"
      >
        <div className="max-w-4xl mx-auto p-4 md:p-6">
          {renderCategoryContent()}
        </div>
      </ResponsiveLayout>

      {/* Backup Password Modal */}
      <Modal
        open={showBackupModal}
        onClose={() => { setShowBackupModal(false); setBackupPassword('') }}
        title={t('settings.encryptedBackup')}
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            {t('settings.createBackupDesc')}
          </p>
          <Input
            label={t('settings.encryptionPassword')}
            type="password"
            value={backupPassword}
            onChange={(e) => setBackupPassword(e.target.value)}
            placeholder={t('settings.min12Characters')}
            helperText={t('settings.encryptionPasswordHelper')}
            autoFocus
            showStrength
          />
          <div className="flex gap-3 justify-end pt-4">
            <Button variant="secondary" onClick={() => { setShowBackupModal(false); setBackupPassword('') }}>
              {t('common.cancel')}
            </Button>
            <Button 
              onClick={handleBackup} 
              disabled={backupLoading || !backupPassword || backupPassword.length < 12}
            >
              {backupLoading ? t('settings.creating') : t('settings.createAndDownload')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Restore Password Modal */}
      <Modal
        open={showRestoreModal}
        onClose={() => { setShowRestoreModal(false); setRestorePassword(''); setRestoreFile(null) }}
        title={t('settings.restoreFromBackup')}
      >
        <div className="space-y-4">
          <div className="p-3 status-warning-bg status-warning-border border rounded-lg">
            <p className="text-sm status-warning-text font-medium">⚠️ {t('common.warning')}</p>
            <p className="text-xs status-warning-text opacity-80">
              {t('settings.restoreWarning')}
            </p>
          </div>
          {restoreFile && (
            <p className="text-sm text-text-primary">
              {t('settings.file')}: <strong>{restoreFile.name}</strong>
            </p>
          )}
          <Input
            label={t('settings.backupPassword')}
            type="password"
            value={restorePassword}
            onChange={(e) => setRestorePassword(e.target.value)}
            placeholder={t('settings.enterBackupPassword')}
            autoFocus
          />
          <div className="flex gap-3 justify-end pt-4">
            <Button variant="secondary" onClick={() => { setShowRestoreModal(false); setRestorePassword(''); setRestoreFile(null) }}>
              {t('common.cancel')}
            </Button>
            <Button 
              variant="danger"
              onClick={handleRestoreBackup} 
              disabled={backupLoading || !restorePassword || restorePassword.length < 12}
            >
              {backupLoading ? t('settings.restoring') : t('settings.restoreBackup')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* SSO Provider Modal */}
      <Modal
        open={showSsoModal}
        onClose={() => { setShowSsoModal(false); setEditingSsoProvider(null) }}
        title={editingSsoProvider ? t('sso.editProvider') : t('common.addDnsProvider')}
        size="lg"
      >
        <SsoProviderForm
          provider={editingSsoProvider}
          onSave={handleSsoSave}
          onCancel={() => { setShowSsoModal(false); setEditingSsoProvider(null) }}
        />
      </Modal>

      {/* SSO Delete Confirmation */}
      <ConfirmModal
        open={!!ssoConfirmDelete}
        onClose={() => setSsoConfirmDelete(null)}
        onConfirm={handleSsoDelete}
        title={t('common.confirmDelete')}
        message={t('sso.deleteConfirm', { name: ssoConfirmDelete?.name })}
        confirmText={t('common.delete')}
        variant="danger"
      />

      {/* Webhook Modal */}
      <Modal
        open={showWebhookModal}
        onClose={() => { setShowWebhookModal(false); setEditingWebhook(null) }}
        title={editingWebhook ? t('webhooks.editWebhook') : t('webhooks.addWebhook')}
        size="lg"
      >
        <WebhookForm
          webhook={editingWebhook}
          onSave={handleWebhookSave}
          onCancel={() => { setShowWebhookModal(false); setEditingWebhook(null) }}
        />
      </Modal>

      {/* Webhook Delete Confirmation */}
      <ConfirmModal
        open={!!webhookConfirmDelete}
        onClose={() => setWebhookConfirmDelete(null)}
        onConfirm={handleWebhookDelete}
        title={t('common.confirmDelete')}
        message={t('webhooks.deleteConfirm', { name: webhookConfirmDelete?.name })}
        confirmText={t('common.delete')}
        variant="danger"
      />
      
      {/* Smart Import Modal for HTTPS certificate */}
      <SmartImportModal
        isOpen={showHttpsImportModal}
        onClose={() => setShowHttpsImportModal(false)}
        onImportComplete={async (imported) => {
          setShowHttpsImportModal(false)
          // If a certificate was imported with private key, offer to apply it
          if (imported?.id && imported?.has_private_key) {
            const apply = await showConfirm(t('settings.applyImportedCertConfirm'), {
              title: t('settings.applyCertificate'),
              confirmText: t('settings.applyAndRestart')
            })
            if (apply) {
              try {
                await systemService.applyHttpsCert({ cert_id: imported.id })
                showSuccess(SUCCESS.HTTPS.APPLIED)
                setTimeout(() => window.location.reload(), 3000)
              } catch (error) {
                showError(error.message || ERRORS.HTTPS.APPLY_FAILED)
              }
            }
          } else {
            // Refresh cert list
            loadCertificates()
            showSuccess(t('common.importSuccess'))
          }
        }}
        defaultType="certificate"
      />
    </>
  )
}
