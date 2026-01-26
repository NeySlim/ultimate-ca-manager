import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Certificate, Folder, Clock, TrendUp, CheckCircle, XCircle } from '@phosphor-icons/react'
import { api } from '../lib/api'
import './Dashboard.css'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()
  
  useEffect(() => {
    // For now, use mock data to show the design
    setTimeout(() => {
      setStats({
        certificates: {
          total: 247,
          active: 189,
          expired: 12,
          expiring: 8,
          revoked: 38
        },
        cas: {
          total: 12,
          root: 3,
          intermediate: 7,
          sub: 2
        },
        activity: [
          { id: 1, type: 'cert_issued', description: 'Certificate issued for api.example.com', timestamp: '2 minutes ago' },
          { id: 2, type: 'ca_created', description: 'New intermediate CA created: Dev-CA-2024', timestamp: '1 hour ago' },
          { id: 3, type: 'cert_revoked', description: 'Certificate revoked: old-server.local', timestamp: '3 hours ago' },
          { id: 4, type: 'acme_order', description: 'ACME order completed for *.staging.com', timestamp: '5 hours ago' }
        ],
        ocsp: {
          requests_today: 1423,
          success_rate: 99.8
        },
        crl: {
          last_update: '2 hours ago',
          next_update: 'in 22 hours',
          entries: 38
        }
      })
      setLoading(false)
    }, 500)
  }, [])
  
  if (loading) {
    return (
      <div className="dashboard">
        <div className="page-header">
          <h1>Dashboard</h1>
          <p className="subtitle">Loading...</p>
        </div>
      </div>
    )
  }
  
  return (
    <div className="dashboard">
      <div className="page-header">
        <h1>Dashboard</h1>
        <p className="subtitle">Overview of your PKI infrastructure</p>
      </div>
      
      <div className="stats-grid">
        <StatCard
          title="Total Certificates"
          value={stats.certificates.total}
          icon={<Certificate size={24} weight="duotone" />}
          color="blue"
        />
        <StatCard
          title="Active Certificates"
          value={stats.certificates.active}
          icon={<CheckCircle size={24} weight="duotone" />}
          color="green"
        />
        <StatCard
          title="Expiring Soon"
          value={stats.certificates.expiring}
          icon={<Clock size={24} weight="duotone" />}
          color="orange"
        />
        <StatCard
          title="Certificate Authorities"
          value={stats.cas.total}
          icon={<Folder size={24} weight="duotone" />}
          color="purple"
        />
      </div>
      
      <div className="dashboard-grid">
        <div className="activity-section">
          <h2>Recent Activity</h2>
          <div className="activity-list">
            {stats.activity.map(item => (
              <div key={item.id} className="activity-item">
                <div className="activity-icon">
                  {item.type === 'cert_issued' && <Certificate size={16} />}
                  {item.type === 'ca_created' && <Folder size={16} />}
                  {item.type === 'cert_revoked' && <XCircle size={16} />}
                  {item.type === 'acme_order' && <CheckCircle size={16} />}
                </div>
                <div className="activity-content">
                  <p className="activity-desc">{item.description}</p>
                  <p className="activity-time">{item.timestamp}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        
        <div className="sidebar-stats">
          <div className="stat-box">
            <h3>Certificate Status</h3>
            <div className="stat-row">
              <span>Active</span>
              <span className="stat-value green">{stats.certificates.active}</span>
            </div>
            <div className="stat-row">
              <span>Expiring</span>
              <span className="stat-value orange">{stats.certificates.expiring}</span>
            </div>
            <div className="stat-row">
              <span>Expired</span>
              <span className="stat-value red">{stats.certificates.expired}</span>
            </div>
            <div className="stat-row">
              <span>Revoked</span>
              <span className="stat-value gray">{stats.certificates.revoked}</span>
            </div>
          </div>
          
          <div className="stat-box">
            <h3>OCSP Status</h3>
            <div className="stat-row">
              <span>Requests Today</span>
              <span className="stat-value">{stats.ocsp.requests_today}</span>
            </div>
            <div className="stat-row">
              <span>Success Rate</span>
              <span className="stat-value green">{stats.ocsp.success_rate}%</span>
            </div>
          </div>
          
          <div className="stat-box">
            <h3>CRL Status</h3>
            <div className="stat-row">
              <span>Last Update</span>
              <span className="stat-value small">{stats.crl.last_update}</span>
            </div>
            <div className="stat-row">
              <span>Next Update</span>
              <span className="stat-value small">{stats.crl.next_update}</span>
            </div>
            <div className="stat-row">
              <span>Entries</span>
              <span className="stat-value">{stats.crl.entries}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function StatCard({ title, value, icon, color }) {
  return (
    <div className={`stat-card ${color}`}>
      <div className="stat-icon">{icon}</div>
      <div className="stat-content">
        <p className="stat-title">{title}</p>
        <p className="stat-value">{value}</p>
      </div>
    </div>
  )
}
