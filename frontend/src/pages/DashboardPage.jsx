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
          <Card className="flex flex-col min-h-[320px]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Certificate size={14} weight="duotone" className="text-blue-400" />
                </div>
                <h2 className="text-sm font-semibold text-text-primary">Recent Certificates</h2>
              </div>
              <Button size="sm" variant="ghost" onClick={() => navigate('/certificates')}>
                <CaretRight size={12} />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto space-y-1">
              {recentCerts.length === 0 ? (
                <EmptyWidget icon={Certificate} text="No certificates yet" />
              ) : (
                recentCerts.slice(0, 5).map((cert, i) => (
                  <div 
                    key={cert.id || i}
                    onClick={() => navigate(`/certificates/${cert.id}`)}
                    className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors border border-transparent hover:border-border"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-text-primary truncate">
                        {cert.common_name || cert.descr || cert.subject || 'Certificate'}
                      </span>
                      <Badge variant={cert.revoked ? 'danger' : 'emerald'} size="sm">
                        {cert.revoked ? 'Revoked' : 'Valid'}
                      </Badge>
                    </div>
                    <div className="text-xs text-text-tertiary mt-0.5">
                      {formatRelativeTime(cert.created_at)}
                    </div>
                  </div>
                ))
              )}
            </div>
            
            {/* Recent CAs Section */}
            <div className="border-t border-border mt-3 pt-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded bg-purple-500/10 flex items-center justify-center">
                    <ShieldCheck size={12} weight="duotone" className="text-purple-400" />
                  </div>
                  <span className="text-xs font-medium text-text-secondary">Recent CAs</span>
                </div>
                <Button size="sm" variant="ghost" onClick={() => navigate('/cas')}>
                  <CaretRight size={10} />
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
                      className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-bg-tertiary/50 cursor-pointer"
                    >
                      <span className="text-xs text-text-primary truncate">{ca.dn_commonname || ca.descr || ca.name}</span>
                      <Badge variant={ca.is_root ? 'purple' : 'blue'} size="sm">
                        {ca.is_root ? 'Root' : 'Int'}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* System Health & Services */}
          <Card className="flex flex-col min-h-[320px]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <Heartbeat size={14} weight="duotone" className="text-emerald-400" />
                </div>
                <h2 className="text-sm font-semibold text-text-primary">System Health</h2>
              </div>
              <Button size="sm" variant="ghost" onClick={() => navigate('/settings')}>
                <Gear size={12} />
              </Button>
            </div>
            
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
            <div className="flex-1">
              <div className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-2">
                Services
              </div>
              <div className="grid grid-cols-2 gap-2">
                <ServiceBadge name="ACME" status={systemStatus?.acme} />
                <ServiceBadge name="SCEP" status={systemStatus?.scep} />
                <ServiceBadge name="OCSP" status={systemStatus?.ocsp} />
                <ServiceBadge name="CRL" status={systemStatus?.crl} />
              </div>
              
              {/* ACME Quick Stats */}
              <div className="mt-3 pt-3 border-t border-border">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-text-secondary">ACME Accounts</span>
                  <Button size="sm" variant="ghost" onClick={() => navigate('/acme')}>
                    <CaretRight size={10} />
                  </Button>
                </div>
                {recentAcme.length === 0 ? (
                  <p className="text-xs text-text-tertiary py-2">No ACME accounts</p>
                ) : (
                  <div className="space-y-1">
                    {recentAcme.slice(0, 2).map((account, i) => (
                      <div key={account.id || i} className="flex items-center gap-2 py-1.5">
                        <User size={12} className="text-text-tertiary" />
                        <span className="text-xs text-text-primary truncate flex-1">{account.email || account.contact}</span>
                        <span className="text-[10px] text-text-tertiary">{account.orders_count || 0} orders</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </Card>

          {/* Recent Activity with Live Indicator */}
          <Card className="flex flex-col min-h-[320px]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-accent-primary/10 flex items-center justify-center">
                  <ClockCounterClockwise size={14} weight="duotone" className="text-accent-primary" />
                </div>
                <h2 className="text-sm font-semibold text-text-primary">Recent Activity</h2>
                {/* Live pulse indicator */}
                {isConnected && (
                  <div className="flex items-center gap-1 ml-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-[10px] text-emerald-500 font-medium">LIVE</span>
                  </div>
                )}
              </div>
              <Button size="sm" variant="ghost" onClick={() => navigate('/audit')}>
                View All
                <CaretRight size={12} />
              </Button>
            </div>
            
            {activityLog.length === 0 ? (
              <EmptyWidget icon={ClockCounterClockwise} text="No recent activity" />
            ) : (
              <div className="flex-1 overflow-y-auto space-y-0.5">
                {activityLog.map((activity, i) => {
                  const Icon = actionIcons[activity.action] || actionIcons.default
                  const isError = activity.action === 'login_failed' || activity.action === 'revoke'
                  const isSuccess = activity.action === 'login_success' || activity.action === 'create'
                  return (
                    <div 
                      key={activity.id || i}
                      className="flex items-start gap-2 py-2 px-2 rounded-lg hover:bg-bg-tertiary/30 transition-colors"
                    >
                      <div className={`w-6 h-6 rounded flex items-center justify-center flex-shrink-0 mt-0.5 ${
                        isError 
                          ? 'bg-red-500/10 text-red-400' 
                          : isSuccess 
                            ? 'bg-emerald-500/10 text-emerald-400'
                            : 'bg-accent-primary/10 text-accent-primary'
                      }`}>
                        <Icon size={12} weight="bold" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-text-primary leading-tight truncate">
                          {activity.message || `${activity.action} ${activity.resource_type || ''}`}
                        </p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span className="text-[10px] text-text-secondary">{activity.user || 'System'}</span>
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
          </Card>
        </div>

      </div>
    </div>
  )
}

// Enhanced Stat Card with live indicator
function StatCard({ icon: Icon, label, value, color, onClick, live, badge }) {
  const colors = {
    blue: 'text-blue-400 bg-blue-500/10 border-blue-500/20 hover:bg-blue-500/15 hover:border-blue-500/30',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20 hover:bg-purple-500/15 hover:border-purple-500/30',
    yellow: 'text-amber-400 bg-amber-500/10 border-amber-500/20 hover:bg-amber-500/15 hover:border-amber-500/30',
    orange: 'text-orange-400 bg-orange-500/10 border-orange-500/20 hover:bg-orange-500/15 hover:border-orange-500/30',
    emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20 hover:bg-emerald-500/15 hover:border-emerald-500/30',
    slate: 'text-text-secondary bg-bg-tertiary border-border hover:bg-bg-tertiary/80',
  }
  
  return (
    <button 
      onClick={onClick}
      className={`relative p-4 rounded-xl border transition-all hover:scale-[1.02] active:scale-[0.98] text-left ${colors[color]}`}
    >
      {/* Live indicator dot */}
      {live && (
        <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
      )}
      
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 rounded-xl bg-current/10 flex items-center justify-center flex-shrink-0">
          <Icon size={22} weight="duotone" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <p className="text-2xl font-bold text-text-primary">{value}</p>
            {badge && (
              <Badge variant="yellow" size="sm">{badge}</Badge>
            )}
          </div>
          <p className="text-xs text-text-secondary">{label}</p>
        </div>
      </div>
    </button>
  )
}

// System Stat mini card
function SystemStat({ icon: Icon, label, value, status }) {
  return (
    <div className={`px-3 py-2 rounded-lg border ${
      status === 'online' 
        ? 'bg-emerald-500/5 border-emerald-500/20' 
        : 'bg-red-500/5 border-red-500/20'
    }`}>
      <div className="flex items-center gap-2">
        <Icon size={14} className={status === 'online' ? 'text-emerald-400' : 'text-red-400'} />
        <span className="text-[10px] text-text-tertiary uppercase">{label}</span>
      </div>
      <p className={`text-xs font-medium mt-0.5 ${
        status === 'online' ? 'text-emerald-400' : 'text-red-400'
      }`}>{value}</p>
    </div>
  )
}

// Service Badge Component
function ServiceBadge({ name, status }) {
  const isOnline = status?.status === 'online' || status?.enabled
  return (
    <div className={`px-3 py-2.5 rounded-lg border text-center transition-colors ${
      isOnline 
        ? 'bg-emerald-500/10 border-emerald-500/20 hover:bg-emerald-500/15' 
        : 'bg-bg-tertiary border-border hover:bg-bg-tertiary/80'
    }`}>
      <div className="flex items-center justify-center gap-1.5">
        <div className={`w-1.5 h-1.5 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-text-tertiary'}`} />
        <span className="text-xs font-medium text-text-primary">{name}</span>
      </div>
    </div>
  )
}

// Empty Widget Component
function EmptyWidget({ icon: Icon, text }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary py-8">
      <Icon size={28} className="opacity-30 mb-2" />
      <p className="text-xs">{text}</p>
    </div>
  )
}
