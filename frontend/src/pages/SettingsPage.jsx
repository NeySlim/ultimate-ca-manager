/**
 * Settings page, on the mockup's sectioned form (settingsView()): the table of contents, the
 * stacked section frames, then the save bar.
 */
import { withoutAdminOnly } from './settings/adminOnlySettings'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { useSortParam } from '../components/atelier/useSortParam'
import { ListBullets, HardDrives, Lock, Palette, Info, Timer, Certificate, Eye, Rocket, Bell, UsersThree, WindowsLogo, ClockClockwise, IdentificationBadge, CloudArrowUp, SlidersHorizontal, PaperPlaneTilt, Archive } from '@phosphor-icons/react'
import { ServiceReconnectOverlay } from '../components'
import { SmartImportModal } from '../components/SmartImport'
import CertificatePickerModal from '../components/CertificatePickerModal'
import { settingsService, systemService, casService, ssoService, mtlsService, mscaService, auditService } from '../services'
import { holdSignOut } from '../services/apiClient'
import { useInFlight } from '../hooks/useInFlight'
import { useAuth, useNotification, useMobile } from '../contexts'
import { useServiceReconnect } from '../hooks'
import { usePermission, useJob, isTransientError, jobPercent } from '../hooks'
import { acceptedJob } from '../services/jobs.service'
import { formatDate, downloadBlob } from '../lib/utils'
import AboutSection from './settings/AboutSection'
import { expiryCheckOutcome } from './settings/expiryCheck'
import { addCtLogUrl, removeCtLogUrl } from './settings/ctLogUrls'
import AppearanceSettings from './settings/AppearanceSettings'
import SsoProviderForm from './settings/SsoProviderForm'
import WebhookForm from './settings/WebhookForm'
import MscaConnectionForm from './settings/MscaConnectionForm'
import MscaCaControlModal from '../components/MscaCaControlModal'
import { Modal as AtlModal, ConfirmModal as AtlConfirmModal } from '../components/atelier/Form'
import AdConnectorSection from './settings/AdConnectorSection'
import XcepWstepSection from './settings/XcepWstepSection'
import GeneralSection from './settings/GeneralSection'
import EmailSection from './settings/EmailSection'
import SecuritySection from './settings/SecuritySection'
import SsoSection from './settings/SsoSection'
import BackupSection from './settings/BackupSection'
import { ceilingNotice } from './settings/backupCeiling'
import RestoreReport from './settings/RestoreReport'
import { BackupDialog, RestoreDialog } from './settings/BackupDialogs'
import { EnableEncryptionDialog, MasterKeyBackupDialog } from './settings/EncryptionDialogs'
import { loginUrl } from '../navigation/safeNext'
import { useRestoreJob, UNCANCELLABLE_PHASES } from './settings/useRestoreJob'
import AuditSection from './settings/AuditSection'
import DatabaseSection from './settings/DatabaseSection'
import { afterDatabaseReset } from './settings/databaseReset'
import HttpsSection from './settings/HttpsSection'
import UpdatesSection from './settings/UpdatesSection'
import DeploySection from './settings/DeploySection'
import SchedulerSection from './settings/SchedulerSection'
import WebhooksSection from './settings/WebhooksSection'
import CTSection from './settings/CTSection'
import MicrosoftCASection from './settings/MicrosoftCASection'
import AutoRenewalSection from './settings/AutoRenewalSection'
import { setAppTimezone } from '../stores/timezoneStore'
import { setDateFormat, setShowTime } from '../stores/dateFormatStore'
import { reportSilentFailure } from '../lib/silentFailure'
import { autoRenewalWaitingMessage } from '../lib/autoRenewalWaiting'
import { secretRequiredForTarget, smtpSecretTargets } from '../lib/secretTarget'
import { SavePartsContext, useSavePartsRegistry, changedKeys, useUnloadGuard } from '../hooks/useSaveParts'
import { usePhoneWidth } from '../hooks/useMediaQuery'
import { keepDraft, readDraft } from '../lib/draftMemory'
import { Zone, PageHead, Pill, SkeletonPanel, jumpTo } from '../components/atelier'
import { SettingsLayout, SettingsToc, SettingsJump, SettingsFrame, SettingsSaveBar } from '../components/atelier/SettingsView'
import { useSaveBarFocus } from '../hooks/useSaveBarFocus'
import { DockSlot, DockSlotProvider } from './protocols/dockSlot'
import SettingsHistory from './settings/SettingsHistory'
import { fieldProblems, fieldSection } from './settings/fieldChecks'
import { changedLabels } from './settings/fieldLabels'

// Sections: label, sentence of the frame, icon; `permission` hides one from other roles
const BASE_SETTINGS_CATEGORIES = [
  { id: 'general', labelKey: 'settings.tabs.general', descKey: 'settings.generalSubtitle', icon: SlidersHorizontal, color: 'icon-bg-blue' },
  { id: 'appearance', labelKey: 'settings.tabs.appearance', descKey: 'settings.appearanceSubtitle', icon: Palette, color: 'icon-bg-violet' },
  { id: 'email', labelKey: 'settings.tabs.email', descKey: 'settings.emailSubtitle', icon: PaperPlaneTilt, color: 'icon-bg-teal' },
  { id: 'security', labelKey: 'settings.tabs.security', descKey: 'settings.securitySubtitle', icon: Lock, color: 'icon-bg-amber' },
  { id: 'sso', labelKey: 'settings.tabs.sso', descKey: 'sso.subtitle', icon: UsersThree, color: 'icon-bg-purple' },
  // Listing, downloading and restoring an archive are admin:system on the API (the archive
  // holds every key and secret): the section is shown to that permission only.
  { id: 'backup', labelKey: 'settings.tabs.backup', descKey: 'settings.backupSubtitle', icon: Archive, color: 'icon-bg-emerald', permission: 'admin:system' },
  { id: 'audit', labelKey: 'settings.tabs.audit', descKey: 'settings.auditSubtitle', icon: ListBullets, color: 'icon-bg-orange' },
  { id: 'database', labelKey: 'settings.tabs.database', descKey: 'settings.databaseSubtitle', icon: HardDrives, color: 'icon-bg-teal' },
  { id: 'https', labelKey: 'settings.tabs.https', descKey: 'settings.httpsSubtitle', icon: Certificate, color: 'icon-bg-emerald' },
  { id: 'updates', labelKey: 'settings.tabs.updates', descKey: 'settings.updatesSubtitle', icon: Rocket, color: 'icon-bg-violet' },
  { id: 'scheduler', labelKey: 'settings.tabs.scheduler', descKey: 'scheduler.subtitle', icon: Timer, color: 'icon-bg-blue' },
  { id: 'webhooks', labelKey: 'settings.tabs.webhooks', descKey: 'webhooks.subtitle', icon: Bell, color: 'icon-bg-orange' },
  { id: 'ct', labelKey: 'settings.tabs.ct', descKey: 'settings.ctDescription', icon: Eye, color: 'icon-bg-cyan' },
  { id: 'autoRenewal', labelKey: 'settings.tabs.autoRenewal', descKey: 'settings.autoRenewalDescription', icon: ClockClockwise, color: 'icon-bg-emerald' },
  // Admin-only (#299) — hidden from non-admin roles below
  { id: 'deploy', labelKey: 'settings.tabs.deploy', descKey: 'deploy.subtitle', icon: CloudArrowUp, color: 'icon-bg-emerald', permission: 'read:deploy' },
  { id: 'microsoftCA', labelKey: 'settings.tabs.microsoftCA', descKey: 'msca.subtitle', icon: WindowsLogo, color: 'icon-bg-indigo' },
  { id: 'adConnector', labelKey: 'settings.tabs.adConnector', descKey: 'adConnector.subtitle', icon: IdentificationBadge, color: 'icon-bg-blue' },
  { id: 'xcepWstep', labelKey: 'settings.tabs.xcepWstep', descKey: 'xcepWstep.subtitle', icon: WindowsLogo, color: 'icon-bg-indigo' },
  { id: 'about', labelKey: 'settings.tabs.about', descKey: 'settings.about.subtitle', icon: Info, color: 'icon-bg-gray' },
]

// The mockup's pictogram of each section in the table of contents
const SECTION_ICONS = {
  general: 'settings', appearance: 'sun', email: 'send', security: 'lock', sso: 'users', backup: 'archive',
  audit: 'activity', database: 'server', https: 'cert', updates: 'download', scheduler: 'clock', webhooks: 'bell',
  ct: 'eye', autoRenewal: 'refresh', deploy: 'upload', microsoftCA: 'plug', adConnector: 'globe', xcepWstep: 'monitor', about: 'help',
}
// The sections whose table needs more than the 960 px of a card in a narrow column (the scheduler's nine columns)
const WIDE_SECTIONS = new Set(['scheduler'])
// Groups of the table of contents, named by what they hold; the frames follow the same
// order. Four groups keep every entry in view on a 1000 px high window.
const SETTINGS_GROUPS = [
  { id: 'instance', labelKey: 'settings.groups.instance', ids: ['general', 'appearance', 'updates', 'scheduler', 'database', 'https', 'backup', 'about'] },
  { id: 'security', labelKey: 'settings.groups.security', ids: ['security', 'sso', 'ct', 'audit'] },
  { id: 'automation', labelKey: 'settings.groups.automation', ids: ['email', 'webhooks', 'autoRenewal', 'deploy'] },
  { id: 'integrations', labelKey: 'settings.groups.integrations', ids: ['microsoftCA', 'adConnector', 'xcepWstep'] },
]

// Audit actions a save of these sections writes (resource_type settings)
const SETTINGS_SAVE_ACTIONS = ['settings_update', 'syslog_config_updated', 'mtls_settings_update', 'ct_settings_updated']

// Type of the HTTPS certificate the server names, in the reader's language
// After a TLS listener reload: the new worker serves within a few seconds, then the state is read again
const HTTPS_RELOAD_SETTLE_MS = 4000
const HTTPS_TYPES = { 'CA-Signed': 'settings.httpsType.caSigned', 'Self-Signed': 'settings.httpsType.selfSigned' }

