/**
 * Dashboard Page - Operational Dashboard
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  ShieldCheck, Certificate, ClockCounterClockwise, 
  Plus, FileArrowDown, FileArrowUp, ArrowsClockwise,
  ListChecks, Gear, CaretRight, User, Globe, Key,
  SignIn, SignOut, Trash, PencilSimple, UploadSimple
} from '@phosphor-icons/react'
import { Card, Button, Badge, LoadingSpinner, Logo } from '../components'
import { dashboardService, casService, certificatesService, acmeService, scepService } from '../services'
import { useNotification } from '../contexts'

// Action icons mapping
const actionIcons = {
  login_success: SignIn,
  login_failed: SignIn,
  logout: SignOut,
  create: Plus,
  update: PencilSimple,
  delete: Trash,
  revoke: ClockCounterClockwise,
  export: FileArrowUp,
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
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadDashboard()
  }, [])

  const loadDashboard = async () => {
    setLoading(true)
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
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message="Loading dashboard..." />
      </div>
    )
  }

  // Get greeting based on time
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

  return (
    <div className="flex-1 h-full overflow-auto bg-bg-primary">
      <div className="p-4 space-y-4 max-w-[1800px] mx-auto min-h-full flex flex-col">
        
        {/* Hero Header with gradient */}
        <div className="relative overflow-hidden rounded-xl bg-gradient-to-r from-accent-primary/10 via-purple-500/10 to-accent-primary/5 border border-accent-primary/20 p-5">
          {/* Decorative circles */}
          <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full bg-accent-primary/5 blur-2xl" />
          <div className="absolute -right-5 -bottom-10 w-32 h-32 rounded-full bg-purple-500/5 blur-2xl" />
          
          <div className="relative flex flex-wrap items-center gap-4">
            {/* App Info */}
            <div className="flex items-center gap-4">
              <Logo variant="horizontal" size="md" />
              <div className="hidden sm:block w-px h-10 bg-border/50" />
              <div>
                <p className="text-sm text-text-secondary">{getGreeting()} 👋</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <Badge variant="purple" size="sm">Pro</Badge>
                  <span className="text-xs text-text-tertiary">v2.0.0</span>
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
              <div className="hidden md:flex items-center gap-2 ml-2">
                <Button size="sm" variant="ghost" onClick={() => navigate('/import')}>
                  <FileArrowDown size={14} />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => navigate('/import')}>
                  <FileArrowUp size={14} />
                </Button>
                <Button size="sm" variant="ghost" onClick={loadDashboard} title="Refresh">
                  <ArrowsClockwise size={14} />
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard 
            icon={Certificate}
            label="Certificates"
            value={totalCerts}
            color="blue"
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
            color={pendingCSRs > 0 ? 'yellow' : 'slate'}
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

        {/* Main Content - 3 Column Layout */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-0">
          
          {/* Recent Certificates & CAs */}
          <Card className="flex flex-col min-h-[300px]">
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
                        {cert.common_name || cert.subject || 'Certificate'}
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
                      <span className="text-xs text-text-primary truncate">{ca.common_name || ca.descr}</span>
                      <Badge variant={ca.is_root ? 'purple' : 'blue'} size="sm">
                        {ca.is_root ? 'Root' : 'Int'}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* Protocol Activity - ACME & SCEP */}
          <Card className="flex flex-col min-h-[300px]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <Globe size={14} weight="duotone" className="text-emerald-400" />
                </div>
                <h2 className="text-sm font-semibold text-text-primary">Protocol Activity</h2>
              </div>
              <Button size="sm" variant="ghost" onClick={() => navigate('/settings')}>
                <Gear size={12} />
              </Button>
            </div>
            
            {/* Services Status */}
            <div className="grid grid-cols-2 gap-2 mb-4">
              <ServiceBadge name="ACME" status={systemStatus?.acme} />
              <ServiceBadge name="SCEP" status={systemStatus?.scep} />
              <ServiceBadge name="OCSP" status={systemStatus?.ocsp} />
              <ServiceBadge name="CRL" status={systemStatus?.crl} />
            </div>
            
            {/* ACME Accounts */}
            <div className="flex-1 overflow-y-auto">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-text-secondary uppercase tracking-wide">ACME Accounts</span>
                <Button size="sm" variant="ghost" onClick={() => navigate('/acme')}>
                  <CaretRight size={10} />
                </Button>
              </div>
              {recentAcme.length === 0 ? (
                <EmptyWidget icon={Globe} text="No ACME accounts" small />
              ) : (
                <div className="space-y-1">
                  {recentAcme.map((account, i) => (
                    <div 
                      key={account.id || i}
                      className="p-2 rounded-lg bg-bg-tertiary/30 border border-border/50"
                    >
                      <div className="flex items-center gap-2">
                        <User size={12} className="text-text-tertiary" />
                        <span className="text-xs text-text-primary truncate">{account.email || account.contact}</span>
                      </div>
                      <div className="text-[10px] text-text-tertiary mt-1">
                        {account.orders_count || 0} orders • {formatRelativeTime(account.created_at)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* Recent Activity */}
          <Card className="flex flex-col min-h-[300px]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-accent-primary/10 flex items-center justify-center">
                  <ClockCounterClockwise size={14} weight="duotone" className="text-accent-primary" />
                </div>
                <h2 className="text-sm font-semibold text-text-primary">Recent Activity</h2>
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

// Stat Card Component
function StatCard({ icon: Icon, label, value, color, onClick }) {
  const colors = {
    blue: 'text-blue-400 bg-blue-500/10 border-blue-500/20 hover:bg-blue-500/15',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20 hover:bg-purple-500/15',
    yellow: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20 hover:bg-yellow-500/15',
    orange: 'text-orange-400 bg-orange-500/10 border-orange-500/20 hover:bg-orange-500/15',
    emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20 hover:bg-emerald-500/15',
    slate: 'text-text-secondary bg-bg-tertiary border-border hover:bg-bg-tertiary/80',
  }
  
  return (
    <button 
      onClick={onClick}
      className={`p-4 rounded-lg border transition-all hover:scale-[1.01] active:scale-[0.99] text-left ${colors[color]}`}
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-current/10 flex items-center justify-center flex-shrink-0">
          <Icon size={20} weight="duotone" />
        </div>
        <div>
          <p className="text-2xl font-bold text-text-primary">{value}</p>
          <p className="text-xs text-text-secondary">{label}</p>
        </div>
      </div>
    </button>
  )
}

// Service Badge Component
function ServiceBadge({ name, status }) {
  const isOnline = status?.status === 'online' || status?.enabled
  return (
    <div className={`px-3 py-2 rounded-lg border text-center ${
      isOnline 
        ? 'bg-emerald-500/10 border-emerald-500/20' 
        : 'bg-bg-tertiary border-border'
    }`}>
      <div className="flex items-center justify-center gap-1.5">
        <div className={`w-1.5 h-1.5 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-text-tertiary'}`} />
        <span className="text-xs font-medium text-text-primary">{name}</span>
      </div>
    </div>
  )
}

// Empty Widget Component
function EmptyWidget({ icon: Icon, text, small }) {
  return (
    <div className={`flex-1 flex flex-col items-center justify-center text-text-tertiary ${small ? 'py-4' : 'py-8'}`}>
      <Icon size={small ? 20 : 28} className="opacity-30 mb-2" />
      <p className="text-xs">{text}</p>
    </div>
  )
}
