/**
 * Settings Page - Horizontal tabs for desktop, scrollable for mobile
 * Uses DetailCard design system
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { 
  Gear, EnvelopeSimple, ShieldCheck, Database, ListBullets, FloppyDisk, 
  Envelope, Download, Trash, HardDrives, Lock, Key, Palette, Sun, Moon, Desktop, Info,
  Timer, Clock, WarningCircle, UploadSimple, Certificate, Eye, ArrowsClockwise, Rocket,
  Plus, PencilSimple, TestTube, Lightning, Globe, Shield, CheckCircle, XCircle, MagnifyingGlass,
  Bell, Copy, Power, ArrowClockwise, LockKey, Warning, User, GithubLogo,
  Plugs, UsersThree, UserPlus, TreeStructure, CaretDown, Play,
  WindowsLogo
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  Button, Input, Select, Badge, Textarea, Card, EmptyState, ConfirmModal,
  LoadingSpinner, FileUpload, Modal, HelpCard, Logo, ExperimentalBadge,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent,
  CompactSection,
  UpdateChecker, ServiceReconnectOverlay
} from '../components'
import { SmartImportModal } from '../components/SmartImport'
import CertificatePickerModal from '../components/CertificatePickerModal'
import CertificateInput from '../components/CertificateInput'
import LanguageSelector from '../components/ui/LanguageSelector'
import { settingsService, systemService, casService, ssoService, mtlsService, mscaService } from '../services'
import { useNotification, useMobile } from '../contexts'
import { useServiceReconnect } from '../hooks'
import { usePermission } from '../hooks'
import { formatDate , downloadBlob} from '../lib/utils'
import { useTheme } from '../contexts/ThemeContext'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'
import TagsInput from '../components/ui/TagsInput'
import EmailTemplateWindow from '../components/EmailTemplateWindow'
import DatabaseBackendSection from './settings/DatabaseBackendSection'
import ServiceStatusWidget from './settings/ServiceStatusWidget'
import AboutSection from './settings/AboutSection'
import AppearanceSettings from './settings/AppearanceSettings'
import CopyableUrl from './settings/CopyableUrl'
import MappingEditor from './settings/MappingEditor'
import SsoProviderForm from './settings/SsoProviderForm'
import WebhookForm from './settings/WebhookForm'
import MscaConnectionForm from './settings/MscaConnectionForm'
import GeneralSection from './settings/GeneralSection'
import EmailSection from './settings/EmailSection'
import SecuritySection from './settings/SecuritySection'
import SsoSection from './settings/SsoSection'
import BackupSection from './settings/BackupSection'
import AuditSection from './settings/AuditSection'
import DatabaseSection from './settings/DatabaseSection'
import HttpsSection from './settings/HttpsSection'
import UpdatesSection from './settings/UpdatesSection'
import WebhooksSection from './settings/WebhooksSection'
import CTSection from './settings/CTSection'
import MicrosoftCASection from './settings/MicrosoftCASection'
import { setAppTimezone } from '../stores/timezoneStore'
import { setDateFormat, setShowTime } from '../stores/dateFormatStore'

// Settings categories with colors for visual distinction
const BASE_SETTINGS_CATEGORIES = [
  { id: 'general', labelKey: 'settings.tabs.general', icon: Gear, color: 'icon-bg-blue' },
  { id: 'appearance', labelKey: 'settings.tabs.appearance', icon: Palette, color: 'icon-bg-violet' },
  { id: 'email', labelKey: 'settings.tabs.email', icon: EnvelopeSimple, color: 'icon-bg-teal' },
  { id: 'security', labelKey: 'settings.tabs.security', icon: ShieldCheck, color: 'icon-bg-amber' },
  { id: 'sso', labelKey: 'settings.tabs.sso', icon: Key, color: 'icon-bg-purple' },
  { id: 'backup', labelKey: 'settings.tabs.backup', icon: Database, color: 'icon-bg-emerald' },
  { id: 'audit', labelKey: 'settings.tabs.audit', icon: ListBullets, color: 'icon-bg-orange' },
  { id: 'database', labelKey: 'settings.tabs.database', icon: HardDrives, color: 'icon-bg-teal' },
  { id: 'https', labelKey: 'settings.tabs.https', icon: Lock, color: 'icon-bg-emerald' },
  { id: 'updates', labelKey: 'settings.tabs.updates', icon: Rocket, color: 'icon-bg-violet' },
  { id: 'webhooks', labelKey: 'settings.tabs.webhooks', icon: Bell, color: 'icon-bg-rose' },
  { id: 'ct', labelKey: 'settings.tabs.ct', icon: Eye, color: 'icon-bg-cyan' },
  { id: 'microsoftCA', labelKey: 'settings.tabs.microsoftCA', icon: WindowsLogo, color: 'icon-bg-indigo' },
  { id: 'about', labelKey: 'settings.tabs.about', icon: Info, color: 'icon-bg-sky' },
]

// SSO Provider type icons
const SSO_PROVIDER_ICONS = {
  ldap: Database,
  oauth2: Globe,
  saml: Shield,
}

export default function SettingsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm, showPrompt, showWarning } = useNotification()
  const { canWrite, hasPermission } = usePermission()
  const { isMobile } = useMobile()
  const [searchParams, setSearchParams] = useSearchParams()
  const { reconnecting, status: reconnectStatus, attempt, countdown, waitForRestart, cancel } = useServiceReconnect()
  
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState({})
  const [emailTestResult, setEmailTestResult] = useState(null) // { success, message }
  const [emailTesting, setEmailTesting] = useState(false)
  const [oauthDirty, setOauthDirty] = useState(false)
  const [oauthPresets, setOauthPresets] = useState({})
  const [showTemplateEditor, setShowTemplateEditor] = useState(false)
  const [backups, setBackups] = useState([])
  const [dbStats, setDbStats] = useState(null)
  const [httpsInfo, setHttpsInfo] = useState(null)
  const [selectedHttpsCert, setSelectedHttpsCert] = useState(null)
  const [showCertPicker, setShowCertPicker] = useState(false)
  const [cas, setCas] = useState([])
  const [isDocker, setIsDocker] = useState(false)  
  // Expiry alert settings
  const [expiryAlerts, setExpiryAlerts] = useState({
    enabled: true, alert_days: [30, 14, 7, 1], include_revoked: false, recipients: []
  })
  
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
  const [editingSsoType, setEditingSsoType] = useState(null) // for creating new: 'ldap' | 'oauth2' | 'saml'
  const [ssoTesting, setSsoTesting] = useState(false)
  const [ssoConfirmDelete, setSsoConfirmDelete] = useState(null)

  // Webhook states
  const [webhooks, setWebhooks] = useState([])
  const [webhooksLoading, setWebhooksLoading] = useState(false)
  const [showWebhookModal, setShowWebhookModal] = useState(false)
  const [editingWebhook, setEditingWebhook] = useState(null)
  const [webhookTesting, setWebhookTesting] = useState(null)
  const [webhookConfirmDelete, setWebhookConfirmDelete] = useState(null)

  // Microsoft CA states
  const [mscaConnections, setMscaConnections] = useState([])
  const [mscaLoading, setMscaLoading] = useState(false)
  const [showMscaModal, setShowMscaModal] = useState(false)
  const [editingMsca, setEditingMsca] = useState(null)
  const [mscaTesting, setMscaTesting] = useState(false)
  const [mscaConfirmDelete, setMscaConfirmDelete] = useState(null)

  // Encryption states
  const [encryptionStatus, setEncryptionStatus] = useState(null)
  const [showEnableEncryptionModal, setShowEnableEncryptionModal] = useState(false)
  const [showDisableEncryptionModal, setShowDisableEncryptionModal] = useState(false)
  const [encryptionLoading, setEncryptionLoading] = useState(false)
  const [encryptionConfirmText, setEncryptionConfirmText] = useState('')
  const [encryptionChecks, setEncryptionChecks] = useState({ backup: false, keyFile: false, lostKeys: false })

  // Anomaly detection state
  const [anomalies, setAnomalies] = useState([])
  const [anomaliesLoading, setAnomaliesLoading] = useState(false)

  // Syslog state
  const [syslogConfig, setSyslogConfig] = useState({ enabled: false, host: '', port: 514, protocol: 'udp', tls: false, categories: ['certificate', 'ca', 'csr', 'user', 'acme', 'scep', 'system'] })
  const [syslogTesting, setSyslogTesting] = useState(false)
  const [syslogSaving, setSyslogSaving] = useState(false)

  // mTLS state
  const [mtlsSettings, setMtlsSettings] = useState({ enabled: false, required: false, trusted_ca_id: '', trusted_ca: null })
  const [mtlsLoading, setMtlsLoading] = useState(false)
  const [mtlsSaving, setMtlsSaving] = useState(false)

  // Certificate Transparency state
  const [ctSettings, setCtSettings] = useState({ enabled: false, auto_submit: false, log_urls: [] })
  const [ctLoading, setCtLoading] = useState(false)
  const [ctSaving, setCtSaving] = useState(false)
  const [ctNewLogUrl, setCtNewLogUrl] = useState('')

  // All settings categories (SSO now integrated directly)
  const SETTINGS_CATEGORIES = BASE_SETTINGS_CATEGORIES

  useEffect(() => {
    loadSettings()
    loadBackups()
    loadHttpsInfo()
    loadCAs()
    loadDbStats()
    loadSsoProviders()
    loadWebhooks()
    loadMscaConnections()
    loadEncryptionStatus()
    loadAnomalies()
    loadExpiryAlerts()
    loadSyslogConfig()
    loadMtlsSettings()
    loadCtSettings()
    systemService.getServiceStatus().then(r => setIsDocker(r.data?.is_docker || false)).catch(() => {})
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
        smtp_auth: emailSettings.smtp_auth !== false,
        smtp_content_type: emailSettings.smtp_content_type || 'html',
        smtp_auth_method: emailSettings.smtp_auth_method || 'password',
        smtp_oauth_provider: emailSettings.smtp_oauth_provider || 'google',
        smtp_oauth_tenant_id: emailSettings.smtp_oauth_tenant_id || '',
        smtp_oauth_client_id: emailSettings.smtp_oauth_client_id || '',
        smtp_oauth_client_secret: emailSettings.has_oauth_client_secret ? '********' : '',
        has_oauth_client_secret: emailSettings.has_oauth_client_secret,
        has_oauth_refresh_token: emailSettings.has_oauth_refresh_token,
        smtp_oauth_authorize_url: emailSettings.smtp_oauth_authorize_url || '',
        smtp_oauth_token_url: emailSettings.smtp_oauth_token_url || '',
        smtp_oauth_scope: emailSettings.smtp_oauth_scope || '',
        smtp_oauth_redirect_uri: emailSettings.smtp_oauth_redirect_uri || '',
      })
      // Load OAuth provider presets in parallel (best-effort, non-blocking)
      settingsService.getSmtpOAuthProviders()
        .then(res => setOauthPresets(res?.data?.providers || res?.providers || {}))
        .catch(() => { /* presets optional, frontend has fallbacks */ })
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.settings'))
    } finally {
      setLoading(false)
    }
  }

  const loadExpiryAlerts = async () => {
    try {
      const res = await settingsService.getExpiryAlerts()
      setExpiryAlerts(res.data || res)
    } catch (e) {}
  }

  const saveExpiryAlerts = async () => {
    setSaving(true)
    try {
      await settingsService.updateExpiryAlerts(expiryAlerts)
      showSuccess(t('common.saved'))
    } catch (e) {
      showError(e.message || t('common.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const triggerExpiryCheck = async () => {
    try {
      const res = await settingsService.checkExpiryAlerts()
      const data = res.data || res
      showSuccess(t('settings.expiryCheckResult', { count: data.alerts_sent || 0 }))
    } catch (e) {
      showError(e.message || t('common.error'))
    }
  }

  const loadCAs = async () => {
    try {
      const data = await casService.getAll()
      setCas(data.data || [])
    } catch (error) {
    }
  }

  const loadBackups = async () => {
    try {
      const data = await systemService.listBackups()
      setBackups(data.data || [])
    } catch (error) {
    }
  }

  const loadHttpsInfo = async () => {
    try {
      const data = await systemService.getHttpsCertInfo()
      setHttpsInfo(data.data || {})
    } catch (error) {
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
        last_optimized: stats.last_vacuum || null
      })
    } catch (error) {
    }
  }

  // SSO Functions
  const loadSsoProviders = async () => {
    setSsoLoading(true)
    try {
      const response = await ssoService.getProviders()
      setSsoProviders(response.data || [])
    } catch (error) {
    } finally {
      setSsoLoading(false)
    }
  }

  const handleSsoCreate = (providerType) => {
    setEditingSsoProvider(null)
    setEditingSsoType(providerType)
    setShowSsoModal(true)
  }

  const handleSsoEdit = (provider) => {
    setEditingSsoProvider(provider)
    setEditingSsoType(null)
    setShowSsoModal(true)
  }

  const handleSsoSave = async (formData) => {
    try {
      if (editingSsoProvider) {
        await ssoService.updateProvider(editingSsoProvider.id, formData)
        showSuccess(t('sso.updateSuccess'))
      } else {
        await ssoService.createProvider(formData)
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
      await ssoService.deleteProvider(ssoConfirmDelete.id)
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
      await ssoService.toggleProvider(provider.id)
      showSuccess(t('sso.toggleSuccess', { action: provider.enabled ? t('common.disabled').toLowerCase() : t('common.enabled').toLowerCase() }))
      loadSsoProviders()
    } catch (error) {
      showError(t('sso.toggleFailed'))
    }
  }

  const handleSsoTest = async (provider) => {
    setSsoTesting(true)
    try {
      const response = await ssoService.testProvider(provider.id)
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

  // Microsoft CA handlers
  const loadMscaConnections = async () => {
    setMscaLoading(true)
    try {
      const response = await mscaService.getAll()
      setMscaConnections(response.data || [])
    } catch (error) {
    } finally {
      setMscaLoading(false)
    }
  }

  const handleMscaCreate = () => {
    setEditingMsca(null)
    setShowMscaModal(true)
  }

  const handleMscaEdit = (conn) => {
    setEditingMsca(conn)
    setShowMscaModal(true)
  }

  const handleMscaSave = async (formData) => {
    try {
      if (editingMsca) {
        await mscaService.update(editingMsca.id, formData)
        showSuccess(t('messages.success.update.settings'))
      } else {
        await mscaService.create(formData)
        showSuccess(t('messages.success.create.settings'))
      }
      setShowMscaModal(false)
      setEditingMsca(null)
      loadMscaConnections()
    } catch (error) {
      showError(error.message)
    }
  }

  const handleMscaDelete = async () => {
    if (!mscaConfirmDelete) return
    try {
      await mscaService.delete(mscaConfirmDelete.id)
      showSuccess(t('messages.success.delete.settings'))
      setMscaConfirmDelete(null)
      loadMscaConnections()
    } catch (error) {
      showError(error.message)
    }
  }

  const handleMscaToggle = async (conn) => {
    try {
      await mscaService.update(conn.id, { enabled: !conn.enabled })
      loadMscaConnections()
    } catch (error) {
      showError(error.message)
    }
  }

  const handleMscaTest = async (conn) => {
    setMscaTesting(true)
    try {
      const response = await mscaService.test(conn.id)
      if (response.data?.success) {
        if (response.data.warning) {
          showWarning(t(`msca.warnings.${response.data.warning}`))
        } else {
          const tplCount = response.data.templates?.length || 0
          showSuccess(t('msca.testSuccessWithTemplates', { count: tplCount }))
        }
        loadMscaConnections()
      } else {
        showError(response.data?.error || t('msca.testFailed'))
      }
    } catch (error) {
      showError(error.message || t('msca.testFailed'))
    } finally {
      setMscaTesting(false)
    }
  }

  // Webhook handlers
  const loadWebhooks = async () => {
    setWebhooksLoading(true)
    try {
      const response = await settingsService.getWebhooks()
      setWebhooks(response.data || [])
    } catch (error) {
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
        await settingsService.updateWebhook(editingWebhook.id, formData)
        showSuccess(t('webhooks.updateSuccess'))
      } else {
        await settingsService.createWebhook(formData)
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
      await settingsService.deleteWebhook(webhookConfirmDelete.id)
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
      await settingsService.toggleWebhook(webhook.id)
      showSuccess(t('webhooks.toggleSuccess', { action: webhook.enabled ? t('common.disabled').toLowerCase() : t('common.enabled').toLowerCase() }))
      loadWebhooks()
    } catch (error) {
      showError(t('webhooks.toggleFailed'))
    }
  }

  const handleWebhookTest = async (webhook) => {
    setWebhookTesting(webhook.id)
    try {
      await settingsService.testWebhook(webhook.id)
      showSuccess(t('webhooks.testSuccess'))
    } catch (error) {
      showError(error.message || t('webhooks.testFailed'))
    } finally {
      setWebhookTesting(null)
    }
  }


  // Encryption management
  const loadEncryptionStatus = async () => {
    try {
      const response = await settingsService.getEncryptionStatus()
      setEncryptionStatus(response.data)
    } catch (error) {
    }
  }

  const handleEnableEncryption = async () => {
    setEncryptionLoading(true)
    try {
      await settingsService.enableEncryption()
      showSuccess(t('settings.encryptionEnabled'))
      setShowEnableEncryptionModal(false)
      setEncryptionConfirmText('')
      setEncryptionChecks({ backup: false, keyFile: false, lostKeys: false })
      await loadEncryptionStatus()
    } catch (error) {
      showError(error.message || t('settings.encryptionEnableFailed'))
    } finally {
      setEncryptionLoading(false)
    }
  }

  const handleDisableEncryption = async () => {
    setEncryptionLoading(true)
    try {
      await settingsService.disableEncryption()
      showSuccess(t('settings.encryptionDisabled'))
      setShowDisableEncryptionModal(false)
      await loadEncryptionStatus()
    } catch (error) {
      showError(error.message || t('settings.encryptionDisableFailed'))
    } finally {
      setEncryptionLoading(false)
    }
  }

  // Anomaly detection
  const loadAnomalies = async () => {
    setAnomaliesLoading(true)
    try {
      const response = await settingsService.getSecurityAnomalies()
      setAnomalies(response.data?.anomalies || response.anomalies || [])
    } catch (error) {
    } finally {
      setAnomaliesLoading(false)
    }
  }

  // Syslog config
  const loadSyslogConfig = async () => {
    try {
      const response = await settingsService.getSyslogConfig()
      setSyslogConfig(response.data || response)
    } catch (error) {
    }
  }

  const handleSaveSyslog = async () => {
    setSyslogSaving(true)
    try {
      await settingsService.updateSyslogConfig(syslogConfig)
      showSuccess(t('settings.syslogSaved'))
    } catch (error) {
      showError(error.message || t('settings.syslogSaveFailed'))
    } finally {
      setSyslogSaving(false)
    }
  }

  const handleTestSyslog = async () => {
    setSyslogTesting(true)
    try {
      const response = await settingsService.testSyslog()
      showSuccess(response.message || t('settings.syslogTestSuccess'))
    } catch (error) {
      showError(error.message || t('settings.syslogTestFailed'))
    } finally {
      setSyslogTesting(false)
    }
  }

  const updateSyslogConfig = (key, value) => {
    setSyslogConfig(prev => ({ ...prev, [key]: value }))
  }

  const loadMtlsSettings = async () => {
    setMtlsLoading(true)
    try {
      const response = await mtlsService.getSettings()
      setMtlsSettings(response.data || {})
    } catch {
    } finally {
      setMtlsLoading(false)
    }
  }

  const handleMtlsSave = async () => {
    setMtlsSaving(true)
    try {
      const response = await mtlsService.updateSettings({
        enabled: mtlsSettings.enabled,
        required: mtlsSettings.required,
        trusted_ca_id: mtlsSettings.trusted_ca_id || null,
      })
      const data = response.data || {}
      setMtlsSettings(prev => ({ ...prev, ...data }))
      showSuccess(t('settings.mtls.saved'))
      if (data.needs_restart && !isDocker) {
        waitForRestart()
      } else if (data.restart_message) {
        showWarning(data.restart_message)
      }
    } catch (error) {
      showError(error.message || t('settings.mtls.saveFailed'))
    } finally {
      setMtlsSaving(false)
    }
  }

  // Certificate Transparency
  const loadCtSettings = async () => {
    setCtLoading(true)
    try {
      const response = await settingsService.getCTSettings()
      setCtSettings(response.data || { enabled: false, auto_submit: false, log_urls: [] })
    } catch {
    } finally {
      setCtLoading(false)
    }
  }

  const handleCtSave = async () => {
    setCtSaving(true)
    try {
      await settingsService.updateCTSettings(ctSettings)
      showSuccess(t('settings.ctSettingsUpdated'))
    } catch (error) {
      showError(error.message || t('settings.ctSettingsFailed'))
    } finally {
      setCtSaving(false)
    }
  }

  const handleCtAddLogUrl = () => {
    const url = ctNewLogUrl.trim()
    if (!url) return
    if (ctSettings.log_urls.includes(url)) return
    setCtSettings(prev => ({ ...prev, log_urls: [...prev.log_urls, url] }))
    setCtNewLogUrl('')
  }

  const handleCtRemoveLogUrl = (index) => {
    setCtSettings(prev => ({ ...prev, log_urls: prev.log_urls.filter((_, i) => i !== index) }))
  }

  const handleSave = async (section) => {
    setSaving(true)
    try {
      if (section === 'email') {
        // Email settings go to a different endpoint with mapped field names
        await settingsService.updateEmailSettings({
          smtp_host: settings.smtp_host,
          smtp_port: settings.smtp_port,
          smtp_username: settings.smtp_auth_method !== 'none' ? settings.smtp_username : '',
          smtp_password: settings.smtp_auth_method === 'password' ? settings.smtp_password : '',
          smtp_tls: settings.smtp_use_tls,
          smtp_auth: settings.smtp_auth_method !== 'none',
          smtp_content_type: settings.smtp_content_type || 'html',
          from_email: settings.smtp_from_email,
          from_name: settings.smtp_from_name,
          enabled: true,
          smtp_auth_method: settings.smtp_auth_method,
          smtp_oauth_provider: settings.smtp_oauth_provider,
          smtp_oauth_tenant_id: settings.smtp_oauth_tenant_id,
          smtp_oauth_client_id: settings.smtp_oauth_client_id,
          ...(settings.smtp_oauth_client_secret && settings.smtp_oauth_client_secret !== '********' ? { smtp_oauth_client_secret: settings.smtp_oauth_client_secret } : {}),
          smtp_oauth_authorize_url: settings.smtp_oauth_authorize_url,
          smtp_oauth_token_url: settings.smtp_oauth_token_url,
          smtp_oauth_scope: settings.smtp_oauth_scope,
          smtp_oauth_redirect_uri: settings.smtp_oauth_redirect_uri,
        })
      } else {
        await settingsService.updateBulk(settings)
      }
      showSuccess(t('messages.success.update.settings'))
      if (section === 'email') setOauthDirty(false)
      if (settings.timezone) setAppTimezone(settings.timezone)
      if (settings.date_format) setDateFormat(settings.date_format)
      if (settings.show_time !== undefined) setShowTime(settings.show_time !== 'false' && settings.show_time !== false)
      await loadSettings()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const handleTestEmail = async () => {
    const testEmail = settings._testRecipient || settings.smtp_from_email
    if (!testEmail) {
      setEmailTestResult({ success: false, message: t('settings.testRecipientRequired') })
      return
    }
    setEmailTesting(true)
    setEmailTestResult(null)
    try {
      await settingsService.testEmail(testEmail)
      setEmailTestResult({ success: true, message: `${t('settings.testEmailSuccess')} → ${testEmail}` })
      showSuccess(t('messages.success.email.testSent'))
    } catch (error) {
      const msg = error?.data?.message || error?.data?.error || error.message || t('messages.errors.email.testFailed')
      setEmailTestResult({ success: false, message: msg })
    } finally {
      setEmailTesting(false)
    }
  }

  const applyOAuthProviderPreset = (providerKey) => {
    updateSetting('smtp_oauth_provider', providerKey)
    setOauthDirty(true)
    const preset = oauthPresets[providerKey]
    if (preset) {
      if (preset.smtp_host) updateSetting('smtp_host', preset.smtp_host)
      if (preset.smtp_port) updateSetting('smtp_port', preset.smtp_port)
      if (typeof preset.smtp_use_tls === 'boolean') updateSetting('smtp_use_tls', preset.smtp_use_tls)
      // Force tenant to the right default for each Microsoft variant.
      // Personal Outlook.com → 'consumers' (the field is hidden in the UI).
      // M365 → 'common' unless the admin already set a tenant GUID.
      if (providerKey === 'microsoft') {
        updateSetting('smtp_oauth_tenant_id', 'consumers')
      } else if (providerKey === 'microsoft365' && !settings.smtp_oauth_tenant_id) {
        updateSetting('smtp_oauth_tenant_id', 'common')
      }
    }
  }

  const handleSmtpOAuthAuthorize = async () => {
    try {
      // Auto-save OAuth config if there are unsaved changes,
      // so the backend uses the latest client_id/secret/redirect_uri.
      if (oauthDirty) {
        await handleSave('email')
      }
      const res = await settingsService.getSmtpOAuthAuthorizeUrl(settings.smtp_oauth_redirect_uri || '')
      const authorizeUrl = res?.data?.authorize_url || res?.authorize_url
      if (!authorizeUrl) throw new Error('No authorize URL returned')
      const popup = window.open(authorizeUrl, 'smtp-oauth', 'width=600,height=700')
      let settled = false
      const finish = async (ok) => {
        if (settled) return
        settled = true
        window.removeEventListener('message', handler)
        try { bc && bc.close() } catch {}
        if (ok) {
          showSuccess(t('settings.smtpOauthSuccess'))
          setOauthDirty(false)
          await loadSettings()
        } else {
          showError(t('settings.smtpOauthFailure'))
        }
      }
      const handler = (event) => {
        if (!event.data || event.data.type !== 'smtp-oauth') return
        finish(!!event.data.ok)
      }
      window.addEventListener('message', handler)
      // BroadcastChannel works even when window.opener is null (COOP).
      let bc = null
      try {
        bc = new BroadcastChannel('smtp-oauth')
        bc.onmessage = (event) => {
          if (!event.data || event.data.type !== 'smtp-oauth') return
          finish(!!event.data.ok)
        }
      } catch {}
      // Fallback: when popup closes, re-check settings — covers cases where
      // both postMessage and BroadcastChannel are blocked (strict COOP/sandbox).
      const pollClose = setInterval(async () => {
        if (popup && popup.closed) {
          clearInterval(pollClose)
          if (settled) return
          await loadSettings()
          // Re-read latest settings to detect if authorization succeeded.
          try {
            const fresh = await settingsService.getAll()
            const authorized = !!(fresh?.data?.smtp_oauth_authorized || fresh?.smtp_oauth_authorized)
            finish(authorized)
          } catch {
            finish(false)
          }
        }
      }, 1000)
    } catch (error) {
      showError(error.message || t('settings.smtpOauthFailure'))
    }
  }

  const handleSmtpOAuthRevoke = async () => {
    const confirmed = await showConfirm(t('settings.smtpOauthRevokeConfirm'), {
      title: t('settings.smtpOauthRevoke'),
      confirmText: t('settings.smtpOauthRevoke'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await settingsService.revokeSmtpOAuth()
      showSuccess(t('messages.success.update.settings'))
      loadSettings()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
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
        downloadBlob(blob, response.data.filename)
        showSuccess(t('messages.success.backup.created'))
        setShowBackupModal(false)
        setBackupPassword('')
        loadBackups()
      }
    } catch (error) {
      showError(error.message || t('messages.errors.backup.createFailed'))
    } finally {
      setBackupLoading(false)
    }
  }

  const handleDownloadBackup = async (filename) => {
    try {
      const blob = await systemService.downloadBackup(filename)
      downloadBlob(blob, filename)
      showSuccess(t('messages.success.backup.downloaded'))
    } catch (error) {
      showError(error.message || t('messages.errors.backup.downloadFailed'))
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
      showSuccess(t('messages.success.backup.deleted'))
      loadBackups()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.backup'))
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
      showError(error.message || t('messages.errors.backup.restoreFailed'))
    } finally {
      setBackupLoading(false)
    }
  }

  const handleOptimizeDb = async () => {
    try {
      await systemService.optimizeDatabase()
      showSuccess(t('messages.success.database.optimized'))
      await loadDbStats()
    } catch (error) {
      showError(error.message || t('messages.errors.database.optimizeFailed'))
    }
  }

  const handleIntegrityCheck = async () => {
    try {
      const response = await systemService.integrityCheck()
      const result = response?.data || {}
      if (result.passed) {
        showSuccess(t('messages.success.database.integrityPassed'))
      } else {
        showError(t('settings.integrityErrors', { count: result.errors }))
      }
      await loadDbStats()
    } catch (error) {
      showError(error.message || t('messages.errors.database.integrityFailed'))
    }
  }

  const handleExportDb = async () => {
    try {
      const blob = await systemService.exportDatabase()
      downloadBlob(blob, `ucm-database-${new Date().toISOString().split('T')[0]}.sql`)
      showSuccess(t('messages.success.export.database'))
    } catch (error) {
      showError(error.message || t('messages.errors.database.exportFailed'))
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
      showSuccess(t('messages.success.database.reset'))
      setTimeout(() => window.location.reload(), 2000)
    } catch (error) {
      showError(error.message || t('messages.errors.database.resetFailed'))
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
      const response = await systemService.applyHttpsCert({
        cert_id: selectedHttpsCert.id
      })
      if (response.data?.requires_container_restart) {
        showSuccess(t('settings.dockerCertNotice'))
      } else {
        showSuccess(t('messages.success.https.applied'))
        waitForRestart()
      }
    } catch (error) {
      if (!isDocker && (error.message?.includes('Failed to fetch') || error.code === 'ERR_NETWORK')) {
        waitForRestart()
      } else {
        showError(error.message || t('messages.errors.https.applyFailed'))
      }
    }
  }

  const handleRegenerateHttpsCert = async () => {
    const confirmed = await showConfirm(t('settings.regenerateCertConfirm'), {
      title: t('settings.regenerateCert'),
      confirmText: t('settings.regenerateAndRestart')
    })
    if (!confirmed) return
    
    try {
      const response = await systemService.regenerateHttpsCert({
        common_name: window.location.hostname,
        validity_days: 365
      })
      if (response.data?.requires_container_restart) {
        showSuccess(t('settings.dockerCertNotice'))
      } else {
        showSuccess(t('messages.success.https.regenerated'))
        waitForRestart()
      }
    } catch (error) {
      if (!isDocker && (error.message?.includes('Failed to fetch') || error.code === 'ERR_NETWORK')) {
        waitForRestart()
      } else {
        showError(error.message || t('messages.errors.https.regenerateFailed'))
      }
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
          <GeneralSection
            settings={settings}
            updateSetting={updateSetting}
            handleSave={handleSave}
            saving={saving}
            canWrite={canWrite}
          />
        )

      case 'appearance':
        return <AppearanceSettings />

      case 'email':
        return (
          <EmailSection
            settings={settings}
            updateSetting={updateSetting}
            handleSave={handleSave}
            saving={saving}
            canWrite={canWrite}
            isMobile={isMobile}
            emailTestResult={emailTestResult}
            emailTesting={emailTesting}
            handleTestEmail={handleTestEmail}
            oauthDirty={oauthDirty}
            setOauthDirty={setOauthDirty}
            oauthPresets={oauthPresets}
            applyOAuthProviderPreset={applyOAuthProviderPreset}
            handleSmtpOAuthAuthorize={handleSmtpOAuthAuthorize}
            handleSmtpOAuthRevoke={handleSmtpOAuthRevoke}
            expiryAlerts={expiryAlerts}
            setExpiryAlerts={setExpiryAlerts}
            saveExpiryAlerts={saveExpiryAlerts}
            triggerExpiryCheck={triggerExpiryCheck}
            showTemplateEditor={showTemplateEditor}
            setShowTemplateEditor={setShowTemplateEditor}
          />
        )
      case 'security':
        return (
          <SecuritySection
            settings={settings}
            updateSetting={updateSetting}
            handleSave={handleSave}
            saving={saving}
            hasPermission={hasPermission}
            encryptionStatus={encryptionStatus}
            setShowEnableEncryptionModal={setShowEnableEncryptionModal}
            setShowDisableEncryptionModal={setShowDisableEncryptionModal}
            anomalies={anomalies}
            anomaliesLoading={anomaliesLoading}
            loadAnomalies={loadAnomalies}
            mtlsSettings={mtlsSettings}
            setMtlsSettings={setMtlsSettings}
            mtlsLoading={mtlsLoading}
            mtlsSaving={mtlsSaving}
            handleMtlsSave={handleMtlsSave}
            cas={cas}
          />
        )
      case 'sso':
        return (
          <SsoSection
            ssoProviders={ssoProviders}
            ssoLoading={ssoLoading}
            ssoTesting={ssoTesting}
            handleSsoCreate={handleSsoCreate}
            handleSsoEdit={handleSsoEdit}
            handleSsoToggle={handleSsoToggle}
            handleSsoTest={handleSsoTest}
            setSsoConfirmDelete={setSsoConfirmDelete}
            hasPermission={hasPermission}
          />
        )
      case 'backup':
        return (
          <BackupSection
            settings={settings}
            updateSetting={updateSetting}
            handleSave={handleSave}
            saving={saving}
            hasPermission={hasPermission}
            backups={backups}
            setShowBackupModal={setShowBackupModal}
            setShowRestoreModal={setShowRestoreModal}
            setRestoreFile={setRestoreFile}
            handleDownloadBackup={handleDownloadBackup}
            handleDeleteBackup={handleDeleteBackup}
          />
        )
      case 'audit':
        return (
          <AuditSection
            settings={settings}
            updateSetting={updateSetting}
            handleSave={handleSave}
            saving={saving}
            hasPermission={hasPermission}
            syslogConfig={syslogConfig}
            updateSyslogConfig={updateSyslogConfig}
            syslogSaving={syslogSaving}
            syslogTesting={syslogTesting}
            handleSaveSyslog={handleSaveSyslog}
            handleTestSyslog={handleTestSyslog}
          />
        )
      case 'database':
        return (
          <DatabaseSection
            dbStats={dbStats}
            handleOptimizeDb={handleOptimizeDb}
            handleIntegrityCheck={handleIntegrityCheck}
            handleExportDb={handleExportDb}
            handleResetDb={handleResetDb}
          />
        )
      case 'https':
        return (
          <HttpsSection
            httpsInfo={httpsInfo}
            selectedHttpsCert={selectedHttpsCert}
            setSelectedHttpsCert={setSelectedHttpsCert}
            setShowCertPicker={setShowCertPicker}
            handleApplyUcmCert={handleApplyUcmCert}
            handleRegenerateHttpsCert={handleRegenerateHttpsCert}
            setShowHttpsImportModal={setShowHttpsImportModal}
          />
        )
      case 'updates':
        return <UpdatesSection />
      case 'webhooks':
        return (
          <WebhooksSection
            webhooks={webhooks}
            webhooksLoading={webhooksLoading}
            webhookTesting={webhookTesting}
            handleWebhookCreate={handleWebhookCreate}
            handleWebhookEdit={handleWebhookEdit}
            handleWebhookToggle={handleWebhookToggle}
            handleWebhookTest={handleWebhookTest}
            setWebhookConfirmDelete={setWebhookConfirmDelete}
            hasPermission={hasPermission}
          />
        )
      case 'ct':
        return (
          <CTSection
            ctSettings={ctSettings}
            setCtSettings={setCtSettings}
            ctLoading={ctLoading}
            ctSaving={ctSaving}
            ctNewLogUrl={ctNewLogUrl}
            setCtNewLogUrl={setCtNewLogUrl}
            handleCtSave={handleCtSave}
            handleCtAddLogUrl={handleCtAddLogUrl}
            handleCtRemoveLogUrl={handleCtRemoveLogUrl}
          />
        )
      case 'microsoftCA':
        return (
          <MicrosoftCASection
            mscaConnections={mscaConnections}
            mscaLoading={mscaLoading}
            mscaTesting={mscaTesting}
            handleMscaCreate={handleMscaCreate}
            handleMscaEdit={handleMscaEdit}
            handleMscaToggle={handleMscaToggle}
            handleMscaTest={handleMscaTest}
            setMscaConfirmDelete={setMscaConfirmDelete}
            hasPermission={hasPermission}
          />
        )
      case 'about':
        return <AboutSection />

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
      {reconnecting && (
        <ServiceReconnectOverlay status={reconnectStatus} attempt={attempt} countdown={countdown} onCancel={cancel} />
      )}
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
          { labelKey: 'settings.groups.security', tabs: ['security', 'sso', 'ct'], color: 'icon-bg-amber' },
          { labelKey: 'settings.groups.notifications', tabs: ['email', 'webhooks'], color: 'icon-bg-teal' },
          { labelKey: 'settings.groups.integrations', tabs: ['microsoftCA'], color: 'icon-bg-indigo' },
          { labelKey: 'settings.groups.interface', tabs: ['appearance', 'audit'], color: 'icon-bg-violet' },
          { labelKey: 'settings.groups.about', tabs: ['about'], color: 'icon-bg-sky' },
        ]}
        helpPageKey="settings"
      >
        {renderCategoryContent()}
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
            noAutofill
            value={backupPassword}
            onChange={(e) => setBackupPassword(e.target.value)}
            placeholder={t('settings.min12Characters')}
            helperText={t('settings.encryptionPasswordHelper')}
            autoFocus
            showStrength
          />
          <div className="flex gap-3 justify-end pt-4">
            <Button type="button" variant="secondary" onClick={() => { setShowBackupModal(false); setBackupPassword('') }}>
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
            noAutofill
            value={restorePassword}
            onChange={(e) => setRestorePassword(e.target.value)}
            placeholder={t('settings.enterBackupPassword')}
            autoFocus
          />
          <div className="flex gap-3 justify-end pt-4">
            <Button type="button" variant="secondary" onClick={() => { setShowRestoreModal(false); setRestorePassword(''); setRestoreFile(null) }}>
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
        onClose={() => { setShowSsoModal(false); setEditingSsoProvider(null); setEditingSsoType(null) }}
        title={editingSsoProvider ? t('sso.editProvider') : t('sso.newProvider')}
        size="lg"
      >
        <SsoProviderForm
          provider={editingSsoProvider}
          forcedType={editingSsoType}
          onSave={handleSsoSave}
          onCancel={() => { setShowSsoModal(false); setEditingSsoProvider(null); setEditingSsoType(null) }}
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

      {/* Microsoft CA Connection Modal */}
      <Modal
        open={showMscaModal}
        onClose={() => { setShowMscaModal(false); setEditingMsca(null) }}
        title={editingMsca ? t('msca.editConnection') : t('msca.addConnection')}
        size="lg"
      >
        <MscaConnectionForm
          connection={editingMsca}
          onSave={handleMscaSave}
          onCancel={() => { setShowMscaModal(false); setEditingMsca(null) }}
        />
      </Modal>

      {/* Microsoft CA Delete Confirmation */}
      <ConfirmModal
        open={!!mscaConfirmDelete}
        onClose={() => setMscaConfirmDelete(null)}
        onConfirm={handleMscaDelete}
        title={t('common.confirmDelete')}
        message={t('msca.deleteConfirm')}
        confirmText={t('common.delete')}
        variant="danger"
      />
      
      {/* Enable Encryption Modal */}
      <Modal
        open={showEnableEncryptionModal}
        onClose={() => {
          setShowEnableEncryptionModal(false)
          setEncryptionConfirmText('')
          setEncryptionChecks({ backup: false, keyFile: false, lostKeys: false })
        }}
        title={t('settings.enableEncryption')}
        maxWidth="lg"
      >
        <div className="p-4 space-y-4">
          <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
            <div className="flex items-start gap-2">
              <WarningCircle size={20} className="text-amber-500 flex-shrink-0 mt-0.5" weight="fill" />
              <div className="text-sm text-text-primary">
                <p className="font-semibold mb-1">{t('settings.encryptionWarningTitle')}</p>
                <p className="text-text-secondary">{t('settings.encryptionWarningDesc')}</p>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={encryptionChecks.keyFile}
                onChange={(e) => setEncryptionChecks(prev => ({ ...prev, keyFile: e.target.checked }))}
                className="rounded border-border bg-bg-tertiary mt-0.5"
              />
              <span className="text-sm text-text-primary">{t('settings.encryptionCheckKeyFile')}</span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={encryptionChecks.backup}
                onChange={(e) => setEncryptionChecks(prev => ({ ...prev, backup: e.target.checked }))}
                className="rounded border-border bg-bg-tertiary mt-0.5"
              />
              <span className="text-sm text-text-primary">{t('settings.encryptionCheckBackup')}</span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={encryptionChecks.lostKeys}
                onChange={(e) => setEncryptionChecks(prev => ({ ...prev, lostKeys: e.target.checked }))}
                className="rounded border-border bg-bg-tertiary mt-0.5"
              />
              <span className="text-sm text-text-primary">{t('settings.encryptionCheckLostKeys')}</span>
            </label>
          </div>

          <div>
            <label className="block text-sm text-text-secondary mb-1">
              {t('settings.typeToConfirm', { word: 'ENCRYPT' })}
            </label>
            <Input
              value={encryptionConfirmText}
              onChange={(e) => setEncryptionConfirmText(e.target.value)}
              placeholder="ENCRYPT"
            />
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="outline" onClick={() => {
              setShowEnableEncryptionModal(false)
              setEncryptionConfirmText('')
              setEncryptionChecks({ backup: false, keyFile: false, lostKeys: false })
            }}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="primary"
              onClick={handleEnableEncryption}
              disabled={
                encryptionLoading ||
                encryptionConfirmText !== 'ENCRYPT' ||
                !encryptionChecks.backup ||
                !encryptionChecks.keyFile ||
                !encryptionChecks.lostKeys
              }
            >
              {encryptionLoading ? <LoadingSpinner size="sm" /> : <LockKey size={16} />}
              {t('settings.enableEncryption')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Disable Encryption Modal */}
      <ConfirmModal
        open={showDisableEncryptionModal}
        onClose={() => setShowDisableEncryptionModal(false)}
        onConfirm={handleDisableEncryption}
        title={t('settings.disableEncryption')}
        message={t('settings.disableEncryptionConfirm')}
        confirmText={t('settings.disableEncryption')}
        variant="danger"
        loading={encryptionLoading}
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
                const response = await systemService.applyHttpsCert({ cert_id: imported.id })
                if (response.data?.requires_container_restart) {
                  showSuccess(t('settings.dockerCertNotice'))
                } else {
                  showSuccess(t('messages.success.https.applied'))
                  setTimeout(() => window.location.reload(), 3000)
                }
              } catch (error) {
                showError(error.message || t('messages.errors.https.applyFailed'))
              }
            }
          } else {
            showSuccess(t('common.importSuccess'))
          }
        }}
        defaultType="certificate"
      />

      {/* Certificate Picker Modal for HTTPS cert selection */}
      <CertificatePickerModal
        isOpen={showCertPicker}
        onClose={() => setShowCertPicker(false)}
        onSelect={(cert) => {
          setSelectedHttpsCert(cert)
          setShowCertPicker(false)
        }}
        filters={{ status: 'valid', has_private_key: true }}
      />
    </>
  )
}