// Draft of the page kept for the tab (lib/draftMemory)
const SETTINGS_DRAFT = 'settings'

// Keys the email route stores (mapped names); the others go through the bulk route
const EMAIL_KEYS = [
  'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'smtp_security', 'smtp_from_email',
  'smtp_from_name', 'smtp_auth', 'smtp_content_type', 'smtp_auth_method', 'smtp_oauth_provider',
  'smtp_oauth_tenant_id', 'smtp_oauth_client_id', 'smtp_oauth_client_secret', 'smtp_oauth_authorize_url',
  'smtp_oauth_token_url', 'smtp_oauth_scope', 'smtp_oauth_redirect_uri',
]
const EMAIL_STATE_KEYS = ['has_oauth_client_secret', 'has_oauth_refresh_token']
const bulkKeys = (draft, saved) => [...new Set([...Object.keys(saved || {}), ...Object.keys(draft || {})])]
  .filter((k) => !k.startsWith('_') && !EMAIL_KEYS.includes(k) && !EMAIL_STATE_KEYS.includes(k))
const MTLS_KEYS = ['enabled', 'required', 'trusted_ca_id']
const pick = (obj, keys) => Object.fromEntries(keys.filter((k) => k in (obj || {})).map((k) => [k, obj[k]]))

// Backup password rules, mirrored from the server (services/backup):
// at least 12 characters, and at least 8 distinct ones, relaxed to 6 for a
// password of 16 characters or more. The dialog used to check only the
// length, so a password the strength meter called strong was refused by the
// server with a message that named no rule (#346).
const BACKUP_PASSWORD_MIN_LENGTH = 12
const BACKUP_PASSWORD_MIN_DISTINCT = 8
const BACKUP_PASSWORD_LONG_LENGTH = 16
const BACKUP_PASSWORD_MIN_DISTINCT_LONG = 6

export function backupPasswordProblem(password, t) {
  // Count characters the way the server does. A string's length counts UTF-16
  // units, so an emoji counts twice here and once there: a password the dialog
  // accepted came back refused by the API (#346 review).
  const characters = password ? [...password] : []
  if (characters.length < BACKUP_PASSWORD_MIN_LENGTH) {
    return t('settings.passwordMinLength')
  }
  const distinct = new Set(characters).size
  const required = characters.length >= BACKUP_PASSWORD_LONG_LENGTH
    ? BACKUP_PASSWORD_MIN_DISTINCT_LONG
    : BACKUP_PASSWORD_MIN_DISTINCT
  if (distinct < required) {
    return t('settings.backupPasswordTooRepetitive', { distinct, required })
  }
  return null
}

// The archives' sort keys, read by the server as `<key>_<asc|desc>`
const BACKUP_NEWEST = { key: 'created', asc: false }
const BACKUP_SORT_KEYS = ['created', 'size', 'name']
const backupOrder = (sort) => `${sort.key}_${sort.asc ? 'asc' : 'desc'}`

