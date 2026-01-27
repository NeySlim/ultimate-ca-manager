import { useState, useEffect } from 'react'
import { Certificate, Shield, Clock, FileText } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [activity, setActivity] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  useEffect(() => {
    fetchDashboard()
  }, [])
  
  async function fetchDashboard() {
    try {
      setLoading(true)
      setError(null)
      
      const [statsData, activityData] = await Promise.all([
        api.getDashboardStats().catch(() => null),
        api.getActivityLog(10).catch(() => [])
      ])
      
      setStats(statsData || {})
      setActivity(activityData || [])
    } catch (err) {
      console.error('Dashboard error:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading dashboard..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchDashboard} />
  
  return (
    <div className="dashboard-page">
      <h1>Dashboard</h1>
      <p className="subtitle">Overview of your PKI infrastructure</p>
      
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">
            <Certificate size={24} weight="duotone" />
          </div>
          <div className="stat-content">
            <div className="stat-value">{stats.total_certificates || 0}</div>
            <div className="stat-label">Total Certificates</div>
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-icon green">
            <Shield size={24} weight="duotone" />
          </div>
          <div className="stat-content">
            <div className="stat-value">{stats.active_cas || 0}</div>
            <div className="stat-label">Active CAs</div>
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-icon orange">
            <Clock size={24} weight="duotone" />
          </div>
          <div className="stat-content">
            <div className="stat-value">{stats.expiring_soon || 0}</div>
            <div className="stat-label">Expiring Soon</div>
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-icon red">
            <FileText size={24} weight="duotone" />
          </div>
          <div className="stat-content">
            <div className="stat-value">{stats.revoked_certificates || 0}</div>
            <div className="stat-label">Revoked</div>
          </div>
        </div>
      </div>
      
      <div className="dashboard-grid">
        <div className="activity-section">
          <h2>Recent Activity</h2>
          {activity.length === 0 ? (
            <p className="empty-message">No recent activity</p>
          ) : (
            <div className="activity-feed">
              {activity.map((item, i) => (
                <div key={item.id || i} className="activity-item">
                  <div className={`activity-dot ${item.type || 'default'}`}></div>
                  <div className="activity-content">
                    <p className="activity-text">{item.message || item.description}</p>
                    <span className="activity-time">{item.timestamp || item.created_at}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        <div className="status-sidebar">
          <h2>System Status</h2>
          <div className="status-item">
            <div className="status-indicator green"></div>
            <span>API Server</span>
            <span className="status-value">Online</span>
          </div>
          <div className="status-item">
            <div className="status-indicator green"></div>
            <span>Database</span>
            <span className="status-value">Healthy</span>
          </div>
          <div className="status-item">
            <div className="status-indicator green"></div>
            <span>OCSP</span>
            <span className="status-value">{stats.ocsp_enabled ? 'Active' : 'Disabled'}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
