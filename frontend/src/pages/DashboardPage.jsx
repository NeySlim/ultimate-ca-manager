/**
 * Dashboard Page
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  ShieldCheck, Certificate, Warning, ClockCounterClockwise, 
  Plus, FileArrowUp, Clock
} from '@phosphor-icons/react'
import { 
  ExplorerPanel, DetailsPanel, Card, Button, Table, 
  Badge, StatusIndicator, LoadingSpinner, EmptyState 
} from '../components'
import { dashboardService, systemService } from '../services'
import { useNotification } from '../contexts'

export default function DashboardPage() {
  const { showError } = useNotification()
  const navigate = useNavigate()
  
  const [stats, setStats] = useState(null)
  const [expiringCerts, setExpiringCerts] = useState([])
  const [recentCAs, setRecentCAs] = useState([])
  const [activityLog, setActivityLog] = useState([])
  const [systemStatus, setSystemStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadDashboard()
  }, [])

  const loadDashboard = async () => {
    setLoading(true)
    try {
      const [statsData, expiringData, casData, activityData, statusData] = await Promise.all([
        dashboardService.getStats(),
        dashboardService.getExpiringCerts(30),
        dashboardService.getRecentCAs(5),
        dashboardService.getActivityLog(20),
        dashboardService.getSystemStatus(),
      ])
      
      // API returns {data: {...}} for all endpoints
      setStats(statsData.data || {})
      setExpiringCerts(expiringData.data || [])
      setRecentCAs(casData.data || [])
      setActivityLog(activityData.data?.activity || [])  // activity is nested
      setSystemStatus(statusData.data || {})
    } catch (error) {
      showError(error.message || 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }

  const certColumns = [
    { key: 'common_name', label: 'Common Name' },
    { key: 'issuer', label: 'Issuer' },
    { 
      key: 'valid_to', 
      label: 'Expires',
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <span>{val ? new Date(val).toLocaleDateString() : 'N/A'}</span>
          {row.days_left <= 7 && (
            <Badge variant="danger" size="sm">{row.days_left}d</Badge>
          )}
          {row.days_left > 7 && row.days_left <= 30 && (
            <Badge variant="warning" size="sm">{row.days_left}d</Badge>
          )}
        </div>
      )
    },
    {
      key: 'status',
      label: 'Status',
      render: (val) => (
        <div className="flex items-center gap-2">
          <StatusIndicator status={val} />
          <span className="text-sm">{val}</span>
        </div>
      )
    }
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message="Loading dashboard..." />
      </div>
    )
  }

  return (
    <>
      <ExplorerPanel
        title="Activity"
        footer={
          <div className="text-xs text-text-secondary">
            Last updated: {new Date().toLocaleTimeString()}
          </div>
        }
      >
        <div className="p-4 space-y-2">
          {activityLog.length === 0 ? (
            <EmptyState 
              icon={ClockCounterClockwise}
              title="No activity"
              description="Recent activities will appear here"
            />
          ) : (
            activityLog.map((activity, index) => (
              <div 
                key={index}
                className="flex gap-3 p-3 bg-bg-tertiary rounded-lg hover:bg-bg-tertiary/80 transition-colors"
              >
                <div className="flex-shrink-0 mt-1">
                  <ClockCounterClockwise size={16} className="text-accent-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-text-primary truncate">{activity.message}</p>
                  <p className="text-xs text-text-secondary mt-1">
                    {new Date(activity.timestamp).toLocaleString()}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </ExplorerPanel>

      <DetailsPanel
      >
        <div className="space-y-6">
          {/* System Overview Stats */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center">
                  <ShieldCheck size={24} weight="duotone" className="text-blue-500" />
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase tracking-wide">Total CAs</p>
                  <p className="text-xl font-bold text-text-primary">{stats?.total_cas || 0}</p>
                </div>
              </div>
            </Card>

            <Card>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-green-500/10 flex items-center justify-center">
                  <Certificate size={24} weight="duotone" className="text-green-500" />
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase tracking-wide">Certificates</p>
                  <p className="text-xl font-bold text-text-primary">{stats?.total_certificates || 0}</p>
                </div>
              </div>
            </Card>

            <Card>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-orange-500/10 flex items-center justify-center">
                  <Warning size={24} weight="duotone" className="text-orange-500" />
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase tracking-wide">Expiring Soon</p>
                  <p className="text-xl font-bold text-orange-500">{stats?.expiring_certificates || 0}</p>
                </div>
              </div>
            </Card>

            <Card>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center">
                  <Clock size={24} weight="duotone" className="text-purple-500" />
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase tracking-wide">System Status</p>
                  <div className="flex items-center gap-2 mt-1">
                    <StatusIndicator status={systemStatus?.status === 'healthy' ? 'active' : 'inactive'} pulse />
                    <span className="text-sm font-medium text-text-primary">
                      {systemStatus?.status || 'Unknown'}
                    </span>
                  </div>
                </div>
              </div>
            </Card>
          </div>

          {/* Quick Actions */}
          <Card>
            <h3 className="text-sm font-semibold text-text-primary mb-4">Quick Actions</h3>
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => navigate('/certificates?action=create')}>
                <Certificate size={18} />
                Issue Certificate
              </Button>
              <Button variant="secondary" onClick={() => navigate('/cas?action=create')}>
                <ShieldCheck size={18} />
                Create CA
              </Button>
              <Button variant="secondary" onClick={() => navigate('/csrs?action=upload')}>
                <FileArrowUp size={18} />
                Upload CSR
              </Button>
              <Button variant="ghost" onClick={() => navigate('/settings')}>
                <ClockCounterClockwise size={18} />
                View Activity
              </Button>
            </div>
          </Card>

          {/* Expiring Certificates */}
          <Card>
            <h3 className="text-sm font-semibold text-text-primary mb-4">
              Expiring Certificates (Next 30 Days)
            </h3>
            {expiringCerts.length === 0 ? (
              <EmptyState
                title="No expiring certificates"
                description="All certificates are valid for more than 30 days"
              />
            ) : (
              <Table
                columns={certColumns}
                data={expiringCerts}
                onRowClick={(row) => navigate(`/certificates?id=${row.id}`)}
              />
            )}
          </Card>

          {/* Recent CAs */}
          <Card>
            <h3 className="text-sm font-semibold text-text-primary mb-4">Recent Certificate Authorities</h3>
            {recentCAs.length === 0 ? (
              <EmptyState
                title="No CAs yet"
                description="Create your first Certificate Authority to get started"
                action={{
                  label: 'Create CA',
                  onClick: () => navigate('/cas')
                }}
              />
            ) : (
              <div className="space-y-3">
                {recentCAs.map((ca) => (
                  <div
                    key={ca.id}
                    className="flex items-center gap-4 p-4 bg-bg-tertiary rounded-xl hover:bg-bg-tertiary/80 transition-colors cursor-pointer"
                    onClick={() => navigate(`/cas?id=${ca.id}`)}
                  >
                    <ShieldCheck size={32} weight="duotone" className="text-accent-primary" />
                    <div className="flex-1">
                      <p className="font-medium text-text-primary">{ca.name}</p>
                      <p className="text-sm text-text-secondary">{ca.subject}</p>
                    </div>
                    <Badge variant={ca.type === 'root' ? 'primary' : 'secondary'}>
                      {ca.type}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </DetailsPanel>
    </>
  )
}