export default function SettingsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { showSuccess, showError, showInfo, showConfirm, showPrompt, showWarning } = useNotification()
  const { canWrite, hasPermission } = usePermission()
  const { isMobile } = useMobile()
  // A wide screen holds the save state in the page head; a phone keeps the bar under the form
  const phone = usePhoneWidth()
  useSaveBarFocus(phone)
  const [searchParams, setSearchParams] = useSearchParams()
  const { reconnecting, status: reconnectStatus, attempt, countdown, waitForRestart, cancel } = useServiceReconnect()
  
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState({})
  // Values as last loaded or stored: the save bar counts the draft against them
  const [savedSettings, setSavedSettings] = useState({})
  const savedSettingsRef = useRef(savedSettings)
  savedSettingsRef.current = savedSettings
  // Section whose field last changed a key: a bulk save in error points at it
  const keyOrigin = useRef({})
  const [sectionErrors, setSectionErrors] = useState({})
  // Fields out of the bounds the interface knows: marked on the field, nothing sent
  const [fieldErrors, setFieldErrors] = useState({})
  const [announce, setAnnounce] = useState('')
  const [invalidFocus, setInvalidFocus] = useState(0)
  const [savingAll, setSavingAll] = useState(false)
  const [savedVersion, setSavedVersion] = useState(0)
  const [settingsLog, setSettingsLog] = useState(null)
  const saveState = useRef(null)
  const parts = useSavePartsRegistry()
  // What was left pending when the page was last left, taken back part by part as each loads
  const kept = useRef(readDraft(SETTINGS_DRAFT))
  const takeKept = (name) => {
    const value = kept.current?.[name]
    if (kept.current) delete kept.current[name]
    return value
  }
  const [emailTestResult, setEmailTestResult] = useState(null) // { success, message }
  const [emailTesting, setEmailTesting] = useState(false)
  const [oauthDirty, setOauthDirty] = useState(false)
  // Email settings as last loaded: the targets the saved SMTP secrets belong to
  const [savedEmail, setSavedEmail] = useState(null)
  const [oauthPresets, setOauthPresets] = useState({})
  const [showTemplateEditor, setShowTemplateEditor] = useState(false)
  const [backups, setBackups] = useState([])
  const [backupMeta, setBackupMeta] = useState({ total: 0, pages: 1, page: 1 })
  const [backupSchedule, setBackupSchedule] = useState({})
  // The archives' order lives in the address under its own scope (the sections are stacked): the newest first by default
  const backupSort = useSortParam(BACKUP_NEWEST, BACKUP_SORT_KEYS, { scope: 'backup' })
  const urlBackupOrder = backupOrder(backupSort.sort)
  const [backupQuery, setBackupQuery] = useState(() => ({ page: 1, per_page: 20, search: '', sort: urlBackupOrder }))
  const [selectedBackups, setSelectedBackups] = useState([])
  const [backupBusy, setBackupBusy] = useState(false)
  const [dbStats, setDbStats] = useState(null)
  const [httpsInfo, setHttpsInfo] = useState(null)
  const [selectedHttpsCert, setSelectedHttpsCert] = useState(null)
  const [showCertPicker, setShowCertPicker] = useState(false)
  const [cas, setCas] = useState([])
  const [isDocker, setIsDocker] = useState(false)  
  // Expiry alert settings
  const [expiryAlerts, setExpiryAlerts] = useState({
    enabled: true, alert_days: [30, 14, 7, 1], include_revoked: false, exclude_acme: false, recipients: []
  })
  const [savedExpiryAlerts, setSavedExpiryAlerts] = useState(expiryAlerts)
  
  // The section a link names: ?tab= (the product's links), or ?section= as well
  const sectionParam = searchParams.get('tab') || searchParams.get('section')
  const [selectedCategory, setSelectedCategory] = useState(sectionParam || 'general')

  // Re-sync when the URL's ?tab= changes from outside this component (e.g.
  // navigate('/settings?tab=adConnector') from another page's "Configure"
  // link) -- the state above only captures the URL at mount, and React
  // Router doesn't remount this component for an in-place query-param
  // change, so without this the tab never visibly switches.
  useEffect(() => {
    setSelectedCategory(sectionParam || 'general')
  }, [sectionParam])

  // Every section is on the page: a jump scrolls to its frame and gives its title the focus
  const jumpToSection = useCallback((categoryId, options) => jumpTo(categoryId, options), [])

  // Update URL when category changes
  const handleCategoryChange = (categoryId) => {
    setSelectedCategory(categoryId)
    searchParams.delete('section')
    if (categoryId === 'general') {
      searchParams.delete('tab')
    } else {
      searchParams.set('tab', categoryId)
    }
    setSearchParams(searchParams, { replace: true })
    jumpToSection(categoryId)
  }

  // A link to /settings?tab=<id> (overview, palette, other pages) lands on that section's frame
  const tabParam = sectionParam
  useEffect(() => {
    if (loading || !tabParam) return undefined
    jumpToSection(tabParam, { quiet: true })
    // Sections above still load and grow: the frame is held in place until the user moves
    const form = document.getElementById('settings-form')
    if (!form || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => {
      document.getElementById(`set-sec-${tabParam}`)?.scrollIntoView?.({ block: 'start' })
    })
    const release = () => observer.disconnect()
    observer.observe(form)
    const timer = setTimeout(release, 5000)
    const events = ['wheel', 'touchstart', 'keydown', 'pointerdown']
    events.forEach((e) => window.addEventListener(e, release, { once: true, passive: true }))
    return () => {
      release()
      clearTimeout(timer)
      events.forEach((e) => window.removeEventListener(e, release))
    }
  }, [tabParam, loading, jumpToSection])
  
  // Backup modal states
  const [showBackupModal, setShowBackupModal] = useState(false)
  const [showRestoreModal, setShowRestoreModal] = useState(false)
  const [backupPassword, setBackupPassword] = useState('')
  const [restorePassword, setRestorePassword] = useState('')
  const [restoreFile, setRestoreFile] = useState(null)
  const [backupLoading, setBackupLoading] = useState(false)
  // A backup that outlasts the request runs as a job: followed here, its archive offered at the end
  const { job: backupJob, running: backupRunning, follow: followBackupJob, resume: resumeBackupJob,
    cancel: cancelBackupJob } = useJob()
  const [backupReady, setBackupReady] = useState(null)
  const [restoreProgress, setRestoreProgress] = useState(null)
  const [restoreReport, setRestoreReport] = useState(null)
  // Off the page the report can no longer show: the held sign-out goes with it
  const mounted = useRef(true)
  const holdingSignOut = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      if (holdingSignOut.current) {
        holdingSignOut.current = false
        holdSignOut(false)
      }
    }
  }, [])
  // A restore that outlasts the request runs as a job; its report survives its own sign-out
  const releaseSignOut = () => {
    holdingSignOut.current = false
    holdSignOut(false)
  }
  // A restore's server error stays until closed: a committed restore's asks a restart
  const showRestoreError = (message, status) => {
    if (status >= 500) showError(message, 0)
    else showError(message)
  }
  const restoreJob = useRestoreJob({
    enabled: hasPermission('admin:system'),
    account: user?.username,
    onReport: (data) => {
      setShowRestoreModal(false)
      setRestoreReport(data)
    },
    onFailure: (job) => {
      releaseSignOut()
      setShowRestoreModal(false)
      if (job.state === 'cancelled') showWarning(t('settings.restoreCancelled'))
      else if (job.reason === 'executor_lost' || job.reason === 'not_taken') showError(t('settings.restoreLost'))
      else showRestoreError(job.result?.message || t('messages.errors.backup.restoreFailed'), job.result?.code)
    },
    // The job can no longer be followed and no commit was seen: its end shows at the next visit
    onLost: (error) => {
      releaseSignOut()
      setShowRestoreModal(false)
      showError(isTransientError(error) ? t('settings.restoreContactLost')
        : error?.message || t('messages.errors.backup.restoreFailed'))
    },
  })
  useEffect(() => {
    if (restoreJob.running || restoreJob.signInNeeded) setShowRestoreModal(true)
  }, [restoreJob.running, restoreJob.signInNeeded])
  
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
  // One deletion at a time: the SSO, webhook and Microsoft CA confirmations share it
  const [deleting, runDelete] = useInFlight()
  const [mscaCaControl, setMscaCaControl] = useState(null)

  // Active Directory Connector state

  // Encryption states
  const [encryptionStatus, setEncryptionStatus] = useState(null)
  const [secretsStatus, setSecretsStatus] = useState(null)
  const [sessionKeyLoading, setSessionKeyLoading] = useState(false)
  const [showEnableEncryptionModal, setShowEnableEncryptionModal] = useState(false)
  const [showDisableEncryptionModal, setShowDisableEncryptionModal] = useState(false)
  const [encryptionLoading, setEncryptionLoading] = useState(false)

  // Master-key backup modal — shown immediately after enable-encryption succeeds.
  // Holds the freshly-generated key so the user can download it BEFORE leaving
  // the page. Without this backup, losing /etc/ucm/master.key = losing every
  // encrypted private key in the DB.
  const [showBackupKeyModal, setShowBackupKeyModal] = useState(false)
  const [backupKeyMaterial, setBackupKeyMaterial] = useState(null)
  const [backupKeyDownloaded, setBackupKeyDownloaded] = useState(false)

  // Anomaly detection state
  const [anomalies, setAnomalies] = useState([])
  const [anomaliesLoading, setAnomaliesLoading] = useState(false)

  // Syslog state
  const [syslogConfig, setSyslogConfig] = useState({ enabled: false, host: '', port: 514, protocol: 'udp', tls: false, tls_verify: true, framing: 'line', categories: ['certificate', 'ca', 'csr', 'user', 'acme', 'scep', 'system'] })
  const [syslogTesting, setSyslogTesting] = useState(false)
  const [syslogTestResult, setSyslogTestResult] = useState(null)
  const [syslogSaving, setSyslogSaving] = useState(false)
  const [savedSyslog, setSavedSyslog] = useState(syslogConfig)

  // mTLS state
  const [mtlsSettings, setMtlsSettings] = useState({ enabled: false, required: false, trusted_ca_id: '', trusted_ca: null })
  const [mtlsLoading, setMtlsLoading] = useState(false)
  const [mtlsSaving, setMtlsSaving] = useState(false)
  const [savedMtls, setSavedMtls] = useState(mtlsSettings)

  // Certificate Transparency state
  const [ctSettings, setCtSettings] = useState({ enabled: false, auto_submit: false, log_urls: [] })
  const [ctLoading, setCtLoading] = useState(false)
  const [ctSaving, setCtSaving] = useState(false)
  const [ctNewLogUrl, setCtNewLogUrl] = useState('')
  const [savedCt, setSavedCt] = useState(ctSettings)

  // Auto-renewal state
  const [arSettings, setArSettings] = useState({
    enabled: false,
    days_before_expiry: 30,
    renewal_sources: ['manual', 'scep', 'acme', 'est'],
    notify_on_renewal: true,
    notify_on_failure: true,
    notify_emails: [],
  })
  const [arLoading, setArLoading] = useState(false)
  const [arSaving, setArSaving] = useState(false)
  const [arRunning, setArRunning] = useState(false)
  const [arRunResult, setArRunResult] = useState(null)
  const [savedAr, setSavedAr] = useState(arSettings)

  // All settings categories (SSO now integrated directly)
  const SETTINGS_CATEGORIES = BASE_SETTINGS_CATEGORIES

  useEffect(() => {
    loadSettings({ initial: true })
    loadSettingsLog()
    // Backup listing is admin:system now — don't fire a request every other
    // role is refused.
    if (hasPermission('admin:system')) loadBackups()
    else if (hasPermission('read:settings')) loadBackupSchedule()
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
    loadAutoRenewalSettings()
    systemService.getServiceStatus().then(r => setIsDocker(r.data?.is_docker || false)).catch(() => {})
  }, [])

  // `keep`: keys whose draft survives the reload (a part whose save failed).
  // `keepPending`: every key still differing from what was loaded survives too, except `stored`.
  const loadSettings = async ({ initial = false, keep = [], keepPending = false, stored = [] } = {}) => {
    if (initial) setLoading(true)
    const savedBefore = savedSettingsRef.current
    try {
      const [generalRes, emailRes] = await Promise.all([
        settingsService.getAll(),
        settingsService.getEmailSettings().catch(() => ({ data: {} }))
      ])
      const generalSettings = generalRes.data || generalRes || {}
      const emailSettings = emailRes.data || {}
      
      // Merge email settings with mapped field names. The test recipient is
      // not a setting: keep what was typed across the reload a save triggers.
      const email = {
        smtp_host: emailSettings.smtp_host,
        smtp_port: emailSettings.smtp_port,
        smtp_username: emailSettings.smtp_username,
        smtp_password: emailSettings.smtp_password,
        // Left undefined when the API said nothing, so a save does not overwrite it
        smtp_security: emailSettings.smtp_security
          ?? (emailSettings.smtp_tls == null ? undefined : (emailSettings.smtp_tls ? 'starttls' : 'none')),
        smtp_from_email: emailSettings.from_email,
        smtp_from_name: emailSettings.from_name,
        smtp_auth: emailSettings.smtp_auth !== false,
        smtp_content_type: emailSettings.smtp_content_type || 'html',
        // Authentication off is reported as 'none' by the API; derive the
        // highlighted method from it rather than from the stored default (#322)
        smtp_auth_method: emailSettings.smtp_auth === false ? 'none' : (emailSettings.smtp_auth_method || 'password'),
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
      }
      const keptSettings = initial ? takeKept('settings') : undefined
      if (initial) {
        Object.assign(keyOrigin.current, takeKept('keyOrigin') || {})
        if (takeKept('oauthDirty')) setOauthDirty(true)
      }
      setSettings(prev => {
        const pending = keepPending
          ? changedKeys(prev, savedBefore, [...bulkKeys(prev, savedBefore), ...EMAIL_KEYS]).filter((k) => !stored.includes(k))
          : []
        return { _testRecipient: prev._testRecipient, ...generalSettings, ...email, ...pick(prev, [...keep, ...pending]), ...keptSettings }
      })
      setSavedSettings({ ...generalSettings, ...email })
      setSavedEmail(email)
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

  // The settings carry no date: the last saves are read from the audit log, when readable.
  // Only an entry a save writes counts (a manual renewal run or an OAuth consent is no save).
  const loadSettingsLog = async () => {
    if (!hasPermission('read:audit')) return
    try {
      const res = await auditService.getLogs({ resource_type: 'settings', success: true, per_page: 25 })
      const saves = (Array.isArray(res?.data) ? res.data : []).filter((e) => SETTINGS_SAVE_ACTIONS.includes(e.action))
      setSettingsLog(saves.slice(0, 5))
    } catch (error) { reportSilentFailure('loadSettingsLog', error) }
  }

  const loadExpiryAlerts = async () => {
    try {
      const res = await settingsService.getExpiryAlerts()
      setExpiryAlerts(takeKept('expiry') ?? (res.data || res))
      setSavedExpiryAlerts(res.data || res)
    } catch (error) { reportSilentFailure('loadExpiryAlerts', error) }
  }

  const saveExpiryAlerts = async ({ quiet = false } = {}) => {
    setSaving(true)
    try {
      await settingsService.updateExpiryAlerts(expiryAlerts)
      setSavedExpiryAlerts(expiryAlerts)
      if (!quiet) showSuccess(t('common.saved'))
      return { ok: true }
    } catch (e) {
      if (!quiet) showError(e.message || t('common.saveFailed'))
      return { ok: false, message: e.message || t('common.saveFailed') }
    } finally {
      setSaving(false)
    }
  }

  const triggerExpiryCheck = async () => {
    try {
      const res = await settingsService.checkExpiryAlerts()
      const outcome = expiryCheckOutcome(res.data || res)
      if (outcome.skipped) showInfo(t('settings.expiryCheckSkipped'))
      else showSuccess(t('settings.expiryCheckResult', { count: outcome.count }))
    } catch (e) {
      showError(e.message || t('common.error'))
    }
  }

  const loadCAs = async () => {
    try {
      const data = await casService.getAll()
      setCas(data.data || [])
    } catch (error) { reportSilentFailure('loadCAs', error) }
  }

  // The space used and the ceiling warning, as the server counts them
  const loadBackupSchedule = async () => {
    try {
      const res = await settingsService.getBackupSchedule()
      setBackupSchedule(res?.data || {})
    } catch (error) { reportSilentFailure('loadBackupSchedule', error) }
  }

  const loadBackups = async (query = backupQuery, { withSchedule = true } = {}) => {
    if (withSchedule) loadBackupSchedule()
    try {
      const res = await systemService.listBackups(query)
      const data = res.data || res
      // New shape {items, meta}; tolerate the old flat array for safety.
      if (Array.isArray(data)) {
        setBackups(data)
        setBackupMeta({ total: data.length, pages: 1, page: 1 })
      } else {
        setBackups(data.items || [])
        setBackupMeta(data.meta || { total: 0, pages: 1, page: 1 })
      }
      setSelectedBackups([])
    } catch (error) { reportSilentFailure('loadBackups', error) }
  }

  const updateBackupQuery = (patch) => {
    const next = { ...backupQuery, ...patch }
    if (patch.sort && patch.sort !== urlBackupOrder) {
      const [key, dir] = patch.sort.split('_')
      backupSort.setSort({ key, asc: dir === 'asc' })
    }
    // Any change other than an explicit page jump resets to page 1.
    if (!('page' in patch)) next.page = 1
    setBackupQuery(next)
    loadBackups(next, { withSchedule: false })
  }

  // Back or a link that changes the order reads the archives again in it
  useEffect(() => {
    if (urlBackupOrder !== backupQuery.sort && hasPermission('admin:system')) updateBackupQuery({ sort: urlBackupOrder })
  }, [urlBackupOrder]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleSelectBackup = (filename) => {
    setSelectedBackups((prev) =>
      prev.includes(filename) ? prev.filter((f) => f !== filename) : [...prev, filename])
  }

  const toggleSelectAllBackups = () => {
    setSelectedBackups((prev) =>
      prev.length === backups.length ? [] : backups.map((b) => b.filename))
  }

  const handleBulkDeleteBackups = async () => {
    if (selectedBackups.length === 0) return
    const confirmed = await showConfirm(
      t('settings.backupBulkDeleteConfirm', { count: selectedBackups.length }),
      { title: t('settings.deleteBackup'), confirmText: t('common.delete'), variant: 'danger' })
    if (!confirmed) return
    setBackupBusy(true)
    try {
      const res = await systemService.bulkDeleteBackups(selectedBackups)
      showSuccess(t('settings.backupDeletedCount', { count: (res.data || res).deleted ?? selectedBackups.length }))
      loadBackups()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.backup'))
    } finally {
      setBackupBusy(false)
    }
  }

  const handleRunRetention = async () => {
    const confirmed = await showConfirm(t('settings.backupRunRetentionConfirm'),
      { title: t('settings.backupCleanupNow'), confirmText: t('settings.backupCleanupNow') })
    if (!confirmed) return
    setBackupBusy(true)
    try {
      const res = await systemService.runBackupRetention()
      const outcome = res.data || res
      showSuccess(t('settings.backupRetentionRemoved', { count: outcome.removed ?? 0 }))
      const notice = ceilingNotice(outcome, backupSchedule,
        { afterRetention: true, shared: backupMeta.storage === 'database' }, t)
      if (notice) showWarning(notice)
      loadBackups()
    } catch (error) {
      showError(error.message || t('common.error'))
    } finally {
      setBackupBusy(false)
    }
  }

  const handleClearBackupPassword = async () => {
    const confirmed = await showConfirm(t('settings.clearBackupPasswordConfirm'), {
      title: t('settings.clearBackupPassword'),
      confirmText: t('settings.clearBackupPassword'),
      variant: 'danger',
    })
    if (!confirmed) return
    setSaving(true)
    try {
      await settingsService.updateBulk({ clear_backup_password: true })
      showSuccess(t('settings.backupPasswordCleared'))
      await loadSettings({ keepPending: true })
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const loadHttpsInfo = async () => {
    try {
      const data = await systemService.getHttpsCertInfo()
      setHttpsInfo(data.data || {})
    } catch (error) { reportSilentFailure('loadHttpsInfo', error) }
  }

  const loadDbStats = async () => {
    try {
      const data = await systemService.getDatabaseStats()
      const stats = data.data || {}
      setDbStats({
        certificates: stats.counts?.certificates || 0,
        cas: stats.counts?.cas || 0,
        size_mb: stats.size_mb || null,
        last_optimized: stats.last_vacuum || null
      })
    } catch (error) { reportSilentFailure('loadDbStats', error) }
  }

  // SSO Functions
  const loadSsoProviders = async () => {
    setSsoLoading(true)
    try {
      const response = await ssoService.getProviders()
      setSsoProviders(response.data || [])
    } catch (error) { reportSilentFailure('loadSsoProviders', error) } finally {
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

  const handleSsoDelete = () => runDelete(async () => {
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
  })

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
    } catch (error) { reportSilentFailure('loadMscaConnections', error) } finally {
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
        showSuccess(t('messages.success.create.mscaConnection'))
      }
      setShowMscaModal(false)
      setEditingMsca(null)
      loadMscaConnections()
    } catch (error) {
      showError(error.message)
    }
  }

  const handleMscaDelete = () => runDelete(async () => {
    if (!mscaConfirmDelete) return
    try {
      await mscaService.delete(mscaConfirmDelete.id)
      showSuccess(t('messages.success.delete.mscaConnection'))
      setMscaConfirmDelete(null)
      loadMscaConnections()
    } catch (error) {
      showError(error.message)
    }
  })

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

  const handleMscaSyncCrl = async (conn) => {
    setMscaTesting(true)
    try {
      const response = await mscaService.syncCrl(conn.id)
      showSuccess(t('msca.crlSyncResult', {
        revoked: response.data?.revoked ?? 0,
        checked: response.data?.checked ?? 0
      }))
      loadMscaConnections()
    } catch (error) {
      showError(error.message || t('msca.crlSyncFailed'))
    } finally {
      setMscaTesting(false)
    }
  }

  const handleMscaPublishCrl = async (conn) => {
    setMscaTesting(true)
    try {
      await mscaService.publishCrl(conn.id)
      showSuccess(t('msca.publishCrlSuccess'))
    } catch (error) {
      showError(error.message || t('msca.publishCrlFailed'))
    } finally {
      setMscaTesting(false)
    }
  }

  const handleMscaInventorySync = async (conn) => {
    setMscaTesting(true)
    try {
      const res = await mscaService.inventorySync(conn.id)
      showSuccess(t('msca.inventorySyncResult', {
        imported: res.data?.imported ?? 0,
        completed: res.data?.completed ?? 0,
        skipped: res.data?.skipped ?? 0
      }))
      loadMscaConnections()
    } catch (error) {
      showError(error.message || t('msca.inventorySyncFailed'))
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
    } catch (error) { reportSilentFailure('loadWebhooks', error) } finally {
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

  const handleWebhookDelete = () => runDelete(async () => {
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
  })

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
    } catch (error) { reportSilentFailure('loadEncryptionStatus', error) }
    // Enabling or disabling encryption changes how the session key rotates
    loadSecretsStatus()
  }

  const handleEnableEncryption = async () => {
    setEncryptionLoading(true)
    try {
      const response = await settingsService.enableEncryption()
      showSuccess(t('settings.encryptionEnabled', {
        count: response?.data?.key_files_removed ?? 0,
      }))
      setShowEnableEncryptionModal(false)
      await loadEncryptionStatus()

      // CRITICAL: prompt the operator to back up the master key right now.
      // The plaintext key is only available in this response; once the user
      // leaves this page we lose the chance to surface it cleanly.
      const masterKey = response?.data?.master_key
      if (masterKey) {
        setBackupKeyMaterial(masterKey)
        setBackupKeyDownloaded(false)
        setShowBackupKeyModal(true)
      }
    } catch (error) {
      showError(error.message || t('settings.encryptionEnableFailed'))
    } finally {
      setEncryptionLoading(false)
    }
  }

  const handleDownloadMasterKey = () => {
    if (!backupKeyMaterial) return
    try {
      const blob = new Blob([backupKeyMaterial + '\n'], { type: 'application/octet-stream' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'ucm-master.key'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setBackupKeyDownloaded(true)
    } catch (e) {
      showError(t('settings.masterKeyDownloadFailed'))
    }
  }

  // Standalone backup (button in encryption status section, after enable).
  // Fetches the key from the server (admin already has FS access) and
  // triggers the same browser download as post-enable.
  const handleDownloadExistingMasterKey = async () => {
    try {
      const blob = await settingsService.downloadMasterKey()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'ucm-master.key'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      showSuccess(t('settings.masterKeyDownloaded'))
    } catch (e) {
      showError(e.message || t('settings.masterKeyDownloadFailed'))
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

  const handleEncryptRemainingKeys = async () => {
    const count = encryptionStatus?.unencrypted_count ?? 0
    const confirmed = await showConfirm(t('settings.encryptRemainingKeysConfirm', { count }), {
      title: t('settings.encryptRemainingKeys', { count }),
      confirmText: t('settings.encryptRemainingKeys', { count }),
    })
    if (!confirmed) return
    setEncryptionLoading(true)
    try {
      const res = await settingsService.encryptAllKeys()
      const data = res.data || res
      if (data.errors?.length) {
        showWarning(data.errors.join('\n'))
      } else {
        showSuccess(t('settings.encryptRemainingKeysDone', { count: data.encrypted ?? 0 }))
      }
      await loadEncryptionStatus()
    } catch (error) {
      showError(error.message || t('common.error'))
    } finally {
      setEncryptionLoading(false)
    }
  }

  const loadSecretsStatus = async () => {
    try {
      const response = await settingsService.getSecretsStatus()
      setSecretsStatus(response.data)
    } catch (error) { reportSilentFailure('loadSecretsStatus', error) }
  }

  const handleRotateSessionKey = async () => {
    const stored = secretsStatus?.session_secret?.rotation === 'database'
    const confirmed = await showConfirm(
      t(stored ? 'settings.rotateSessionKeyConfirmStored' : 'settings.rotateSessionKeyConfirmFile'), {
        title: t('settings.rotateSessionKey'),
        confirmText: t('settings.rotateSessionKey'),
      })
    if (!confirmed) return
    setSessionKeyLoading(true)
    try {
      const res = await settingsService.rotateSessionKey()
      const data = res.data || res
      showSuccess(t(data.mode === 'database' ? 'settings.rotateSessionKeyDoneStored' : 'settings.rotateSessionKeyDoneFile'))
      await loadSecretsStatus()
    } catch (error) {
      showError(error.message || t('common.error'))
      await loadSecretsStatus()
    } finally {
      setSessionKeyLoading(false)
    }
  }

  const handleRotateDataKey = async () => {
    const confirmed = await showConfirm(t('settings.rotateDataKeyConfirm'), {
      title: t('settings.rotateDataKey'),
      confirmText: t('settings.rotateDataKey'),
    })
    if (!confirmed) return
    setEncryptionLoading(true)
    try {
      const res = await settingsService.rotateDataKey()
      const data = res.data || res
      if (data.state === 'done') {
        showSuccess(t('settings.rotateDataKeyDone', { version: data.version }))
      } else {
        showWarning(t('settings.rotateDataKeyPending'))
      }
      await loadEncryptionStatus()
    } catch (error) {
      showError(error.message || t('common.error'))
      await loadEncryptionStatus()
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
    } catch (error) { reportSilentFailure('loadAnomalies', error) } finally {
      setAnomaliesLoading(false)
    }
  }

  // Syslog config
  const loadSyslogConfig = async () => {
    try {
      const response = await settingsService.getSyslogConfig()
      setSyslogConfig(takeKept('syslog') ?? (response.data || response))
      setSavedSyslog(response.data || response)
    } catch (error) { reportSilentFailure('loadSyslogConfig', error) }
  }

  const handleSaveSyslog = async ({ quiet = false } = {}) => {
    setSyslogSaving(true)
    try {
      await settingsService.updateSyslogConfig(syslogConfig)
      setSavedSyslog(syslogConfig)
      if (!quiet) showSuccess(t('settings.syslogSaved'))
      return { ok: true }
    } catch (error) {
      if (!quiet) showError(error.message || t('settings.syslogSaveFailed'))
      return { ok: false, message: error.message || t('settings.syslogSaveFailed') }
    } finally {
      setSyslogSaving(false)
    }
  }

  // The test sends to the saved forwarding; its result stays beside the button
  const handleTestSyslog = async () => {
    if (!savedSyslog.enabled || !savedSyslog.host) {
      setSyslogTestResult({ ok: false, text: t('settings.syslogTestOff') })
      return
    }
    setSyslogTesting(true)
    try {
      const response = await settingsService.testSyslog()
      const text = response.message || t('settings.syslogTestSuccess')
      setSyslogTestResult({ ok: true, text })
      showSuccess(text)
    } catch (error) {
      const text = error.message || t('settings.syslogTestFailed')
      setSyslogTestResult({ ok: false, text })
      showError(text)
    } finally {
      setSyslogTesting(false)
    }
  }

  const updateSyslogConfig = (key, value) => {
    clearFieldError(`syslog.${key}`)
    setSyslogTestResult(null)
    setSyslogConfig(prev => ({ ...prev, [key]: value }))
  }

  const loadMtlsSettings = async () => {
    setMtlsLoading(true)
    try {
      const response = await mtlsService.getSettings()
      setMtlsSettings(takeKept('mtls') ?? (response.data || {}))
      setSavedMtls(response.data || {})
    } catch (error) { reportSilentFailure('loadMtlsSettings', error) } finally {
      setMtlsLoading(false)
    }
  }

  const handleMtlsSave = async ({ quiet = false } = {}) => {
    setMtlsSaving(true)
    try {
      const response = await mtlsService.updateSettings({
        enabled: mtlsSettings.enabled,
        required: mtlsSettings.required,
        trusted_ca_id: mtlsSettings.trusted_ca_id || null,
      })
      const data = response.data || {}
      setMtlsSettings(prev => ({ ...prev, ...data }))
      setSavedMtls({ ...mtlsSettings, ...data })
      if (!quiet) showSuccess(t('settings.mtls.saved'))
      // A hot reload keeps the service up: only a real restart is awaited (#452)
      if (data.listener_reload === 'reloading') {
        showInfo(data.restart_message)
      } else if (data.needs_restart && !isDocker && data.listener_reload !== 'failed') {
        waitForRestart()
      } else if (data.restart_message) {
        showWarning(data.restart_message)
      }
      return { ok: true }
    } catch (error) {
      if (!quiet) showError(error.message || t('settings.mtls.saveFailed'))
      return { ok: false, message: error.message || t('settings.mtls.saveFailed') }
    } finally {
      setMtlsSaving(false)
    }
  }

  // Certificate Transparency
  const loadCtSettings = async () => {
    setCtLoading(true)
    try {
      const response = await settingsService.getCTSettings()
      setCtSettings(takeKept('ct') ?? (response.data || { enabled: false, auto_submit: false, log_urls: [] }))
      setSavedCt(response.data || { enabled: false, auto_submit: false, log_urls: [] })
    } catch (error) { reportSilentFailure('loadCtSettings', error) } finally {
      setCtLoading(false)
    }
  }

  const handleCtSave = async ({ quiet = false } = {}) => {
    setCtSaving(true)
    try {
      await settingsService.updateCTSettings(ctSettings)
      setSavedCt(ctSettings)
      if (!quiet) showSuccess(t('settings.ctSettingsUpdated'))
      return { ok: true }
    } catch (error) {
      if (!quiet) showError(error.message || t('settings.ctSettingsFailed'))
      return { ok: false, message: error.message || t('settings.ctSettingsFailed') }
    } finally {
      setCtSaving(false)
    }
  }

  const handleCtAddLogUrl = () => {
    const url = ctNewLogUrl.trim()
    if (!url) return
    setCtSettings(prev => ({ ...prev, log_urls: addCtLogUrl(prev.log_urls, url) }))
    setCtNewLogUrl('')
  }

  const handleCtRemoveLogUrl = (index) => {
    setCtSettings(prev => ({ ...prev, log_urls: removeCtLogUrl(prev.log_urls, index) }))
  }

  // Auto-renewal
  const loadAutoRenewalSettings = async () => {
    setArLoading(true)
    try {
      const response = await settingsService.getAutoRenewalSettings()
      if (response.data) {
        setArSettings(takeKept('ar') ?? response.data)
        setSavedAr(response.data)
      }
    } catch {
      // keep defaults silently
    } finally {
      setArLoading(false)
    }
  }

  const handleArSave = async ({ quiet = false } = {}) => {
    setArSaving(true)
    try {
      const response = await settingsService.updateAutoRenewalSettings(arSettings)
      if (response.data) setArSettings(response.data)
      setSavedAr(response.data || arSettings)
      if (!quiet) showSuccess(t('settings.autoRenewalSettingsUpdated'))
      return { ok: true }
    } catch (error) {
      if (!quiet) showError(error.message || t('settings.autoRenewalSettingsFailed'))
      return { ok: false, message: error.message || t('settings.autoRenewalSettingsFailed') }
    } finally {
      setArSaving(false)
    }
  }

  const handleArRunNow = async () => {
    setArRunning(true)
    setArRunResult(null)
    try {
      const response = await settingsService.runAutoRenewalNow()
      const stats = response.data || {}
      const done = t('settings.autoRenewalRunSuccess', {
        renewed: stats.renewed || 0,
        failed: stats.failed || 0,
      })
      showSuccess(done)
      const waiting = autoRenewalWaitingMessage(stats.waiting, t)
      if (waiting) showInfo(waiting)
      setArRunResult({ ok: !stats.failed, text: waiting ? `${done}. ${waiting}` : done })
    } catch (error) {
      setArRunResult({ ok: false, text: error.message || t('settings.autoRenewalRunFailed') })
      showError(error.message || t('settings.autoRenewalRunFailed'))
    } finally {
      setArRunning(false)
    }
  }

  // `quiet`: the save bar reports; `reload: false`: the save bar reloads once at the end
  const handleSave = async (section, { quiet = false, reload = true } = {}) => {
    setSaving(true)
    let restartMessage = null
    let ignoredKeys = []
    try {
      if (section === 'email') {
        const targets = smtpSecretTargets(savedEmail, settings)
        if (secretRequiredForTarget(targets.password) || secretRequiredForTarget(targets.oauth)) {
          if (!quiet) showError(t('common.secretRequiredForTarget'))
          return { ok: false, message: t('common.secretRequiredForTarget') }
        }
        // Email settings go to a different endpoint with mapped field names
        await settingsService.updateEmailSettings({
          smtp_host: settings.smtp_host,
          smtp_port: settings.smtp_port,
          smtp_username: settings.smtp_auth_method !== 'none' ? settings.smtp_username : '',
          smtp_password: settings.smtp_auth_method === 'password' ? settings.smtp_password : '',
          smtp_security: settings.smtp_security,
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
        const response = await settingsService.updateBulk(
          withoutAdminOnly(settings, hasPermission('admin:settings')))
        restartMessage = response?.data?.restart_message
        ignoredKeys = response?.data?.ignored_keys || []
      }
      if (!quiet) showSuccess(t('messages.success.update.settings'))
      if (ignoredKeys.length) {
        showWarning(t('settings.adminKeysIgnored', { keys: ignoredKeys.join(', ') }))
      }
      if (restartMessage) showWarning(restartMessage)
      if (section === 'email') setOauthDirty(false)
      if (settings.timezone) setAppTimezone(settings.timezone)
      if (settings.date_format) setDateFormat(settings.date_format)
      if (settings.show_time !== undefined) setShowTime(settings.show_time !== 'false' && settings.show_time !== false)
      if (reload) {
        // The other route's drafts were not stored: they survive the reload
        await loadSettings({ keepPending: true, stored: section === 'email' ? EMAIL_KEYS : bulkKeys(settings, savedSettings) })
        if (section === 'backup') await loadBackupSchedule()
        setSavedVersion((v) => v + 1)
      }
      return { ok: true }
    } catch (error) {
      if (!quiet) showError(error.message || t('messages.errors.updateFailed.settings'))
      return { ok: false, message: error.message || t('messages.errors.updateFailed.settings') }
    } finally {
      setSaving(false)
    }
  }

  // The sender is often an unattended mailbox: default to the signed-in user.
  const defaultTestRecipient = user?.email || settings.smtp_from_email

  const handleTestEmail = async () => {
    const testEmail = settings._testRecipient || defaultTestRecipient
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
      // `data.error` is a BOOLEAN in UCM's error bodies (utils/response.py sets
      // `'error': True`), so it may only be read as text when it really is one —
      // same guard as apiClient.buildErrorMessage. Without it a body without
      // `message` yields `true`, which React renders as an empty banner.
      const backendError = typeof error?.data?.error === 'string' ? error.data.error : null
      const msg = error?.data?.message || backendError || error.message || t('messages.errors.email.testFailed')
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
      if (typeof preset.smtp_use_ssl === 'boolean' || typeof preset.smtp_use_tls === 'boolean') {
        updateSetting('smtp_security', preset.smtp_use_ssl ? 'ssl' : (preset.smtp_use_tls ? 'starttls' : 'none'))
      }
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
        try { bc && bc.close() } catch { /* the channel is already gone */ }
        if (ok) {
          showSuccess(t('settings.smtpOauthSuccess'))
          setOauthDirty(false)
          await loadSettings({ keepPending: true })
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
          await loadSettings({ keepPending: true })
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
      loadSettings({ keepPending: true })
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    }
  }

  const closeBackupModal = () => {
    setShowBackupModal(false)
    setBackupPassword('')
    setBackupReady(null)
  }

  const showBackupEnd = useCallback((job) => {
    if (job.state === 'succeeded' && job.result?.data) {
      setBackupReady(job.result.data)
      setShowBackupModal(true)
      showSuccess(t('messages.success.backup.ready'))
      const notice = ceilingNotice(job.result.data, backupSchedule, {}, t)
      if (notice) showWarning(notice)
      loadBackups()
    } else if (job.state === 'cancelled') {
      setShowBackupModal(false)
      showWarning(t('settings.backupCancelled'))
    } else if (job.reason === 'executor_lost' || job.reason === 'not_taken') {
      showError(t('settings.backupLost'))
    } else {
      showError(job.result?.message || t('messages.errors.backup.createFailed'))
    }
  }, [backupSchedule, showSuccess, showWarning, showError, t]) // eslint-disable-line react-hooks/exhaustive-deps

  const followBackup = useCallback(async (job) => {
    try {
      showBackupEnd(await followBackupJob(job))
    } catch {
      showError(t('messages.errors.backup.createFailed'))
    }
  }, [followBackupJob, showBackupEnd, showError, t])

  // After a reload: a backup still running is shown and followed again, once per mount
  const backupEnd = useRef(showBackupEnd)
  backupEnd.current = showBackupEnd
  const canBackup = hasPermission('admin:system')
  useEffect(() => {
    if (!canBackup) return undefined
    let gone = false
    resumeBackupJob('backup').then((job) => {
      if (!gone && job) backupEnd.current(job)
    }).catch(() => {})
    return () => { gone = true }
  }, [resumeBackupJob, canBackup])
  useEffect(() => {
    if (backupRunning) setShowBackupModal(true)
  }, [backupRunning])

  const handleBackup = async () => {
    const problem = backupPasswordProblem(backupPassword, t)
    if (problem) {
      showError(problem)
      return
    }
    
    setBackupLoading(true)
    try {
      const response = await systemService.backup(backupPassword)
      const job = acceptedJob(response)
      if (job) {
        setBackupPassword('')
        setBackupLoading(false)
        await followBackup(job)
        return
      }
      if (response.data) {
        const blob = await systemService.downloadBackup(response.data.filename)
        downloadBlob(blob, response.data.filename)
        showSuccess(t('messages.success.backup.created'))
        const notice = ceilingNotice(response.data, backupSchedule, {}, t)
        if (notice) showWarning(notice)
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

  const handleCancelBackup = async () => {
    try {
      await cancelBackupJob()
    } catch {
      showError(t('settings.backupCancelFailed'))
    }
  }

  const backupProgress = backupRunning && backupJob?.progress?.total
    ? t('settings.backupProgress', { done: backupJob.progress.done || 0, total: backupJob.progress.total })
    : t('settings.backupStarting')

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
    // Requests answered after the restore revoked the sessions get 401: the report stays first
    holdSignOut()
    holdingSignOut.current = true
    try {
      setRestoreProgress(0)
      const result = await systemService.restore(restoreFile, restorePassword, {
        onProgress: (loaded, total) => setRestoreProgress(Math.floor((loaded / total) * 100)),
      })
      // Restored after the page was left: the session is revoked, the reload leads to sign-in
      if (!mounted.current) {
        window.location.reload()
        return
      }
      setRestorePassword('')
      setRestoreFile(null)
      // Past the bounded wait: the job is followed in the dialog, its report shown at the end
      setBackupLoading(false)
      setRestoreProgress(null)
      if (await restoreJob.start(result)) return
      setShowRestoreModal(false)
      setRestoreReport(result.data || {})
    } catch (error) {
      holdingSignOut.current = false
      holdSignOut(false)
      showRestoreError(error.message || t('messages.errors.backup.restoreFailed'), error.status)
    } finally {
      setBackupLoading(false)
      setRestoreProgress(null)
    }
  }

  const handleCancelRestore = async () => {
    try {
      await restoreJob.cancel()
    } catch (error) {
      showError(error.message || t('settings.restoreCancelFailed'))
    }
  }

  // A restore counts its rows: a percentage, the total known once the archive is read
  const restorePercent = jobPercent(restoreJob.job?.progress)
  const restoreJobProgress = restorePercent !== null
    ? t('settings.restoreJobPercent', { percent: restorePercent })
    : t('settings.restoreJobStarting')

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
      const res = await systemService.resetDatabase()
      await afterDatabaseReset(res, { t, showConfirm, showSuccess, reload: () => window.location.reload() })
    } catch (error) {
      showError(error.message || t('messages.errors.database.resetFailed'))
    }
  }

  // After an HTTPS change: a hot reload keeps the service up, so no restart is awaited (#452)
  const afterHttpsChange = (data, doneKey, onRestart = waitForRestart) => {
    if (data?.listener_reload === 'failed') {
      showWarning(t('settings.httpsReloadFailed', { error: data.error || '' }))
      loadHttpsInfo()
    } else if (data?.listener_reload === 'reloading') {
      showSuccess(t('settings.httpsReloading'))
      setTimeout(loadHttpsInfo, HTTPS_RELOAD_SETTLE_MS)
    } else {
      showSuccess(t(doneKey))
      onRestart()
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
      afterHttpsChange(response.data, 'messages.success.https.applied')
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
      afterHttpsChange(response.data, 'messages.success.https.regenerated')
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
  // A section's fields record which section a key belongs to, for the marks and the errors
  const clearFieldError = (key) => setFieldErrors((prev) => {
    if (!(key in prev)) return prev
    const next = { ...prev }
    delete next[key]
    return next
  })
  const updateSettingFrom = (sectionId) => (key, value) => {
    keyOrigin.current[key] = sectionId
    clearFieldError(key)
    updateSetting(key, value)
  }

  // Parts of the save bar: one per route of today's API, each with its draft and its section
  const bulkChanged = changedKeys(settings, savedSettings, bulkKeys(settings, savedSettings))
  const emailChanged = changedKeys(settings, savedSettings, EMAIL_KEYS)
  const pageParts = [
    { key: 'email', section: 'email', count: emailChanged.length,
      save: () => handleSave('email', { quiet: true, reload: false }) },
    { key: 'expiry', section: 'email',
      count: changedKeys(expiryAlerts, savedExpiryAlerts, Object.keys({ ...savedExpiryAlerts, ...expiryAlerts })).length,
      save: () => saveExpiryAlerts({ quiet: true }), reset: () => setExpiryAlerts(savedExpiryAlerts) },
    { key: 'syslog', section: 'audit',
      count: changedKeys(syslogConfig, savedSyslog, Object.keys({ ...savedSyslog, ...syslogConfig })).length,
      save: () => handleSaveSyslog({ quiet: true }), reset: () => setSyslogConfig(savedSyslog) },
    { key: 'mtls', section: 'security', count: changedKeys(mtlsSettings, savedMtls, MTLS_KEYS).length,
      save: () => handleMtlsSave({ quiet: true }), reset: () => setMtlsSettings(savedMtls) },
    { key: 'ct', section: 'ct', count: changedKeys(ctSettings, savedCt, Object.keys({ ...savedCt, ...ctSettings })).length,
      save: () => handleCtSave({ quiet: true }), reset: () => setCtSettings(savedCt) },
    { key: 'ar', section: 'autoRenewal', count: changedKeys(arSettings, savedAr, Object.keys({ ...savedAr, ...arSettings })).length,
      save: () => handleArSave({ quiet: true }), reset: () => setArSettings(savedAr) },
  ]
  // The bulk route stores every section's keys at once: its count goes to each origin section
  const bulkBySection = {}
  for (const key of bulkChanged) {
    const sectionId = keyOrigin.current[key] || 'general'
    bulkBySection[sectionId] = (bulkBySection[sectionId] || 0) + 1
  }
  const allParts = [
    ...Object.entries(bulkBySection).map(([sectionId, count]) => ({ key: `bulk:${sectionId}`, section: sectionId, count, bulk: true })),
    ...pageParts,
    ...parts.list,
  ].filter((part) => part.count > 0)
  const pendingCount = allParts.reduce((sum, part) => sum + part.count, 0)
  const pendingSections = [...new Set(allParts.map((part) => part.section))]
  // Each changed field with its section, for the save bar to name it
  const changedOf = (prefix, now, saved, keys) => changedKeys(now, saved, keys).map((k) => `${prefix}.${k}`)
  const pendingFields = [
    ...bulkChanged.map((key) => ({ key, section: keyOrigin.current[key] || 'general' })),
    ...emailChanged.map((key) => ({ key, section: 'email' })),
    ...changedOf('expiry', expiryAlerts, savedExpiryAlerts, Object.keys({ ...savedExpiryAlerts, ...expiryAlerts })).map((key) => ({ key, section: 'email' })),
    ...changedOf('syslog', syslogConfig, savedSyslog, Object.keys({ ...savedSyslog, ...syslogConfig })).map((key) => ({ key, section: 'audit' })),
    ...changedOf('mtls', mtlsSettings, savedMtls, MTLS_KEYS).map((key) => ({ key, section: 'security' })),
    ...changedOf('ct', ctSettings, savedCt, Object.keys({ ...savedCt, ...ctSettings })).map((key) => ({ key, section: 'ct' })),
    ...changedOf('ar', arSettings, savedAr, Object.keys({ ...savedAr, ...arSettings })).map((key) => ({ key, section: 'autoRenewal' })),
    ...parts.list.filter((part) => part.count > 0).map((part) => ({ key: part.key, section: part.section })),
  ]

  const resetAll = () => {
    setSettings((prev) => ({ ...savedSettings, _testRecipient: prev._testRecipient }))
    for (const part of [...pageParts, ...parts.list]) if (part.count > 0) part.reset?.()
    keyOrigin.current = {}
    setSectionErrors({})
    setFieldErrors({})
    setOauthDirty(false)
    saveState.current?.focus()
  }

  // Each part goes to its own route; a failed one keeps its draft and names its section
  const saveAll = async () => {
    if (!pendingCount || savingAll) return
    const syslogChanged = changedKeys(syslogConfig, savedSyslog, Object.keys({ ...savedSyslog, ...syslogConfig }))
    const arChanged = changedKeys(arSettings, savedAr, Object.keys({ ...savedAr, ...arSettings }))
    // A changed syslog part checks its server and port together: turning it on needs both
    const problems = fieldProblems({ settings, syslog: syslogConfig, ar: arSettings }, [
      ...bulkChanged, ...emailChanged,
      ...(syslogChanged.length ? ['syslog.host', 'syslog.port'] : []),
      ...arChanged.map((k) => `ar.${k}`),
    ])
    const bad = Object.keys(problems)
    if (bad.length) {
      setFieldErrors(Object.fromEntries(bad.map((k) => [k, t(problems[k].key, problems[k].values)])))
      setAnnounce(t('sectioned.fieldsToCorrect', { count: bad.length }))
      setInvalidFocus((n) => n + 1)
      return
    }
    setAnnounce('')
    setSavingAll(true)
    const errors = {}
    const keep = []
    try {
      for (const part of allParts.filter((p) => !p.bulk)) {
        const result = await part.save()
        if (!result?.ok) {
          errors[part.section] = result?.message || t('messages.errors.updateFailed.settings')
          if (part.key === 'email') keep.push(...emailChanged)
        }
      }
      if (bulkChanged.length) {
        const result = await handleSave('bulk', { quiet: true, reload: false })
        if (!result.ok) {
          for (const sectionId of Object.keys(bulkBySection)) errors[sectionId] = result.message
          keep.push(...bulkChanged)
        } else if (bulkBySection.backup) {
          await loadBackupSchedule()
        }
      }
      if (bulkChanged.length || emailChanged.length) await loadSettings({ keep })
      setSectionErrors(errors)
      setSavedVersion((v) => v + 1)
      loadSettingsLog()
      const failed = Object.keys(errors)
      if (failed.length) {
        const labels = failed.map((id) => t(BASE_SETTINGS_CATEGORIES.find((c) => c.id === id)?.labelKey || id))
        showError(t('sectioned.saveFailedToast', { sections: labels.join(', ') }))
        jumpToSection(failed[0])
      } else {
        showSuccess(t('sectioned.savedToast'))
        saveState.current?.focus()
      }
    } finally {
      setSavingAll(false)
    }
  }

  // Enter in a field of a section saves, as in a form; a field that takes Enter for itself
  // (tags, a list to add to) prevents it first, and a dialog's fields are not on the page
  const NO_ENTER_SAVE = ['checkbox', 'radio', 'button', 'submit', 'reset', 'file', 'range', 'search', 'color']
  const saveOnEnter = (e) => {
    const field = e.target
    if (e.key !== 'Enter' || e.defaultPrevented || e.isComposing || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return
    if (field.tagName !== 'INPUT' || NO_ENTER_SAVE.includes(field.type) || !e.currentTarget.contains(field)) return
    e.preventDefault()
    saveAll()
  }

  // A save stopped by a field out of bounds: the first such field takes the focus
  useEffect(() => {
    if (!invalidFocus) return
    const field = document.querySelector('#settings-form [aria-invalid="true"]')
    field?.scrollIntoView?.({ block: 'center' })
    field?.focus({ preventScroll: true })
  }, [invalidFocus])

  // Leaving keeps the draft for the return (no question); a reload or a close asks the browser
  useUnloadGuard(pendingCount > 0)
  const pageCounts = Object.fromEntries(pageParts.map((part) => [part.key, part.count]))
  useEffect(() => {
    if (loading) return
    const draft = {
      settings: pick(settings, [...bulkChanged, ...emailChanged]),
      keyOrigin: pick(keyOrigin.current, bulkChanged),
      oauthDirty: oauthDirty || undefined,
      expiry: pageCounts.expiry ? expiryAlerts : undefined,
      syslog: pageCounts.syslog ? syslogConfig : undefined,
      mtls: pageCounts.mtls ? mtlsSettings : undefined,
      ct: pageCounts.ct ? ctSettings : undefined,
      ar: pageCounts.ar ? arSettings : undefined,
    }
    // A part whose route has not answered yet keeps what it had left
    for (const [name, value] of Object.entries(kept.current || {})) if (draft[name] === undefined) draft[name] = value
    const pending = bulkChanged.length + emailChanged.length + Object.values(pageCounts).reduce((a, b) => a + b, 0)
    keepDraft(SETTINGS_DRAFT, pending || Object.keys(kept.current || {}).length ? draft : null)
  })

  // Render content for each category
  const renderCategoryContent = (selectedCategory) => {
    switch (selectedCategory) {
      case 'general':
        return (
          <GeneralSection
            settings={settings}
            fieldErrors={fieldErrors}
            updateSetting={updateSettingFrom('general')}
            handleSave={handleSave}
            saving={saving}
            canWrite={canWrite}
            hasPermission={hasPermission}
            savedVersion={savedVersion}
          />
        )

      case 'appearance':
        return <AppearanceSettings />

      case 'email':
        return (
          <EmailSection
            settings={settings}
            fieldErrors={fieldErrors}
            savedEmail={savedEmail}
            updateSetting={updateSettingFrom('email')}
            handleSave={handleSave}
            saving={saving}
            canWrite={canWrite}
            isMobile={isMobile}
            emailTestResult={emailTestResult}
            emailTesting={emailTesting}
            handleTestEmail={handleTestEmail}
            defaultTestRecipient={defaultTestRecipient}
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
            fieldErrors={fieldErrors}
            updateSetting={updateSettingFrom('security')}
            handleSave={handleSave}
            saving={saving}
            hasPermission={hasPermission}
            encryptionStatus={encryptionStatus}
            setShowEnableEncryptionModal={setShowEnableEncryptionModal}
            setShowDisableEncryptionModal={setShowDisableEncryptionModal}
            handleDownloadExistingMasterKey={handleDownloadExistingMasterKey}
            handleEncryptRemainingKeys={handleEncryptRemainingKeys}
            handleRotateDataKey={handleRotateDataKey}
            encryptionLoading={encryptionLoading}
            secretsStatus={secretsStatus}
            handleRotateSessionKey={handleRotateSessionKey}
            sessionKeyLoading={sessionKeyLoading}
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
            fieldErrors={fieldErrors}
            updateSetting={updateSettingFrom('backup')}
            handleSave={handleSave}
            saving={saving}
            hasPermission={hasPermission}
            backups={backups}
            backupMeta={backupMeta}
            backupSchedule={backupSchedule}
            backupQuery={backupQuery}
            updateBackupQuery={updateBackupQuery}
            selectedBackups={selectedBackups}
            toggleSelectBackup={toggleSelectBackup}
            toggleSelectAllBackups={toggleSelectAllBackups}
            handleBulkDeleteBackups={handleBulkDeleteBackups}
            handleRunRetention={handleRunRetention}
            backupBusy={backupBusy}
            setShowBackupModal={setShowBackupModal}
            backupRunning={backupRunning}
            setShowRestoreModal={setShowRestoreModal}
            setRestoreFile={setRestoreFile}
            handleDownloadBackup={handleDownloadBackup}
            handleDeleteBackup={handleDeleteBackup}
            handleClearBackupPassword={handleClearBackupPassword}
            clearBackupSelection={() => setSelectedBackups([])}
          />
        )
      case 'audit':
        return (
          <AuditSection
            settings={settings}
            fieldErrors={fieldErrors}
            updateSetting={updateSettingFrom('audit')}
            handleSave={handleSave}
            saving={saving}
            hasPermission={hasPermission}
            syslogConfig={syslogConfig}
            updateSyslogConfig={updateSyslogConfig}
            syslogSaving={syslogSaving}
            syslogTesting={syslogTesting}
            syslogTestResult={syslogTestResult}
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
            onUnbindHttpsCert={async () => {
              try {
                await systemService.unbindHttpsCert()
                showSuccess(t('settings.httpsUnbindDone'))
                loadHttpsInfo()
              } catch (err) {
                showError(err.message)
              }
            }}
          />
        )
      case 'updates':
        return <UpdatesSection />
      case 'scheduler':
        return <SchedulerSection hasPermission={hasPermission} />
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
      case 'deploy':
        return <DeploySection />
      case 'autoRenewal':
        return (
          <AutoRenewalSection
            arSettings={arSettings}
            setArSettings={(next) => { clearFieldError('ar.days_before_expiry'); setArSettings(next) }}
            fieldErrors={fieldErrors}
            arLoading={arLoading}
            arSaving={arSaving}
            arRunning={arRunning}
            handleArSave={handleArSave}
            handleArRunNow={handleArRunNow}
            arRunResult={arRunResult}
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
            handleMscaSyncCrl={handleMscaSyncCrl}
            handleMscaPublishCrl={handleMscaPublishCrl}
            handleMscaInventorySync={handleMscaInventorySync}
            handleMscaCaControl={setMscaCaControl}
            setMscaConfirmDelete={setMscaConfirmDelete}
            hasPermission={hasPermission}
          />
        )
      case 'adConnector':
        return <AdConnectorSection hasPermission={hasPermission} />
      case 'xcepWstep':
        return <XcepWstepSection hasPermission={hasPermission} />
      case 'about':
        return <AboutSection />

      default:
        return null
    }
  }

  // Sections in the order of the table of contents (permission-gated ones hidden from other roles)
  const allowed = SETTINGS_CATEGORIES.filter(cat => !cat.permission || [].concat(cat.permission).some(hasPermission))
  const sections = SETTINGS_GROUPS.flatMap(g => g.ids)
    .map(id => allowed.find(cat => cat.id === id))
    .filter(Boolean)
    .map(cat => ({ id: cat.id, label: t(cat.labelKey), description: t(cat.descKey), icon: SECTION_ICONS[cat.id] }))
  const head = (bar) => (
    <PageHead title={t('common.settings')} total={t('sectioned.sectionCount', { count: sections.length })} intent={t('shell.moduleDesc.settings')} bar={bar} />
  )

  if (loading) {
    return (
      <Zone testId="settings-page">
        {head()}
        <div className="scroll-view" id="view-scroll"><SkeletonPanel label={t('settings.loadingSettings')} /></div>
      </Zone>
    )
  }

  const flags = {}
  for (const id of pendingSections) flags[id] = 'modified'
  for (const id of Object.keys(sectionErrors)) flags[id] = 'error'
  for (const key of Object.keys(fieldErrors)) flags[fieldSection(key)] = 'error'
  const sectionLabel = (id) => sections.find(s => s.id === id)?.label || id
  const lastSave = settingsLog?.[0]
  // States the section headers carry: certificate type of HTTPS, experimental Microsoft CA
  const sectionAside = {
    https: httpsInfo?.type ? (
      <Pill tone={httpsInfo.type === 'CA-Signed' ? 'good' : httpsInfo.type === 'Self-Signed' ? 'warn' : 'muted'}
        label={HTTPS_TYPES[httpsInfo.type] ? t(HTTPS_TYPES[httpsInfo.type]) : httpsInfo.type} />
    ) : null,
    microsoftCA: <Pill tone="warn" icon="sparkles" label={t('common.experimental')} />,
  }
  // One bar at a time, so its ids stay unique; without it the announcement stays in the form
  const saveBar = (canWrite('settings') || pendingCount > 0) && (
    <SettingsSaveBar
      head={!phone}
      stateRef={saveState}
      dirty={pendingCount > 0}
      count={pendingCount}
      sections={pendingSections.map(sectionLabel)}
      pending={changedLabels(pendingFields, t, sectionLabel)}
      failed={pendingCount ? Object.keys(sectionErrors).map(sectionLabel) : []}
      lastSaved={lastSave ? { at: formatDate(lastSave.timestamp, { time: true }), by: lastSave.username } : null}
      saving={savingAll}
      onReset={resetAll}
      onSave={saveAll}
      announce={announce}
    />
  )

  return (
    <>
      {reconnecting && (
        <ServiceReconnectOverlay status={reconnectStatus} attempt={attempt} countdown={countdown} onCancel={cancel} />
      )}
      {/* A section's inspector (the scheduler's tasks) is drawn where the zone draws its dock */}
      <DockSlotProvider>
      <Zone testId="settings-page" dock={<DockSlot />}>
        {head(phone ? null : saveBar)}
        <SavePartsContext.Provider value={parts.api}>
          <SettingsLayout
            toc={(
              <SettingsToc label={t('settings.tocLabel')} sections={sections} flags={flags} current={selectedCategory}
                hrefFor={(id) => (id === 'general' ? '/settings' : `/settings?tab=${id}`)} onJump={handleCategoryChange} />
            )}
            history={settingsLog && <SettingsHistory entries={settingsLog} />}
            onKeyDown={saveOnEnter}
          >
            <SettingsJump sections={sections} current={selectedCategory} onJump={handleCategoryChange} />
            {sections.map(section => (
              <SettingsFrame key={section.id} id={section.id} label={section.label} desc={section.description}
                aside={sectionAside[section.id]} error={sectionErrors[section.id]} wide={WIDE_SECTIONS.has(section.id)}>
                {renderCategoryContent(section.id)}
              </SettingsFrame>
            ))}
            {!saveBar ? (
              <p className="sr-only" id="settings-announce" role="status" aria-live="polite">{announce}</p>
            ) : phone && saveBar}
          </SettingsLayout>
        </SavePartsContext.Provider>
      </Zone>
      </DockSlotProvider>

      {/* Backup: the password, then the running backup, then its archive to download */}
      {showBackupModal && (
        <BackupDialog running={backupRunning} progress={backupProgress} job={backupJob} ready={backupReady}
          password={backupPassword} setPassword={setBackupPassword} problem={backupPasswordProblem(backupPassword, t)}
          loading={backupLoading} onClose={closeBackupModal} onCreate={handleBackup} onCancelJob={handleCancelBackup}
          onDownload={handleDownloadBackup} />
      )}

      {/* Restore: the password, then the running restore, or the sign-in its end asks for */}
      {showRestoreModal && (
        <RestoreDialog job={restoreJob} uncancellable={UNCANCELLABLE_PHASES.includes(restoreJob.job?.phase)} progress={restoreJobProgress}
          file={restoreFile} password={restorePassword} setPassword={setRestorePassword} loading={backupLoading}
          uploadLabel={restoreProgress !== null && restoreProgress < 100 ? t('settings.restoreUploading', { percent: restoreProgress }) : t('settings.restoring')}
          onClose={() => {
            // Closed on "sign in again": every call now answers 401, which must lead to the sign-in
            if (restoreJob.signInNeeded) releaseSignOut()
            setShowRestoreModal(false); setRestorePassword(''); setRestoreFile(null)
          }}
          onCancel={() => { setShowRestoreModal(false); setRestorePassword(''); setRestoreFile(null) }}
          onRestore={handleRestoreBackup} onCancelJob={handleCancelRestore}
          onSignIn={() => {
            // Back to this tab after the sign-in: its report is shown there
            releaseSignOut(); window.location.href = loginUrl('/settings', '?tab=backup')
          }} />
      )}

      <RestoreReport data={restoreReport} onClose={() => setRestoreReport(null)} />

      {/* SSO Provider Modal */}
      <AtlModal
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
      </AtlModal>

      {/* SSO Delete Confirmation */}
      <AtlConfirmModal
        open={!!ssoConfirmDelete}
        onClose={() => setSsoConfirmDelete(null)}
        onConfirm={handleSsoDelete}
        title={t('sso.deleteTitle')}
        message={t('sso.deleteConfirm', { name: ssoConfirmDelete?.name })}
        confirmLabel={t('common.delete')}
        variant="danger"
        loading={deleting}
      />

      {/* Webhook Modal */}
      <AtlModal
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
      </AtlModal>

      {/* Webhook Delete Confirmation */}
      <AtlConfirmModal
        open={!!webhookConfirmDelete}
        onClose={() => setWebhookConfirmDelete(null)}
        onConfirm={handleWebhookDelete}
        title={t('webhooks.deleteTitle')}
        message={t('webhooks.deleteConfirm', { name: webhookConfirmDelete?.name })}
        confirmLabel={t('common.delete')}
        variant="danger"
        loading={deleting}
      />

      {/* Microsoft CA Connection Modal */}
      <AtlModal
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
      </AtlModal>

      {/* Microsoft CA Delete Confirmation */}
      <AtlConfirmModal
        open={!!mscaConfirmDelete}
        onClose={() => setMscaConfirmDelete(null)}
        onConfirm={handleMscaDelete}
        title={t('common.confirmDelete')}
        message={t('msca.deleteConfirm')}
        confirmLabel={t('common.delete')}
        variant="danger"
        loading={deleting}
      />

      {/* Microsoft CA Control Panel (pending requests + health) */}
      <MscaCaControlModal
        connection={mscaCaControl}
        open={!!mscaCaControl}
        onClose={() => setMscaCaControl(null)}
      />

      <EnableEncryptionDialog
        open={showEnableEncryptionModal}
        loading={encryptionLoading}
        onConfirm={handleEnableEncryption}
        onClose={() => setShowEnableEncryptionModal(false)}
      />

      <AtlConfirmModal
        open={showDisableEncryptionModal}
        onClose={() => setShowDisableEncryptionModal(false)}
        onConfirm={handleDisableEncryption}
        title={t('settings.disableEncryption')}
        message={t('settings.disableEncryptionConfirm')}
        confirmLabel={t('settings.disableEncryption')}
        variant="danger"
        loading={encryptionLoading}
      />

      {/* The master key, shown once after enabling: downloaded and its storage confirmed before it closes */}
      <MasterKeyBackupDialog
        open={showBackupKeyModal}
        downloaded={backupKeyDownloaded}
        onDownload={handleDownloadMasterKey}
        onDone={() => {
          setShowBackupKeyModal(false)
          setBackupKeyMaterial(null)
          setBackupKeyDownloaded(false)
        }}
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
                afterHttpsChange(response.data, 'messages.success.https.applied',
                  () => setTimeout(() => window.location.reload(), 3000))
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
        filters={{ status: ['valid', 'expiring'], has_private_key: true }}
      />
    </>
  )
}
