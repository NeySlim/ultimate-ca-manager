import { useState, useEffect } from 'react'
import { DeviceMobile, QrCode, Key } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import './SCEP.css'

export default function SCEP() {
  const [configs, setConfigs] = useState([])
  const [enrollments, setEnrollments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showQR, setShowQR] = useState(null)
  
  useEffect(() => {
    fetchData()
  }, [])
  
  async function fetchData() {
    try {
      setLoading(true)
      setError(null)
      const [cfgs, enrs] = await Promise.all([
        api.getSCEPConfigs().catch(() => []),
        api.getSCEPEnrollments().catch(() => [])
      ])
      setConfigs(cfgs || [])
      setEnrollments(enrs || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading SCEP..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchData} />
  
  return (
    <div className="scep-page">
      <h1>SCEP Enrollment</h1>
      <p className="subtitle">Simple Certificate Enrollment Protocol for devices</p>
      
      <div className="scep-grid">
        <div className="configs-section">
          <h2>SCEP Configurations</h2>
          {configs.length === 0 ? (
            <div className="empty-state">
              <DeviceMobile size={48} weight="duotone" />
              <p>No SCEP configurations</p>
            </div>
          ) : (
            <div className="configs-list">
              {configs.map(cfg => (
                <div key={cfg.id} className="config-card">
                  <div className="config-header">
                    <Key size={24} weight="duotone" />
                    <div>
                      <h3>{cfg.name}</h3>
                      <span className="url">{cfg.url}</span>
                    </div>
                  </div>
                  <div className="config-info">
                    <div className="info-row">
                      <span>CA</span>
                      <strong>{cfg.ca_name}</strong>
                    </div>
                    <div className="info-row">
                      <span>Challenge</span>
                      <code>{cfg.challenge || '***'}</code>
                    </div>
                  </div>
                  <button className="btn-secondary" onClick={() => setShowQR(cfg)}>
                    <QrCode size={18} /> QR Code
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        
        <div className="enrollments-section">
          <h2>Recent Enrollments</h2>
          {enrollments.length === 0 ? (
            <p className="empty-message">No recent enrollments</p>
          ) : (
            <div className="enrollments-list">
              {enrollments.map(enr => (
                <div key={enr.id} className="enrollment-item">
                  <DeviceMobile size={20} weight="duotone" />
                  <div className="enrollment-info">
                    <strong>{enr.device_name || enr.common_name}</strong>
                    <span>{enr.created_at}</span>
                  </div>
                  <span className={`badge ${enr.status}`}>{enr.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      
      {showQR && (
        <div className="modal-overlay" onClick={() => setShowQR(null)}>
          <div className="modal-container" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>SCEP QR Code</h2>
              <button className="modal-close" onClick={() => setShowQR(null)}>×</button>
            </div>
            <div className="modal-body qr-modal">
              <div className="qr-placeholder">
                <QrCode size={200} weight="duotone" />
                <p>Scan to enroll device</p>
              </div>
              <div className="scep-details">
                <div className="detail-row">
                  <span>URL:</span>
                  <code>{showQR.url}</code>
                </div>
                <div className="detail-row">
                  <span>Challenge:</span>
                  <code>{showQR.challenge}</code>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
