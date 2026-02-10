/**
 * Dashboard Page - Live Operational Dashboard with WebSocket
 * Real-time updates via WebSocket events
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { 
  ShieldCheck, Certificate, ClockCounterClockwise, Clock,
  Plus, ArrowsClockwise, ListChecks, Gear, CaretRight, 
  User, Globe, SignIn, SignOut, Trash, PencilSimple, 
  UploadSimple, Key, Warning, WifiHigh, Heartbeat, Database, Lightning,
  SlidersHorizontal, Eye, EyeSlash, X
} from '@phosphor-icons/react'
import { Card, Button, Badge, LoadingSpinner, Logo, Modal } from '../components'
import { CertificateTrendChart, StatusPieChart } from '../components/DashboardChart'
import { dashboardService, certificatesService, acmeService } from '../services'
import { useNotification } from '../contexts'
import { useWebSocket, EventType } from '../hooks'
import { formatRelativeTime } from '../lib/ui'

// Default widgets configuration - names are i18n keys
const DEFAULT_WIDGETS = [
  { id: 'stats', nameKey: 'dashboard.widgetStatistics', visible: true },
  { id: 'charts', nameKey: 'dashboard.widgetChartsAnalytics', visible: true },
  { id: 'system', nameKey: 'dashboard.widgetSystemStatus', visible: true },
  { id: 'expiring', nameKey: 'dashboard.widgetExpiringCertificates', visible: true },
  { id: 'activity', nameKey: 'dashboard.widgetRecentActivity', visible: true },
  { id: 'certs', nameKey: 'dashboard.widgetRecentCertificates', visible: true },
  { id: 'cas', nameKey: 'dashboard.widgetCertificateAuthorities', visible: true },
  { id: 'acme', nameKey: 'dashboard.widgetAcmeAccounts', visible: true },
]

// Load widget preferences from localStorage
const loadWidgetPrefs = () => {
  try {
    const saved = localStorage.getItem('ucm-dashboard-widgets')
    if (saved) {
      const parsed = JSON.parse(saved)
      // Merge with defaults to handle new widgets
      return DEFAULT_WIDGETS.map(w => ({
        ...w,
        visible: parsed.find(p => p.id === w.id)?.visible ?? w.visible,
        order: parsed.findIndex(p => p.id === w.id)
      })).sort((a, b) => (a.order >= 0 ? a.order : 999) - (b.order >= 0 ? b.order : 999))
    }
  } catch {}
  return DEFAULT_WIDGETS
}

// Save widget preferences to localStorage
const saveWidgetPrefs = (widgets) => {
  localStorage.setItem('ucm-dashboard-widgets', JSON.stringify(widgets.map(w => ({ id: w.id, visible: w.visible }))))
}

// Action icons mapping
const actionIcons = {
  login_success: SignIn,
  login_failed: SignIn,
  logout: SignOut,
  create: Plus,
  update: PencilSimple,
  delete: Trash,
  revoke: ClockCounterClockwise,
  export: UploadSimple,
  import: UploadSimple,
  sign: Key,
  default: ClockCounterClockwise
}

export default function DashboardPage() {
  const { t } = useTranslation()
  const { showError } = useNotification()
  const navigate = useNavigate()
  
  const [stats, setStats] = useState(null)
  const [recentCerts, setRecentCerts] = useState([])
  const [recentCAs, setRecentCAs] = useState([])
  const [recentAcme, setRecentAcme] = useState([])
  const [activityLog, setActivityLog] = useState([])
  const [systemStatus, setSystemStatus] = useState(null)
  const [expiringCerts, setExpiringCerts] = useState([])
  const [certificateTrend, setCertificateTrend] = useState([])
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState(new Date())
  const [versionInfo, setVersionInfo] = useState({ version: '2.0.0', edition: 'community', update_available: false })
  
  // Widget customization
  const [widgets, setWidgets] = useState(loadWidgetPrefs)
  const [showWidgetSettings, setShowWidgetSettings] = useState(false)
  const refreshTimeoutRef = useRef(null)

  // WebSocket for live updates
  const { isConnected, subscribe } = useWebSocket({ showToasts: true })

  const loadDashboard = useCallback(async () => {
    try {
      const [statsData, casData, certsData, activityData, statusData, trendData] = await Promise.all([
        dashboardService.getStats(),
        dashboardService.getRecentCAs(5),
        certificatesService.getAll({ limit: 5, sort: 'created_at', order: 'desc' }),
        dashboardService.getActivityLog(10),
        dashboardService.getSystemStatus(),
        dashboardService.getCertificateTrend(7),
      ])
      
      setStats(statsData.data || {})
      setRecentCAs(casData.data || [])
      setRecentCerts(certsData.data?.certificates || certsData.data || [])
      setActivityLog(activityData.data?.activity || [])
      setSystemStatus(statusData.data || {})
      setCertificateTrend(trendData.data?.trend || [])
      setLastUpdate(new Date())
      
      // Get expiring certificates (within 30 days)
      try {
        const expiringData = await certificatesService.getAll({ 
          expiring_within: 30, 
          limit: 5 
        })
        setExpiringCerts(expiringData.data?.certificates || [])
      } catch {
        setExpiringCerts([])
      }
      
      // Try to get ACME accounts
      try {
        const acmeData = await acmeService.getAccounts()
        setRecentAcme(acmeData.data?.slice(0, 5) || [])
      } catch {
        setRecentAcme([])
      }
    } catch (error) {
      showError(error.message || t('dashboard.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  // Load version info
  useEffect(() => {
    const loadVersion = async () => {
      try {
        const response = await fetch('/api/v2/system/updates/version')
        if (response.ok) {
          const data = await response.json()
          setVersionInfo(data.data || { version: '2.0.0', edition: 'community', update_available: false })
        }
      } catch {}
    }
    loadVersion()
  }, [])

  // Subscribe to PKI events for auto-refresh
  useEffect(() => {
    if (!isConnected) return
    
    const debouncedRefresh = () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current)
      }
      refreshTimeoutRef.current = setTimeout(() => {
        loadDashboard()
      }, 1000)
    }
    
    // Subscribe to certificate events
    const unsub1 = subscribe(EventType.CERTIFICATE_ISSUED, debouncedRefresh)
    const unsub2 = subscribe(EventType.CERTIFICATE_REVOKED, debouncedRefresh)
    const unsub3 = subscribe(EventType.CA_CREATED, debouncedRefresh)
    
    // Subscribe for activity log updates
    const unsub4 = subscribe(EventType.USER_LOGIN, (data) => {
      setActivityLog(prev => [{
        id: Date.now(),
        action: 'login_success',
        message: `Password login successful for ${data.username}`,
        user: data.username,
        timestamp: new Date().toISOString()
      }, ...prev.slice(0, 9)])
    })
    
    return () => {
      unsub1?.()
      unsub2?.()
      unsub3?.()
      unsub4?.()
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current)
      }
    }
  }, [isConnected, subscribe, loadDashboard])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message="Loading dashboard..." />
      </div>
    )
  }

  const getGreeting = () => {
    const hour = new Date().getHours()
    if (hour < 12) return t('dashboard.goodMorning')
    if (hour < 18) return t('dashboard.goodAfternoon')
    return t('dashboard.goodEvening')
  }

  const totalCerts = stats?.total_certificates || 0
  const totalCAs = stats?.total_cas || 0
  const pendingCSRs = stats?.pending_csrs || 0
  const acmeAccounts = recentAcme.length
  const expiringCount = expiringCerts.length

  return (
    <div className="flex-1 h-full overflow-auto bg-bg-primary">
      <div className="p-4 space-y-4 max-w-[1800px] mx-auto min-h-full flex flex-col">
        
        {/* Hero Header */}
        <div className="relative overflow-hidden rounded-xl hero-gradient border border-accent-primary/20 p-4">
          <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full bg-accent-primary/5 blur-2xl" />
          
          <div className="relative flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-4">
              <Logo variant="horizontal" size="md" />
              <div className="hidden sm:block w-px h-10 bg-border/50" />
              <div>
                <p className="text-sm text-text-secondary">{getGreeting()} 👋</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <Badge variant="primary" size="sm">
                    {t('common.community')}
                  </Badge>
                  <span className="text-xs text-text-tertiary">v{versionInfo.version}</span>
                  {versionInfo.update_available && (
                    <Badge variant="warning" size="sm" dot>{t('common.updateAvailable')}</Badge>
                  )}
                  {/* Live Indicator */}
                  <div className="flex items-center gap-1 ml-2">
                    <div className={`w-2 h-2 rounded-full ${isConnected ? 'status-success-bg-solid animate-pulse' : 'bg-text-tertiary'}`} />
                    <span className={`text-xs ${isConnected ? 'status-success-text' : 'text-text-tertiary'}`}>
                      {isConnected ? t('dashboard.liveUpdates') : t('common.offline')}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="flex-1" />
            
            {/* Quick Actions */}
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={() => navigate('/certificates?action=create')}>
                <Plus size={14} weight="bold" />
                {t('common.issueCert')}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => navigate('/cas?action=create')}>
                <Plus size={14} weight="bold" />
                {t('common.createCA')}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => navigate('/csrs')}>
                <ListChecks size={14} weight="bold" />
                {t('common.signCSR')}
              </Button>
              <Button 
                size="sm" 
                variant="ghost" 
                onClick={loadDashboard} 
                title={t('common.refresh')}
                className="hidden md:flex"
              >
                <ArrowsClockwise size={14} />
              </Button>
              <Button 
                size="sm" 
                variant="ghost" 
                onClick={() => setShowWidgetSettings(true)} 
                title={t('dashboard.customizeDashboard')}
                className="hidden md:flex"
              >
                <SlidersHorizontal size={14} />
              </Button>
            </div>
          </div>
        </div>

        {/* Stats Row - Now with colors and live indicators */}
        {widgets.find(w => w.id === 'stats')?.visible && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard 
            icon={Certificate}
            label={t('common.certificates')}
            value={totalCerts}
            color="blue"
            live={isConnected}
            onClick={() => navigate('/certificates')}
          />
          <StatCard 
            icon={ShieldCheck}
            label={t('common.cas')}
            value={totalCAs}
            color="purple"
            live={isConnected}
            onClick={() => navigate('/cas')}
          />
          <StatCard 
            icon={ListChecks}
            label={t('common.csrs')}
            value={pendingCSRs}
            color={pendingCSRs > 0 ? 'yellow' : 'slate'}
            badge={pendingCSRs > 0 ? t('common.pending') : null}
            onClick={() => navigate('/csrs')}
          />
          <StatCard 
            icon={Globe}
            label={t('nav.acme')}
            value={acmeAccounts}
            color="emerald"
            onClick={() => navigate('/acme')}
          />
        </div>
        )}
        
        {/* Charts Row */}
        {widgets.find(w => w.id === 'charts')?.visible && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Certificate Trend */}
          <Card variant="elevated" className="p-0">
            <Card.Header 
              icon={Lightning}
              iconColor="blue"
              title={t('dashboard.certificateActivity')}
              subtitle={t('dashboard.last7Days')}
            />
            <Card.Body className="!pt-2 !pb-2">
              <CertificateTrendChart data={certificateTrend} height={140} />
            </Card.Body>
          </Card>
          
          {/* Status Distribution */}
          <Card variant="elevated" className="p-0">
            <Card.Header 
              icon={Certificate}
              iconColor="violet"
              title={t('dashboard.statusDistribution')}
              subtitle={t('dashboard.currentCertificates')}
            />
            <Card.Body className="!pt-2 !pb-2">
              <StatusPieChart 
                data={{
                  valid: Math.max(0, (stats?.total_certificates || 0) - (stats?.expiring_soon || 0) - (stats?.revoked || 0)),
                  expiring: stats?.expiring_soon || 0,
                  expired: 0,
                  revoked: stats?.revoked || 0,
                }}
                height={140} 
              />
            </Card.Body>
          </Card>
        </div>
        )}

        {/* Expiring Certs Warning Banner */}
        {widgets.find(w => w.id === 'expiring')?.visible && expiringCount > 0 && (
          <div 
            onClick={() => navigate('/certificates?filter=expiring')}
            className="flex items-center gap-3 p-3 rounded-lg stat-card-warning cursor-pointer border transition-colors"
          >
            <div className="w-8 h-8 rounded-lg status-warning-bg flex items-center justify-center">
              <Warning size={18} weight="fill" className="status-warning-text" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium status-warning-text">
                {t('dashboard.expiringCertificates', { count: expiringCount })}
              </p>
              <p className="text-xs text-text-secondary">{t('dashboard.clickToRenew')}</p>
            </div>
            <CaretRight size={16} className="status-warning-text" />
          </div>
        )}

        {/* Main Content - 2x2 Grid + Activity Column */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-0">
          
          {/* Left: 2x2 Grid for Certs, CAs, System, ACME */}
          <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
            
            {/* Recent Certificates */}
            {widgets.find(w => w.id === 'certs')?.visible && (
            <Card variant="elevated" className="flex flex-col min-h-[200px] p-0">
              <Card.Header 
                icon={Certificate}
                iconColor="blue"
                title={t('dashboard.recentCertificates')}
                action={
                  <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/certificates')}>
                    {t('common.viewAll')} <CaretRight size={12} />
                  </Button>
                }
              />
              <Card.Body className="flex-1 overflow-y-auto space-y-0.5 !pt-0">
                {recentCerts.length === 0 ? (
                  <EmptyWidget icon={Certificate} text={t('dashboard.noCertificatesYet')} />
                ) : (
                  recentCerts.slice(0, 4).map((cert, i) => (
                    <div 
                      key={cert.id || i}
                      onClick={() => navigate(`/certificates/${cert.id}`)}
                      className="p-2.5 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-all group flex items-center gap-3"
                    >
                      <div className="w-8 h-8 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0 group-hover:bg-accent-primary/10 transition-colors">
                        <Certificate size={16} weight="duotone" className="text-text-tertiary group-hover:text-accent-primary transition-colors" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium text-text-primary truncate group-hover:text-accent-primary transition-colors">
                            {cert.common_name || cert.descr || cert.subject || t('common.certificate')}
                          </span>
                          <Badge variant={cert.revoked ? 'danger' : 'success'} size="sm" dot>
                            {cert.revoked ? t('common.revoked') : t('common.valid')}
                          </Badge>
                        </div>
                        <div className="text-xs text-text-tertiary mt-0.5">
                          {formatRelativeTime(cert.created_at, t)}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </Card.Body>
            </Card>
            )}

            {/* Recent CAs */}
            {widgets.find(w => w.id === 'cas')?.visible && (
            <Card variant="elevated" className="flex flex-col min-h-[200px] p-0">
              <Card.Header 
                icon={ShieldCheck}
                iconColor="violet"
                title={t('dashboard.recentCAs')}
                action={
                  <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/cas')}>
                    {t('common.viewAll')} <CaretRight size={12} />
                  </Button>
                }
              />
              <Card.Body className="flex-1 overflow-y-auto space-y-0.5 !pt-0">
                {recentCAs.length === 0 ? (
                  <EmptyWidget icon={ShieldCheck} text={t('dashboard.noCAsYet')} />
                ) : (
                  recentCAs.slice(0, 4).map((ca, i) => (
                    <div 
                      key={ca.id || i}
                      onClick={() => navigate(`/cas/${ca.id}`)}
                      className="p-2.5 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors group flex items-center gap-3"
                    >
                      <div className="w-8 h-8 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0 group-hover:bg-accent-primary/10 transition-colors">
                        <ShieldCheck size={16} weight="duotone" className="text-text-tertiary group-hover:text-accent-primary transition-colors" />
                      </div>
                      <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-text-primary truncate group-hover:text-accent-primary transition-colors">
                          {ca.dn_commonname || ca.descr || ca.name}
                        </span>
                        <Badge variant={ca.is_root ? 'purple' : 'info'} size="sm">
                          {ca.is_root ? t('common.root') : t('dashboard.sub')}
                        </Badge>
                      </div>
                    </div>
                  ))
                )}
              </Card.Body>
            </Card>
            )}

            {/* System Health */}
            {widgets.find(w => w.id === 'system')?.visible && (
            <Card variant="elevated" className="flex flex-col min-h-[200px] p-0">
              <Card.Header 
                icon={Heartbeat}
                iconColor="emerald"
                title={t('dashboard.systemHealth')}
                action={
                  <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/settings')}>
                    <Gear size={14} />
                  </Button>
                }
              />
              <Card.Body className="!pt-2">
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <SystemStat 
                    icon={WifiHigh} 
                    label={t('dashboard.websocket')} 
                    value={isConnected ? t('common.connected') : t('common.disconnected')} 
                    status={isConnected ? 'online' : 'offline'} 
                  />
                  <SystemStat 
                    icon={Database} 
                    label={t('common.database')} 
                    value={t('dashboard.healthy')} 
                    status="online" 
                  />
                  <SystemStat 
                    icon={Clock} 
                    label={t('common.lastUpdate')} 
                    value={formatRelativeTime(lastUpdate, t)} 
                    status="online" 
                  />
                  <SystemStat 
                    icon={Lightning} 
                    label={t('dashboard.api')} 
                    value={t('common.online')} 
                    status="online" 
                  />
                </div>
                <div className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-2">
                  {t('dashboard.services')}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <ServiceBadge name="ACME" status={systemStatus?.acme} />
                  <ServiceBadge name="SCEP" status={systemStatus?.scep} />
                  <ServiceBadge name="OCSP" status={systemStatus?.ocsp} />
                  <ServiceBadge name="CRL" status={systemStatus?.crl} />
                </div>
              </Card.Body>
            </Card>
            )}

            {/* ACME Accounts */}
            {widgets.find(w => w.id === 'acme')?.visible && (
            <Card variant="elevated" className="flex flex-col min-h-[200px] p-0">
              <Card.Header 
                icon={Globe}
                iconColor="orange"
                title={t('dashboard.acmeAccounts')}
                action={
                  <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/acme')}>
                    {t('common.viewAll')} <CaretRight size={12} />
                  </Button>
                }
              />
              <Card.Body className="flex-1 overflow-y-auto !pt-0">
                {recentAcme.length === 0 ? (
                  <EmptyWidget icon={Globe} text={t('dashboard.noAcmeAccounts')} />
                ) : (
                  <div className="space-y-0.5">
                    {recentAcme.slice(0, 4).map((account, i) => (
                      <div 
                        key={account.id || i} 
                        className="p-2.5 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors group flex items-center gap-3"
                        onClick={() => navigate('/acme')}
                      >
                        <div className="w-8 h-8 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0 group-hover:bg-accent-primary/10 transition-colors">
                          <User size={16} weight="duotone" className="text-text-tertiary group-hover:text-accent-primary transition-colors" />
                        </div>
                        <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
                          <span className="text-sm font-medium text-text-primary truncate group-hover:text-accent-primary transition-colors">
                            {account.email || account.contact}
                          </span>
                          <Badge variant="secondary" size="sm">{account.orders_count || 0} {t('dashboard.orders')}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card.Body>
            </Card>
            )}
          </div>

          {/* Recent Activity with Live Indicator */}
          {widgets.find(w => w.id === 'activity')?.visible && (
          <Card variant="elevated" className="flex flex-col min-h-[320px] p-0">
            <Card.Header 
              icon={ClockCounterClockwise}
              iconColor="teal"
              title={t('dashboard.recentActivity')}
              subtitle={isConnected ? t('dashboard.liveUpdates') : undefined}
              action={
                <div className="flex items-center gap-2">
                  {isConnected && (
                    <Badge variant="success" size="sm" dot pulse>{t('common.live')}</Badge>
                  )}
                  <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/audit')}>
                    {t('common.viewAll')} <CaretRight size={12} />
                  </Button>
                </div>
              }
            />
            <Card.Body className="flex-1 overflow-y-auto !pt-0">
              {activityLog.length === 0 ? (
                <EmptyWidget icon={ClockCounterClockwise} text={t('dashboard.noRecentActivity')} />
              ) : (
                <div className="space-y-0.5">
                  {activityLog.map((activity, i) => {
                    const Icon = actionIcons[activity.action] || actionIcons.default
                    const isError = activity.action === 'login_failed' || activity.action === 'revoke'
                    const isSuccess = activity.action === 'login_success' || activity.action === 'create'
                    return (
                      <div 
                        key={activity.id || i}
                        className="flex items-start gap-2.5 py-2 px-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors"
                      >
                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                          isError 
                            ? 'status-danger-bg status-danger-text' 
                            : isSuccess 
                              ? 'status-success-bg status-success-text'
                              : 'status-primary-bg status-primary-text'
                        }`}>
                          <Icon size={14} weight="bold" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-text-primary leading-tight">
                            {activity.message || `${activity.action} ${activity.resource_type || ''}`}
                          </p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className="text-[10px] text-text-secondary font-medium">{activity.user || 'System'}</span>
                            <span className="text-text-tertiary text-[10px]">•</span>
                            <span className="text-[10px] text-text-tertiary">
                              {formatRelativeTime(activity.timestamp, t)}
                            </span>
                          </div>
                        </div>
                      </div>
                    )
                })}
                </div>
              )}
            </Card.Body>
          </Card>
          )}
        </div>

      </div>
      
      {/* Widget Settings Modal */}
      <WidgetSettingsModal
        open={showWidgetSettings}
        onClose={() => setShowWidgetSettings(false)}
        widgets={widgets}
        onSave={(newWidgets) => {
          setWidgets(newWidgets)
          saveWidgetPrefs(newWidgets)
          setShowWidgetSettings(false)
        }}
      />
    </div>
  )
}

// Widget Settings Modal
function WidgetSettingsModal({ open, onClose, widgets, onSave }) {
  const { t } = useTranslation()
  const [localWidgets, setLocalWidgets] = useState(widgets)
  
  useEffect(() => {
    setLocalWidgets(widgets)
  }, [widgets, open])
  
  const toggleWidget = (id) => {
    setLocalWidgets(prev => prev.map(w => 
      w.id === id ? { ...w, visible: !w.visible } : w
    ))
  }
  
  const resetToDefaults = () => {
    setLocalWidgets(DEFAULT_WIDGETS)
  }

  return (
    <Modal open={open} onClose={onClose} size="sm">
      <div className="p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg icon-bg-blue flex items-center justify-center">
              <SlidersHorizontal size={18} className="text-accent-primary" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-text-primary">{t('dashboard.customizeDashboard')}</h2>
              <p className="text-xs text-text-secondary">{t('dashboard.showOrHideWidgets')}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-bg-tertiary text-text-secondary">
            <X size={18} />
          </button>
        </div>
        
        <div className="space-y-1 mb-4">
          {localWidgets.map(widget => (
            <button
              key={widget.id}
              onClick={() => toggleWidget(widget.id)}
              className="w-full flex items-center gap-3 p-2.5 rounded-lg hover:bg-bg-tertiary transition-colors"
            >
              <div className={`w-5 h-5 rounded flex items-center justify-center transition-colors ${
                widget.visible ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-tertiary'
              }`}>
                {widget.visible ? <Eye size={14} /> : <EyeSlash size={14} />}
              </div>
              <span className={`text-sm ${widget.visible ? 'text-text-primary' : 'text-text-tertiary'}`}>
                {t(widget.nameKey)}
              </span>
            </button>
          ))}
        </div>
        
        <div className="flex items-center justify-between pt-3 border-t border-border">
          <Button size="sm" variant="ghost" onClick={resetToDefaults}>
            {t('common.reset')}
          </Button>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button size="sm" onClick={() => onSave(localWidgets)}>
              {t('common.save')}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

// Enhanced Stat Card with live indicator and subtle polish
function StatCard({ icon: Icon, label, value, color, onClick, live, badge }) {
  const accentMap = {
    blue: '--accent-primary',
    purple: '--accent-primary',
    yellow: '--accent-warning',
    emerald: '--accent-success',
    slate: '--text-tertiary',
  }
  
  const colorClasses = {
    blue: 'primary',
    purple: 'primary',
    yellow: 'warning',
    emerald: 'success',
    slate: '',
  }
  
  const iconStyles = {
    blue: 'icon-bg-blue',
    purple: 'icon-bg-violet',
    yellow: 'icon-bg-amber',
    emerald: 'icon-bg-emerald',
    slate: 'icon-bg-teal',
  }
  
  const variant = colorClasses[color] || ''
  const accentVar = accentMap[color] || accentMap.slate
  
  return (
    <button 
      onClick={onClick}
      className={`stat-card-enhanced ${variant} relative p-4 text-left group transition-all duration-200`}
      style={{ '--card-accent': `var(${accentVar})` }}
    >
      {/* Live indicator */}
      {live && (
        <div className="absolute top-3 right-3 flex items-center gap-1.5 z-10">
          <span className="text-[10px] status-success-text font-medium opacity-0 group-hover:opacity-100 transition-opacity">Live</span>
          <div className="w-2 h-2 rounded-full status-success-bg-solid animate-pulse-soft" />
        </div>
      )}
      
      <div className="relative flex items-center gap-3">
        <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-105 ${iconStyles[color] || iconStyles.slate}`}>
          <Icon size={22} weight="duotone" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-2xl font-bold text-text-primary tracking-tight tabular-nums">{value}</p>
            {badge && (
              <Badge variant="warning" size="sm" dot pulse>{badge}</Badge>
            )}
          </div>
          <p className="text-xs text-text-secondary font-medium">{label}</p>
        </div>
      </div>
      
      {/* Subtle hover arrow */}
      <CaretRight 
        size={14} 
        className="absolute right-3 bottom-3 text-text-tertiary opacity-0 group-hover:opacity-60 transition-all duration-200 group-hover:translate-x-0.5" 
      />
    </button>
  )
}

// System Stat mini card - polished with icon animation
function SystemStat({ icon: Icon, label, value, status }) {
  return (
    <div className={`px-3 py-2 rounded-lg border transition-all duration-200 group ${
      status === 'online' 
        ? 'stat-card-success' 
        : 'stat-card-danger'
    }`}>
      <div className="flex items-center gap-2">
        <div className={`w-5 h-5 rounded flex items-center justify-center transition-transform duration-200 group-hover:scale-110 ${
          status === 'online' ? 'status-success-bg' : 'status-danger-bg'
        }`}>
          <Icon size={12} className={status === 'online' ? 'status-success-text' : 'status-danger-text'} weight="bold" />
        </div>
        <span className="text-[10px] text-text-tertiary uppercase tracking-wide font-medium">{label}</span>
      </div>
      <p className={`text-xs font-semibold mt-1 ${
        status === 'online' ? 'status-success-text' : 'status-danger-text'
      }`}>{value}</p>
    </div>
  )
}

// Service Badge Component - theme-aware with subtle animation
function ServiceBadge({ name, status }) {
  const isOnline = status?.status === 'online' || status?.enabled
  return (
    <div className={`px-3 py-2.5 rounded-lg border text-center transition-all duration-200 group cursor-default ${
      isOnline 
        ? 'stat-card-success' 
        : 'bg-bg-tertiary border-border hover:border-text-tertiary/30'
    }`}>
      <div className="flex items-center justify-center gap-2">
        <div className={`w-2 h-2 rounded-full transition-transform duration-300 group-hover:scale-125 ${isOnline ? 'status-success-bg-solid animate-pulse' : 'bg-text-tertiary'}`} />
        <span className={`text-xs font-semibold ${isOnline ? 'text-text-primary' : 'text-text-secondary'}`}>{name}</span>
      </div>
    </div>
  )
}

// Empty Widget Component - polished empty state
function EmptyWidget({ icon: Icon, text }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary py-8">
      <div className="w-12 h-12 rounded-xl bg-bg-tertiary/50 flex items-center justify-center mb-3 border border-border/50">
        <Icon size={24} className="opacity-50" />
      </div>
      <p className="text-xs font-medium opacity-70">{text}</p>
    </div>
  )
}
