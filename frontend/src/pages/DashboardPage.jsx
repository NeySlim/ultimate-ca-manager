/**
 * Dashboard Page - Live Operational Dashboard with WebSocket
 * Real-time updates via WebSocket events
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  ShieldCheck, Certificate, ClockCounterClockwise, Clock,
  Plus, ArrowsClockwise, ListChecks, Gear, CaretRight, 
  User, Globe, SignIn, SignOut, Trash, PencilSimple, 
  UploadSimple, Key, Warning, WifiHigh, Heartbeat, Database, Lightning,
  SlidersHorizontal, Eye, EyeSlash, X
} from '@phosphor-icons/react'
import { Card, Button, Badge, LoadingSpinner, Logo, Modal } from '../components'
// Charts loaded directly to allow proper code splitting (recharts is large)
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
      showError(error.message || 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  // Load version info (public endpoint, only once)
  useEffect(() => {
    const loadVersion = async () => {
      try {
        const response = await fetch('/api/v2/system/updates/version')
        if (response.ok) {
          const data = await response.json()
          setVersionInfo(data.data || { version: '', edition: 'community' })
        }
      } catch {
        // Ignore errors, version display is not critical
      }
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
    if (hour < 12) return 'Good morning'
    if (hour < 18) return 'Good afternoon'
    return 'Good evening'
  }

  const totalCerts = stats?.total_certificates || 0
  const totalCAs = stats?.total_cas || 0
  const pendingCSRs = stats?.pending_csrs || 0
  const acmeAccounts = recentAcme.length
  const expiringCount = expiringCerts.length

  return (
    <div className="flex-1 h-full overflow-y-auto xl:overflow-hidden bg-bg-primary">
      <div className="p-4 space-y-4 max-w-[1800px] mx-auto xl:h-full xl:flex xl:flex-col">
        
        {/* Compact Header Row */}
        <div className="flex flex-wrap items-center gap-4">
          {/* Left: Logo + Version */}
          <div className="flex items-center gap-3">
            <Logo variant="horizontal" size="md" />
            <div className="hidden sm:flex items-center gap-2 pl-3 border-l border-border/50">
              <Badge variant="primary" size="sm">{versionInfo.edition === 'pro' ? 'Pro' : 'Community'}</Badge>
              <span className="text-xs text-text-tertiary">v{versionInfo.version || '2.0.0'}</span>
            </div>
          </div>
          
          <div className="flex-1" />
          
          {/* Right: Status + Actions */}
          <div className="flex items-center gap-3">
            {/* Live Status Pill */}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
              isConnected 
                ? 'bg-accent-success/10 text-accent-success border border-accent-success/20' 
                : 'bg-bg-tertiary text-text-tertiary border border-border'
            }`}>
              <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-current animate-pulse' : 'bg-current'}`} />
              {isConnected ? 'Live' : 'Offline'}
            </div>
            
            {/* Actions */}
            <div className="flex items-center gap-1.5">
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
          </div>
        </div>

        {/* Stats Row - Compact horizontal stats */}
        {widgets.find(w => w.id === 'stats')?.visible && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard icon={Certificate} label="Certificates" value={totalCerts} color="blue" onClick={() => navigate('/certificates')} />
          <StatCard icon={ShieldCheck} label="Authorities" value={totalCAs} color="violet" onClick={() => navigate('/cas')} />
          <StatCard icon={ListChecks} label="CSR Queue" value={pendingCSRs} color={pendingCSRs > 0 ? 'amber' : 'slate'} badge={pendingCSRs > 0 ? 'Pending' : null} onClick={() => navigate('/csrs')} />
          <StatCard icon={Globe} label="ACME" value={acmeAccounts} color="emerald" onClick={() => navigate('/acme')} />
        </div>
        )}
        
        {/* Charts Row - visible on 2xl+ screens only */}
        {widgets.find(w => w.id === 'charts')?.visible && (
        <div className="hidden 2xl:grid grid-cols-2 gap-4">
          {/* Certificate Trend */}
          <Card variant="elevated" className="p-0">
            <Card.Header 
              icon={Lightning}
              iconColor="blue"
              title="Certificate Activity"
              subtitle="Last 7 days"
            />
            <Card.Body className="!pt-0 !pb-2">
              <CertificateTrendChart data={certificateTrend} height={100} />
            </Card.Body>
          </Card>
          
          {/* Status Distribution */}
          <Card variant="elevated" className="p-0">
            <Card.Header 
              icon={Certificate}
              iconColor="violet"
              title="Status Distribution"
              subtitle="Current certificates"
            />
            <Card.Body className="!pt-0 !pb-2">
              <StatusPieChart 
                data={{
                  valid: Math.max(0, (stats?.total_certificates || 0) - (stats?.expiring_soon || 0) - (stats?.revoked || 0)),
                  expiring: stats?.expiring_soon || 0,
                  expired: 0,
                  revoked: stats?.revoked || 0,
                }}
                height={100} 
              />
            </Card.Body>
          </Card>
        </div>
        )}

        {/* Expiring Warning Banner - more elegant */}
        {widgets.find(w => w.id === 'expiring')?.visible && expiringCount > 0 && (
          <button 
            onClick={() => navigate('/certificates?filter=expiring')}
            className="w-full flex items-center gap-3 p-3 rounded-xl bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-transparent border border-amber-500/20 hover:border-amber-500/40 transition-all group"
          >
            <div className="w-9 h-9 rounded-lg bg-amber-500/15 flex items-center justify-center">
              <Warning size={18} weight="fill" className="text-amber-500" />
            </div>
            <div className="flex-1 text-left">
              <p className="text-sm font-medium text-amber-600 dark:text-amber-400">
                {expiringCount} certificate{expiringCount > 1 ? 's' : ''} expiring soon
              </p>
              <p className="text-xs text-text-secondary">Click to view and renew</p>
            </div>
            <CaretRight size={16} className="text-amber-500 opacity-50 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
          </button>
        )}

        {/* Main Content - 2 columns on lg+ */}
        <div className="xl:flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4">
          
          {/* Left: 2x2 Grid for Certs, CAs, System, ACME */}
          <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 sm:grid-rows-2 gap-3 sm:auto-rows-fr">
            
            {/* Recent Certificates */}
            {widgets.find(w => w.id === 'certs')?.visible && (
            <Card variant="elevated" className="flex flex-col p-0">
              <Card.Header 
                icon={Certificate}
                iconColor="blue"
                title="Recent Certificates"
                action={
                  <Button size="sm" variant="ghost" onClick={() => navigate('/certificates')}>
                    View all <CaretRight size={12} />
                  </Button>
                }
              />
              <Card.Body className="flex-1 overflow-y-auto space-y-0.5 !pt-0">
                {recentCerts.length === 0 ? (
                  <EmptyWidget icon={Certificate} text="No certificates yet" />
                ) : (
                  recentCerts.slice(0, 2).map((cert, i) => (
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
                            {cert.common_name || cert.descr || cert.subject || 'Certificate'}
                          </span>
                          <Badge variant={cert.revoked ? 'danger' : 'success'} size="sm" dot>
                            {cert.revoked ? 'Revoked' : 'Valid'}
                          </Badge>
                        </div>
                        <div className="text-xs text-text-tertiary mt-0.5">
                          {formatRelativeTime(cert.created_at)}
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
            <Card variant="elevated" className="flex flex-col  p-0">
              <Card.Header 
                icon={ShieldCheck}
                iconColor="violet"
                title="Recent CAs"
                action={
                  <Button size="sm" variant="ghost" onClick={() => navigate('/cas')}>
                    View all <CaretRight size={12} />
                  </Button>
                }
              />
              <Card.Body className="flex-1 overflow-y-auto space-y-0.5 !pt-0">
                {recentCAs.length === 0 ? (
                  <EmptyWidget icon={ShieldCheck} text="No CAs yet" />
                ) : (
                  recentCAs.slice(0, 2).map((ca, i) => (
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
                          {ca.is_root ? 'Root' : 'Sub'}
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
            <Card variant="elevated" className="flex flex-col  p-0">
              <Card.Header 
                icon={Heartbeat}
                iconColor="emerald"
                title="System Health"
                action={
                  <Button size="sm" variant="ghost" onClick={() => navigate('/settings')}>
                    <Gear size={14} />
                  </Button>
                }
              />
              <Card.Body className="!pt-0 !pb-2">
                <div className="grid grid-cols-2 gap-1.5 mb-2">
                  <SystemStat 
                    icon={WifiHigh} 
                    label="WebSocket" 
                    value={isConnected ? 'Connected' : 'Offline'} 
                    status={isConnected ? 'online' : 'offline'} 
                  />
                  <SystemStat 
                    icon={Database} 
                    label="Database" 
                    value="Healthy" 
                    status="online" 
                  />
                </div>
                <div className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-1.5">
                  Services
                </div>
                <div className="grid grid-cols-4 gap-1.5">
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
            <Card variant="elevated" className="flex flex-col  p-0">
              <Card.Header 
                icon={Globe}
                iconColor="orange"
                title="ACME Accounts"
                action={
                  <Button size="sm" variant="ghost" onClick={() => navigate('/acme')}>
                    View all <CaretRight size={12} />
                  </Button>
                }
              />
              <Card.Body className="flex-1 overflow-y-auto !pt-0">
                {recentAcme.length === 0 ? (
                  <EmptyWidget icon={Globe} text="No ACME accounts" />
                ) : (
                  <div className="space-y-0.5">
                    {recentAcme.slice(0, 2).map((account, i) => (
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
                          <Badge variant="secondary" size="sm">{account.orders_count || 0} orders</Badge>
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
              title="Recent Activity"
              subtitle={isConnected ? "Live updates" : undefined}
              action={
                <div className="flex items-center gap-2">
                  {isConnected && (
                    <Badge variant="success" size="sm" dot pulse>Live</Badge>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => navigate('/audit')}>
                    View all <CaretRight size={12} />
                  </Button>
                </div>
              }
            />
            <Card.Body className="flex-1 overflow-y-auto !pt-0">
              {activityLog.length === 0 ? (
                <EmptyWidget icon={ClockCounterClockwise} text="No recent activity" />
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
                            <span className="text-2xs text-text-secondary font-medium">{activity.user || 'System'}</span>
                            <span className="text-text-tertiary text-2xs">•</span>
                            <span className="text-2xs text-text-tertiary">
                              {formatRelativeTime(activity.timestamp)}
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
                widget.visible ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-tertiary'
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
          <Button size="sm" variant="ghost" onClick={resetToDefaults}>
            Reset to defaults
          </Button>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => onSave(localWidgets)}>
              Save
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

// Enhanced Stat Card with hover effects
function StatCard({ icon: Icon, label, value, color, onClick, badge }) {
  const iconStyles = {
    blue: 'icon-bg-blue',
    violet: 'icon-bg-violet',
    amber: 'icon-bg-amber',
    emerald: 'icon-bg-emerald',
    slate: 'icon-bg-slate',
  }
  
  return (
    <button 
      onClick={onClick}
      className="relative p-3.5 text-left group rounded-xl bg-bg-secondary border border-border/50 hover:border-border hover:shadow-lg transition-all duration-200"
    >
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-105 ${iconStyles[color] || iconStyles.slate}`}>
          <Icon size={20} weight="duotone" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-2xl font-bold text-text-primary tracking-tight tabular-nums">{value}</p>
          <div className="flex items-center gap-2">
            <p className="text-xs text-text-secondary">{label}</p>
            {badge && <Badge variant="warning" size="sm" dot>{badge}</Badge>}
          </div>
        </div>
        <CaretRight size={14} className="text-text-tertiary opacity-0 group-hover:opacity-60 transition-all group-hover:translate-x-0.5" />
      </div>
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
        <span className="text-2xs text-text-tertiary uppercase tracking-wide font-medium">{label}</span>
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
