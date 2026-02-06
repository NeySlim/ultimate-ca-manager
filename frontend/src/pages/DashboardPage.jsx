/**
 * Dashboard Page - Live Operational Dashboard with WebSocket
 * Clean redesign using theme-aware CSS classes
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  ShieldCheck, Certificate, ClockCounterClockwise, Clock,
  Plus, ArrowsClockwise, ListChecks, Gear, CaretRight, 
  User, Globe, SignIn, SignOut, Trash, PencilSimple, 
  UploadSimple, Key, Warning, WifiHigh, Heartbeat, Database, Lightning,
  SlidersHorizontal, Eye, EyeSlash, X, CheckCircle, XCircle
} from '@phosphor-icons/react'
import { Card, Button, Badge, LoadingSpinner, Logo, Modal } from '../components'
import { CertificateTrendChart, StatusPieChart } from '../components/DashboardChart'
import { dashboardService, certificatesService, acmeService } from '../services'
import { useNotification } from '../contexts'
import { useWebSocket, EventType } from '../hooks'
import { formatRelativeTime } from '../lib/ui'

// Default widgets configuration
const DEFAULT_WIDGETS = [
  { id: 'stats', name: 'Statistics', visible: true },
  { id: 'charts', name: 'Charts & Analytics', visible: true },
  { id: 'system', name: 'System Status', visible: true },
  { id: 'expiring', name: 'Expiring Certificates', visible: true },
  { id: 'activity', name: 'Recent Activity', visible: true },
  { id: 'certs', name: 'Recent Certificates', visible: true },
  { id: 'cas', name: 'Certificate Authorities', visible: true },
  { id: 'acme', name: 'ACME Accounts', visible: true },
]

const loadWidgetPrefs = () => {
  try {
    const saved = localStorage.getItem('ucm-dashboard-widgets')
    if (saved) {
      const parsed = JSON.parse(saved)
      return DEFAULT_WIDGETS.map(w => ({
        ...w,
        visible: parsed.find(p => p.id === w.id)?.visible ?? w.visible,
        order: parsed.findIndex(p => p.id === w.id)
      })).sort((a, b) => (a.order >= 0 ? a.order : 999) - (b.order >= 0 ? b.order : 999))
    }
  } catch {}
  return DEFAULT_WIDGETS
}

const saveWidgetPrefs = (widgets) => {
  localStorage.setItem('ucm-dashboard-widgets', JSON.stringify(widgets.map(w => ({ id: w.id, visible: w.visible }))))
}

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
  const [versionInfo, setVersionInfo] = useState({ version: '', edition: 'community' })
  
  const [widgets, setWidgets] = useState(loadWidgetPrefs)
  const [showWidgetSettings, setShowWidgetSettings] = useState(false)
  const refreshTimeoutRef = useRef(null)

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
      
      try {
        const expiringData = await certificatesService.getAll({ expiring_within: 30, limit: 5 })
        setExpiringCerts(expiringData.data?.certificates || [])
      } catch {
        setExpiringCerts([])
      }
      
      try {
        const acmeData = await acmeService.getAccounts()
        setRecentAcme(acmeData.data?.slice(0, 5) || [])
      } catch {
        setRecentAcme([])
      }
    } catch (error) {
      showError(error.message || 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  useEffect(() => {
    const loadVersion = async () => {
      try {
        const response = await fetch('/api/v2/system/updates/version')
        if (response.ok) {
          const data = await response.json()
          setVersionInfo(data.data || { version: '', edition: 'community' })
        }
      } catch {}
    }
    loadVersion()
  }, [])

  useEffect(() => {
    if (!isConnected) return
    
    const debouncedRefresh = () => {
      if (refreshTimeoutRef.current) clearTimeout(refreshTimeoutRef.current)
      refreshTimeoutRef.current = setTimeout(() => loadDashboard(), 1000)
    }
    
    const unsub1 = subscribe(EventType.CERTIFICATE_ISSUED, debouncedRefresh)
    const unsub2 = subscribe(EventType.CERTIFICATE_REVOKED, debouncedRefresh)
    const unsub3 = subscribe(EventType.CA_CREATED, debouncedRefresh)
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
      unsub1?.(); unsub2?.(); unsub3?.(); unsub4?.()
      if (refreshTimeoutRef.current) clearTimeout(refreshTimeoutRef.current)
    }
  }, [isConnected, subscribe, loadDashboard])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message="Loading dashboard..." />
      </div>
    )
  }

  const totalCerts = stats?.total_certificates || 0
  const totalCAs = stats?.total_cas || 0
  const pendingCSRs = stats?.pending_csrs || 0
  const acmeAccounts = recentAcme.length
  const expiringCount = expiringCerts.length

  return (
    <div className="flex-1 h-full overflow-y-auto xl:overflow-hidden bg-bg-primary">
      <div className="p-4 lg:p-6 space-y-4 lg:space-y-5 max-w-[1920px] mx-auto xl:h-full xl:flex xl:flex-col">
        
        {/* Header */}
        <header className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-3">
            <Logo variant="horizontal" size="md" />
            <div className="hidden sm:flex items-center gap-2 pl-3 border-l border-border">
              <Badge variant={versionInfo.edition === 'pro' ? 'purple' : 'primary'} size="sm">
                {versionInfo.edition === 'pro' ? 'Pro' : 'Community'}
              </Badge>
              <span className="text-xs text-text-tertiary font-mono">v{versionInfo.version || '2.0.0'}</span>
            </div>
          </div>
          
          <div className="flex-1" />
          
          <div className="flex items-center gap-2">
            {/* Connection Status */}
            <div className={`hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
              isConnected 
                ? 'bg-[color-mix(in_srgb,var(--accent-success)_10%,transparent)] text-[var(--accent-success)] border-[color-mix(in_srgb,var(--accent-success)_25%,transparent)]' 
                : 'bg-bg-tertiary text-text-tertiary border-border'
            }`}>
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-current animate-pulse' : 'bg-current opacity-50'}`} />
              {isConnected ? 'Live' : 'Offline'}
            </div>
            
            <Button size="sm" onClick={() => navigate('/certificates?action=create')}>
              <Plus size={14} weight="bold" />
              <span className="hidden sm:inline">Issue Cert</span>
            </Button>
            <Button size="sm" variant="ghost" onClick={loadDashboard} title="Refresh">
              <ArrowsClockwise size={16} />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowWidgetSettings(true)} title="Customize" className="hidden md:flex">
              <SlidersHorizontal size={16} />
            </Button>
          </div>
        </header>

        {/* Stats Grid */}
        {widgets.find(w => w.id === 'stats')?.visible && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard 
            icon={Certificate} 
            label="Certificates" 
            value={totalCerts} 
            color="primary"
            onClick={() => navigate('/certificates')} 
          />
          <StatCard 
            icon={ShieldCheck} 
            label="Authorities" 
            value={totalCAs} 
            color="purple"
            onClick={() => navigate('/cas')} 
          />
          <StatCard 
            icon={ListChecks} 
            label="CSR Queue" 
            value={pendingCSRs} 
            color={pendingCSRs > 0 ? 'warning' : 'default'}
            badge={pendingCSRs > 0 ? 'Pending' : null}
            onClick={() => navigate('/csrs')} 
          />
          <StatCard 
            icon={Globe} 
            label="ACME" 
            value={acmeAccounts} 
            color="success"
            onClick={() => navigate('/acme')} 
          />
        </div>
        )}
        
        {/* Charts - 2xl+ only */}
        {widgets.find(w => w.id === 'charts')?.visible && (
        <div className="hidden 2xl:grid grid-cols-2 gap-4">
          <div className="dashboard-widget p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg icon-bg-blue flex items-center justify-center">
                <Lightning size={16} weight="duotone" className="text-[var(--icon-blue-text)]" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-text-primary">Certificate Activity</h3>
                <p className="text-2xs text-text-tertiary">Last 7 days</p>
              </div>
            </div>
            <CertificateTrendChart data={certificateTrend} height={90} />
          </div>
          
          <div className="dashboard-widget p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg icon-bg-violet flex items-center justify-center">
                <Certificate size={16} weight="duotone" className="text-[var(--icon-violet-text)]" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-text-primary">Status Distribution</h3>
                <p className="text-2xs text-text-tertiary">Current certificates</p>
              </div>
            </div>
            <StatusPieChart 
              data={{
                valid: Math.max(0, (stats?.total_certificates || 0) - (stats?.expiring_soon || 0) - (stats?.revoked || 0)),
                expiring: stats?.expiring_soon || 0,
                expired: 0,
                revoked: stats?.revoked || 0,
              }}
              height={90} 
            />
          </div>
        </div>
        )}

        {/* Expiring Warning */}
        {widgets.find(w => w.id === 'expiring')?.visible && expiringCount > 0 && (
          <button 
            onClick={() => navigate('/certificates?filter=expiring')}
            className="w-full flex items-center gap-3 p-3 rounded-xl stat-card-warning group"
          >
            <div className="w-10 h-10 rounded-lg status-warning-bg flex items-center justify-center">
              <Warning size={20} weight="fill" className="status-warning-text" />
            </div>
            <div className="flex-1 text-left">
              <p className="text-sm font-semibold status-warning-text">
                {expiringCount} certificate{expiringCount > 1 ? 's' : ''} expiring soon
              </p>
              <p className="text-xs text-text-secondary">Click to review and renew</p>
            </div>
            <CaretRight size={16} className="status-warning-text opacity-50 group-hover:opacity-100 transition-all" />
          </button>
        )}

        {/* Main Grid */}
        <div className="xl:flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4">
          
          {/* Left: 2x2 Grid */}
          <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
            
            {/* Recent Certificates */}
            {widgets.find(w => w.id === 'certs')?.visible && (
            <WidgetCard
              icon={Certificate}
              iconClass="icon-bg-blue"
              iconTextClass="text-[var(--icon-blue-text)]"
              title="Recent Certificates"
              action={<Button size="sm" variant="ghost" onClick={() => navigate('/certificates')}>View all</Button>}
            >
              {recentCerts.length === 0 ? (
                <EmptyState icon={Certificate} text="No certificates yet" />
              ) : (
                <div className="space-y-1">
                  {recentCerts.slice(0, 3).map((cert, i) => (
                    <ListItem
                      key={cert.id || i}
                      icon={Certificate}
                      title={cert.common_name || cert.descr || 'Certificate'}
                      subtitle={formatRelativeTime(cert.created_at)}
                      badge={<Badge variant={cert.revoked ? 'danger' : 'success'} size="sm" dot>{cert.revoked ? 'Revoked' : 'Valid'}</Badge>}
                      onClick={() => navigate(`/certificates/${cert.id}`)}
                    />
                  ))}
                </div>
              )}
            </WidgetCard>
            )}

            {/* Recent CAs */}
            {widgets.find(w => w.id === 'cas')?.visible && (
            <WidgetCard
              icon={ShieldCheck}
              iconClass="icon-bg-violet"
              iconTextClass="text-[var(--icon-violet-text)]"
              title="Certificate Authorities"
              action={<Button size="sm" variant="ghost" onClick={() => navigate('/cas')}>View all</Button>}
            >
              {recentCAs.length === 0 ? (
                <EmptyState icon={ShieldCheck} text="No CAs yet" />
              ) : (
                <div className="space-y-1">
                  {recentCAs.slice(0, 3).map((ca, i) => (
                    <ListItem
                      key={ca.id || i}
                      icon={ShieldCheck}
                      title={ca.dn_commonname || ca.descr || ca.name}
                      badge={<Badge variant={ca.is_root ? 'purple' : 'info'} size="sm">{ca.is_root ? 'Root' : 'Sub'}</Badge>}
                      onClick={() => navigate(`/cas/${ca.id}`)}
                    />
                  ))}
                </div>
              )}
            </WidgetCard>
            )}

            {/* System Health */}
            {widgets.find(w => w.id === 'system')?.visible && (
            <WidgetCard
              icon={Heartbeat}
              iconClass="icon-bg-emerald"
              iconTextClass="text-[var(--icon-emerald-text)]"
              title="System Health"
              action={<Button size="sm" variant="ghost" onClick={() => navigate('/settings')}><Gear size={14} /></Button>}
            >
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <MiniStat 
                    icon={WifiHigh} 
                    label="WebSocket" 
                    value={isConnected ? 'Connected' : 'Offline'} 
                    status={isConnected ? 'success' : 'danger'} 
                  />
                  <MiniStat 
                    icon={Database} 
                    label="Database" 
                    value="Healthy" 
                    status="success" 
                  />
                </div>
                <div>
                  <p className="text-2xs text-text-tertiary uppercase tracking-wider font-semibold mb-2">Services</p>
                  <div className="grid grid-cols-4 gap-1.5">
                    <ServicePill name="ACME" online={systemStatus?.acme?.enabled} />
                    <ServicePill name="SCEP" online={systemStatus?.scep?.enabled} />
                    <ServicePill name="OCSP" online={systemStatus?.ocsp?.enabled} />
                    <ServicePill name="CRL" online={systemStatus?.crl?.enabled} />
                  </div>
                </div>
              </div>
            </WidgetCard>
            )}

            {/* ACME Accounts */}
            {widgets.find(w => w.id === 'acme')?.visible && (
            <WidgetCard
              icon={Globe}
              iconClass="icon-bg-orange"
              iconTextClass="text-[var(--icon-orange-text)]"
              title="ACME Accounts"
              action={<Button size="sm" variant="ghost" onClick={() => navigate('/acme')}>View all</Button>}
            >
              {recentAcme.length === 0 ? (
                <EmptyState icon={Globe} text="No ACME accounts" />
              ) : (
                <div className="space-y-1">
                  {recentAcme.slice(0, 3).map((account, i) => (
                    <ListItem
                      key={account.id || i}
                      icon={User}
                      title={account.email || account.contact}
                      badge={<Badge variant="secondary" size="sm">{account.orders_count || 0} orders</Badge>}
                      onClick={() => navigate('/acme')}
                    />
                  ))}
                </div>
              )}
            </WidgetCard>
            )}
          </div>

          {/* Right: Activity */}
          {widgets.find(w => w.id === 'activity')?.visible && (
          <WidgetCard
            icon={ClockCounterClockwise}
            iconClass="icon-bg-teal"
            iconTextClass="text-[var(--icon-teal-text)]"
            title="Recent Activity"
            subtitle={isConnected ? 'Live updates' : undefined}
            action={
              <div className="flex items-center gap-2">
                {isConnected && <Badge variant="success" size="sm" dot pulse>Live</Badge>}
                <Button size="sm" variant="ghost" onClick={() => navigate('/audit')}>View all</Button>
              </div>
            }
            className="min-h-[280px] xl:min-h-0"
          >
            {activityLog.length === 0 ? (
              <EmptyState icon={ClockCounterClockwise} text="No recent activity" />
            ) : (
              <div className="space-y-0.5">
                {activityLog.slice(0, 6).map((activity, i) => {
                  const Icon = actionIcons[activity.action] || actionIcons.default
                  const isError = activity.action === 'login_failed' || activity.action === 'revoke'
                  const isSuccess = activity.action === 'login_success' || activity.action === 'create'
                  
                  return (
                    <div key={activity.id || i} className="flex items-start gap-2.5 p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
                      <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                        isError ? 'status-danger-bg' : isSuccess ? 'status-success-bg' : 'status-primary-bg'
                      }`}>
                        <Icon size={14} weight="bold" className={
                          isError ? 'status-danger-text' : isSuccess ? 'status-success-text' : 'status-primary-text'
                        } />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-text-primary truncate">
                          {activity.message || `${activity.action} ${activity.resource_type || ''}`}
                        </p>
                        <div className="flex items-center gap-1 mt-0.5">
                          <span className="text-2xs text-text-secondary font-medium">{activity.user || 'System'}</span>
                          <span className="text-2xs text-text-tertiary">•</span>
                          <span className="text-2xs text-text-tertiary">{formatRelativeTime(activity.timestamp)}</span>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </WidgetCard>
          )}
        </div>

      </div>
      
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

// ============ Components ============

function StatCard({ icon: Icon, label, value, color = 'default', onClick, badge }) {
  const colorClasses = {
    primary: 'stat-card-primary',
    success: 'stat-card-success', 
    warning: 'stat-card-warning',
    danger: 'stat-card-danger',
    purple: 'status-purple-bg status-purple-border',
    default: 'bg-bg-secondary border-border hover:border-text-tertiary/30',
  }
  
  const iconClasses = {
    primary: 'status-primary-bg status-primary-text',
    success: 'status-success-bg status-success-text',
    warning: 'status-warning-bg status-warning-text',
    danger: 'status-danger-bg status-danger-text',
    purple: 'status-purple-bg status-purple-text',
    default: 'bg-bg-tertiary text-text-secondary',
  }
  
  return (
    <button 
      onClick={onClick}
      className={`relative p-4 text-left group rounded-xl border transition-all duration-200 hover:shadow-md ${colorClasses[color]}`}
    >
      <div className="flex items-center gap-3">
        <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-105 ${iconClasses[color]}`}>
          <Icon size={22} weight="duotone" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-2xl font-bold text-text-primary tracking-tight tabular-nums">{value}</p>
          <div className="flex items-center gap-2">
            <p className="text-xs text-text-secondary font-medium">{label}</p>
            {badge && <Badge variant="warning" size="sm" dot>{badge}</Badge>}
          </div>
        </div>
        <CaretRight size={14} className="text-text-tertiary opacity-0 group-hover:opacity-70 transition-all group-hover:translate-x-0.5" />
      </div>
    </button>
  )
}

function WidgetCard({ icon: Icon, iconClass, iconTextClass, title, subtitle, action, children, className = '' }) {
  return (
    <div className={`dashboard-widget flex flex-col ${className}`}>
      <div className="flex items-center justify-between p-3 pb-2">
        <div className="flex items-center gap-2.5">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${iconClass}`}>
            <Icon size={16} weight="duotone" className={iconTextClass} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
            {subtitle && <p className="text-2xs text-text-tertiary">{subtitle}</p>}
          </div>
        </div>
        {action}
      </div>
      <div className="flex-1 px-3 pb-3 overflow-y-auto">
        {children}
      </div>
    </div>
  )
}

function ListItem({ icon: Icon, title, subtitle, badge, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-2.5 p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors group text-left"
    >
      <div className="w-8 h-8 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0 group-hover:bg-[color-mix(in_srgb,var(--accent-primary)_10%,transparent)] transition-colors">
        <Icon size={14} weight="duotone" className="text-text-tertiary group-hover:text-[var(--accent-primary)] transition-colors" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary truncate group-hover:text-[var(--accent-primary)] transition-colors">{title}</p>
        {subtitle && <p className="text-2xs text-text-tertiary">{subtitle}</p>}
      </div>
      {badge}
    </button>
  )
}

function MiniStat({ icon: Icon, label, value, status }) {
  const statusClass = status === 'success' ? 'stat-card-success' : status === 'danger' ? 'stat-card-danger' : 'stat-card-primary'
  const iconBg = status === 'success' ? 'status-success-bg' : status === 'danger' ? 'status-danger-bg' : 'status-primary-bg'
  const textClass = status === 'success' ? 'status-success-text' : status === 'danger' ? 'status-danger-text' : 'status-primary-text'
  
  return (
    <div className={`p-2.5 rounded-lg border ${statusClass}`}>
      <div className="flex items-center gap-2">
        <div className={`w-5 h-5 rounded flex items-center justify-center ${iconBg}`}>
          <Icon size={12} weight="bold" className={textClass} />
        </div>
        <span className="text-2xs text-text-tertiary uppercase tracking-wide font-medium">{label}</span>
      </div>
      <p className={`text-xs font-semibold mt-1 ${textClass}`}>{value}</p>
    </div>
  )
}

function ServicePill({ name, online }) {
  return (
    <div className={`px-2 py-1.5 rounded-lg border text-center transition-all ${
      online ? 'stat-card-success' : 'bg-bg-tertiary border-border'
    }`}>
      <div className="flex items-center justify-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${online ? 'status-success-bg-solid animate-pulse' : 'bg-text-tertiary'}`} />
        <span className={`text-2xs font-semibold ${online ? 'text-text-primary' : 'text-text-tertiary'}`}>{name}</span>
      </div>
    </div>
  )
}

function EmptyState({ icon: Icon, text }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center py-6 text-center">
      <div className="w-10 h-10 rounded-xl bg-bg-tertiary/50 flex items-center justify-center mb-2 border border-border/50">
        <Icon size={20} className="text-text-tertiary opacity-50" />
      </div>
      <p className="text-xs text-text-tertiary">{text}</p>
    </div>
  )
}

function WidgetSettingsModal({ open, onClose, widgets, onSave }) {
  const [localWidgets, setLocalWidgets] = useState(widgets)
  
  useEffect(() => {
    setLocalWidgets(widgets)
  }, [widgets, open])
  
  const toggleWidget = (id) => {
    setLocalWidgets(prev => prev.map(w => w.id === id ? { ...w, visible: !w.visible } : w))
  }

  return (
    <Modal open={open} onClose={onClose} size="sm">
      <div className="p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg icon-bg-blue flex items-center justify-center">
              <SlidersHorizontal size={18} className="text-[var(--icon-blue-text)]" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-text-primary">Customize Dashboard</h2>
              <p className="text-xs text-text-secondary">Show or hide widgets</p>
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
                widget.visible ? 'status-primary-bg-solid text-white' : 'bg-bg-tertiary text-text-tertiary'
              }`}>
                {widget.visible ? <Eye size={14} /> : <EyeSlash size={14} />}
              </div>
              <span className={`text-sm ${widget.visible ? 'text-text-primary' : 'text-text-tertiary'}`}>
                {widget.name}
              </span>
            </button>
          ))}
        </div>
        
        <div className="flex items-center justify-between pt-3 border-t border-border">
          <Button size="sm" variant="ghost" onClick={() => setLocalWidgets(DEFAULT_WIDGETS)}>
            Reset
          </Button>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button size="sm" onClick={() => onSave(localWidgets)}>Save</Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
