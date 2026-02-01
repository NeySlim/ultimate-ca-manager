/**
 * Dashboard Page - Live Operational Dashboard with WebSocket
 * Real-time updates via WebSocket events
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  ShieldCheck, Certificate, ClockCounterClockwise, 
  Plus, ArrowsClockwise, ListChecks, Gear, CaretRight, 
  User, Globe, SignIn, SignOut, Trash, PencilSimple, 
  UploadSimple, Key, Warning, WifiHigh,
  Heartbeat, Database, Clock, Lightning
} from '@phosphor-icons/react'
import { Card, Button, Badge, LoadingSpinner, Logo } from '../components'
import { dashboardService, certificatesService, acmeService } from '../services'
import { useNotification } from '../contexts'
import { useWebSocket, EventType } from '../hooks'

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

// Format relative time
const formatRelativeTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const diff = (now - date) / 1000
  
  if (diff < 60) return 'Just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
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
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState(new Date())
  const refreshTimeoutRef = useRef(null)

  // WebSocket for live updates
  const { isConnected, subscribe } = useWebSocket({ showToasts: true })

  const loadDashboard = useCallback(async () => {
    try {
      const [statsData, casData, certsData, activityData, statusData] = await Promise.all([
        dashboardService.getStats(),
        dashboardService.getRecentCAs(5),
        certificatesService.getAll({ limit: 5, sort: 'created_at', order: 'desc' }),
        dashboardService.getActivityLog(10),
        dashboardService.getSystemStatus(),
      ])
      
      setStats(statsData.data || {})
      setRecentCAs(casData.data || [])
      setRecentCerts(certsData.data?.certificates || certsData.data || [])
      setActivityLog(activityData.data?.activity || [])
      setSystemStatus(statusData.data || {})
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
    <div className="flex-1 h-full overflow-auto bg-bg-primary">
      <div className="p-4 space-y-4 max-w-[1800px] mx-auto min-h-full flex flex-col">
        
        {/* Hero Header */}
        <div className="relative overflow-hidden rounded-xl bg-gradient-to-r from-accent-primary/10 via-purple-500/10 to-accent-primary/5 border border-accent-primary/20 p-4">
          <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full bg-accent-primary/5 blur-2xl" />
          
          <div className="relative flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-4">
              <Logo variant="horizontal" size="md" />
              <div className="hidden sm:block w-px h-10 bg-border/50" />
              <div>
                <p className="text-sm text-text-secondary">{getGreeting()} 👋</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <Badge variant="purple" size="sm">Pro</Badge>
                  <span className="text-xs text-text-tertiary">v2.0.3</span>
                  {/* Live Indicator */}
                  <div className="flex items-center gap-1 ml-2">
                    <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-text-tertiary'}`} />
                    <span className={`text-xs ${isConnected ? 'text-emerald-500' : 'text-text-tertiary'}`}>
                      {isConnected ? 'Live' : 'Offline'}
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
                Issue Cert
              </Button>
              <Button size="sm" variant="secondary" onClick={() => navigate('/cas?action=create')}>
                <Plus size={14} weight="bold" />
                Create CA
              </Button>
              <Button size="sm" variant="secondary" onClick={() => navigate('/csrs')}>
                <ListChecks size={14} weight="bold" />
                Sign CSR
              </Button>
              <Button 
                size="sm" 
                variant="ghost" 
                onClick={loadDashboard} 
                title="Refresh"
                className="hidden md:flex"
              >
                <ArrowsClockwise size={14} />
              </Button>
            </div>
          </div>
        </div>

        {/* Stats Row - Now with colors and live indicators */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard 
            icon={Certificate}
            label="Certificates"
            value={totalCerts}
            color="blue"
            live={isConnected}
            onClick={() => navigate('/certificates')}
          />
          <StatCard 
            icon={ShieldCheck}
            label="Authorities"
            value={totalCAs}
            color="purple"
            live={isConnected}
            onClick={() => navigate('/cas')}
          />
          <StatCard 
            icon={ListChecks}
            label="CSR Queue"
            value={pendingCSRs}
            color={pendingCSRs > 0 ? 'yellow' : 'slate'}
            badge={pendingCSRs > 0 ? 'Pending' : null}
            onClick={() => navigate('/csrs')}
          />
          <StatCard 
            icon={Globe}
            label="ACME Accounts"
            value={acmeAccounts}
            color="emerald"
            onClick={() => navigate('/acme')}
          />
        </div>

        {/* Expiring Certs Warning Banner */}
        {expiringCount > 0 && (
          <div 
            onClick={() => navigate('/certificates?filter=expiring')}
            className="flex items-center gap-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 cursor-pointer hover:bg-amber-500/15 transition-colors"
          >
            <div className="w-8 h-8 rounded-lg bg-amber-500/20 flex items-center justify-center">
              <Warning size={18} weight="fill" className="text-amber-500" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-500">
                {expiringCount} certificate{expiringCount > 1 ? 's' : ''} expiring soon
              </p>
              <p className="text-xs text-text-secondary">Click to view and renew</p>
            </div>
            <CaretRight size={16} className="text-amber-500" />
          </div>
        )}

        {/* Main Content - 3 Column Layout */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-0">
          
          {/* Recent Certificates & CAs */}
          <Card variant="elevated" className="flex flex-col min-h-[320px] p-0">
            <Card.Header 
              icon={Certificate} 
              title="Recent Certificates"
              action={
                <Button size="sm" variant="ghost" onClick={() => navigate('/certificates')}>
                  View all <CaretRight size={12} />
                </Button>
              }
            />
            <Card.Body className="flex-1 overflow-y-auto space-y-1 !pt-0">
              {recentCerts.length === 0 ? (
                <EmptyWidget icon={Certificate} text="No certificates yet" />
              ) : (
                recentCerts.slice(0, 5).map((cert, i) => (
                  <div 
                    key={cert.id || i}
                    onClick={() => navigate(`/certificates/${cert.id}`)}
                    className="p-2.5 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-all border border-transparent hover:border-border/50 hover:shadow-sm group"
                  >
                    <div className="flex items-center justify-between">
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
                ))
              )}
            </Card.Body>
            
            {/* Recent CAs Section */}
            <Card.Footer>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-lg bg-purple-500/15 flex items-center justify-center">
                    <ShieldCheck size={12} weight="duotone" className="text-purple-500 dark:text-purple-400" />
                  </div>
                  <span className="text-xs font-semibold text-text-primary">Recent CAs</span>
                </div>
                <Button size="sm" variant="ghost" onClick={() => navigate('/cas')}>
                  <CaretRight size={12} />
                </Button>
              </div>
              {recentCAs.length === 0 ? (
                <p className="text-xs text-text-tertiary py-2">No CAs yet</p>
              ) : (
                <div className="space-y-1">
                  {recentCAs.slice(0, 3).map((ca, i) => (
                    <div 
                      key={ca.id || i}
                      onClick={() => navigate(`/cas/${ca.id}`)}
                      className="flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-bg-secondary cursor-pointer transition-colors"
                    >
                      <span className="text-xs text-text-primary truncate">{ca.dn_commonname || ca.descr || ca.name}</span>
                      <Badge variant={ca.is_root ? 'purple' : 'info'} size="sm">
                        {ca.is_root ? 'Root' : 'Intermediate'}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </Card.Footer>
          </Card>

          {/* System Health & Services */}
          <Card variant="elevated" className="flex flex-col min-h-[320px] p-0">
            <Card.Header 
              icon={Heartbeat} 
              title="System Health"
              action={
                <Button size="sm" variant="ghost" onClick={() => navigate('/settings')}>
                  <Gear size={14} />
                </Button>
              }
            />
            <Card.Body className="!pt-0">
              {/* System Stats */}
              <div className="grid grid-cols-2 gap-2 mb-3">
                <SystemStat 
                  icon={WifiHigh} 
                  label="WebSocket" 
                  value={isConnected ? 'Connected' : 'Disconnected'} 
                  status={isConnected ? 'online' : 'offline'} 
                />
                <SystemStat 
                  icon={Database} 
                  label="Database" 
                  value="Healthy" 
                  status="online" 
                />
                <SystemStat 
                  icon={Clock} 
                  label="Last Update" 
                  value={formatRelativeTime(lastUpdate)} 
                  status="online" 
                />
                <SystemStat 
                  icon={Lightning} 
                  label="API" 
                  value="Online" 
                  status="online" 
                />
              </div>
              
              {/* Services Status */}
              <div>
                <div className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-2">
                  Services
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <ServiceBadge name="ACME" status={systemStatus?.acme} />
                  <ServiceBadge name="SCEP" status={systemStatus?.scep} />
                  <ServiceBadge name="OCSP" status={systemStatus?.ocsp} />
                  <ServiceBadge name="CRL" status={systemStatus?.crl} />
                </div>
              </div>
            </Card.Body>
            
            <Card.Footer>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-lg bg-blue-500/15 flex items-center justify-center">
                    <Globe size={12} weight="duotone" className="text-blue-500 dark:text-blue-400" />
                  </div>
                  <span className="text-xs font-semibold text-text-primary">ACME Accounts</span>
                </div>
                <Button size="sm" variant="ghost" onClick={() => navigate('/acme')}>
                  <CaretRight size={12} />
                </Button>
              </div>
              {recentAcme.length === 0 ? (
                <p className="text-xs text-text-tertiary py-2">No ACME accounts</p>
              ) : (
                <div className="space-y-1">
                  {recentAcme.slice(0, 2).map((account, i) => (
                    <div key={account.id || i} className="flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-bg-secondary transition-colors">
                      <User size={12} className="text-text-tertiary" />
                      <span className="text-xs text-text-primary truncate flex-1">{account.email || account.contact}</span>
                      <Badge variant="secondary" size="sm">{account.orders_count || 0} orders</Badge>
                    </div>
                  ))}
                </div>
              )}
            </Card.Footer>
          </Card>

          {/* Recent Activity with Live Indicator */}
          <Card variant="elevated" className="flex flex-col min-h-[320px] p-0">
            <Card.Header 
              icon={ClockCounterClockwise} 
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
                            ? 'bg-red-500/15 text-red-500 dark:text-red-400' 
                            : isSuccess 
                              ? 'bg-emerald-500/15 text-emerald-500 dark:text-emerald-400'
                              : 'bg-accent-primary/15 text-accent-primary'
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
        </div>

      </div>
    </div>
  )
}

// Enhanced Stat Card with live indicator
function StatCard({ icon: Icon, label, value, color, onClick, live, badge }) {
  const colors = {
    blue: {
      card: 'bg-gradient-to-br from-blue-500/5 to-blue-500/10 border-blue-500/20 hover:border-blue-500/40 shadow-sm shadow-blue-500/5',
      icon: 'bg-blue-500/15 text-blue-500 dark:text-blue-400',
      ring: 'ring-blue-500/20'
    },
    purple: {
      card: 'bg-gradient-to-br from-purple-500/5 to-purple-500/10 border-purple-500/20 hover:border-purple-500/40 shadow-sm shadow-purple-500/5',
      icon: 'bg-purple-500/15 text-purple-500 dark:text-purple-400',
      ring: 'ring-purple-500/20'
    },
    yellow: {
      card: 'bg-gradient-to-br from-amber-500/5 to-amber-500/10 border-amber-500/20 hover:border-amber-500/40 shadow-sm shadow-amber-500/5',
      icon: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
      ring: 'ring-amber-500/20'
    },
    emerald: {
      card: 'bg-gradient-to-br from-emerald-500/5 to-emerald-500/10 border-emerald-500/20 hover:border-emerald-500/40 shadow-sm shadow-emerald-500/5',
      icon: 'bg-emerald-500/15 text-emerald-500 dark:text-emerald-400',
      ring: 'ring-emerald-500/20'
    },
    slate: {
      card: 'bg-bg-secondary border-border/60 hover:border-border shadow-sm',
      icon: 'bg-bg-tertiary text-text-secondary',
      ring: 'ring-border/50'
    },
  }
  
  const style = colors[color] || colors.slate
  
  return (
    <button 
      onClick={onClick}
      className={`
        relative p-4 rounded-xl border transition-all duration-200 text-left group
        hover:shadow-md hover:-translate-y-0.5 active:scale-[0.98]
        ${style.card}
      `}
    >
      {/* Live indicator */}
      {live && (
        <div className="absolute top-3 right-3 flex items-center gap-1.5">
          <span className="text-[10px] text-emerald-500 font-medium opacity-0 group-hover:opacity-100 transition-opacity">Live</span>
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-sm shadow-emerald-500/50" />
        </div>
      )}
      
      <div className="flex items-center gap-3">
        <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${style.icon}`}>
          <Icon size={24} weight="duotone" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-2xl font-bold text-text-primary tracking-tight">{value}</p>
            {badge && (
              <Badge variant="warning" size="sm" dot pulse>{badge}</Badge>
            )}
          </div>
          <p className="text-xs text-text-secondary font-medium">{label}</p>
        </div>
      </div>
    </button>
  )
}

// System Stat mini card
function SystemStat({ icon: Icon, label, value, status }) {
  return (
    <div className={`px-3 py-2 rounded-lg border transition-all duration-200 ${
      status === 'online' 
        ? 'bg-gradient-to-br from-emerald-500/5 to-emerald-500/10 border-emerald-500/20 hover:border-emerald-500/40' 
        : 'bg-gradient-to-br from-red-500/5 to-red-500/10 border-red-500/20 hover:border-red-500/40'
    }`}>
      <div className="flex items-center gap-2">
        <div className={`w-5 h-5 rounded flex items-center justify-center ${
          status === 'online' ? 'bg-emerald-500/15' : 'bg-red-500/15'
        }`}>
          <Icon size={12} className={status === 'online' ? 'text-emerald-500 dark:text-emerald-400' : 'text-red-500 dark:text-red-400'} weight="bold" />
        </div>
        <span className="text-[10px] text-text-tertiary uppercase tracking-wide">{label}</span>
      </div>
      <p className={`text-xs font-semibold mt-1 ${
        status === 'online' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
      }`}>{value}</p>
    </div>
  )
}

// Service Badge Component
function ServiceBadge({ name, status }) {
  const isOnline = status?.status === 'online' || status?.enabled
  return (
    <div className={`px-3 py-2.5 rounded-lg border text-center transition-all duration-200 ${
      isOnline 
        ? 'bg-gradient-to-br from-emerald-500/5 to-emerald-500/10 border-emerald-500/20 hover:border-emerald-500/40 hover:shadow-sm hover:shadow-emerald-500/10' 
        : 'bg-bg-tertiary border-border hover:border-text-tertiary/30'
    }`}>
      <div className="flex items-center justify-center gap-2">
        <div className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-500 animate-pulse' : 'bg-text-tertiary'}`} />
        <span className={`text-xs font-semibold ${isOnline ? 'text-text-primary' : 'text-text-secondary'}`}>{name}</span>
      </div>
    </div>
  )
}

// Empty Widget Component
function EmptyWidget({ icon: Icon, text }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary py-8">
      <div className="w-12 h-12 rounded-xl bg-bg-tertiary/50 flex items-center justify-center mb-3">
        <Icon size={24} className="opacity-40" />
      </div>
      <p className="text-xs font-medium">{text}</p>
    </div>
  )
}
