import { useState, useEffect } from 'react'
import { ListChecks, Download, ArrowsClockwise } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'

export default function CRL() {
  const [crls, setCrls] = useState([])
  const [ocspStatus, setOcspStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  useEffect(() => {
    fetchData()
  }, [])
  
  async function fetchData() {
    try {
      setLoading(true)
      setError(null)
      const [crlData, ocspData] = await Promise.all([
        api.getCRLs().catch(() => []),
        api.getOCSPStatus().catch(() => null)
      ])
      setCrls(crlData || [])
      setOcspStatus(ocspData || {})
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  async function handleGenerateCRL(caId) {
    try {
      await api.generateCRL(caId)
      fetchData()
    } catch (err) {
      alert(err.message)
    }
  }
  
  async function handleDownloadCRL(crlId) {
    try {
      const blob = await api.downloadCRL(crlId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `crl-${crlId}.pem`
      a.click()
    } catch (err) {
      alert(err.message)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading CRL/OCSP..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchData} />
  
  return (
    <div className="crl-page">
      <h1>CRL & OCSP Management</h1>
      <p className="subtitle">Certificate revocation lists and online status protocol</p>
      
      <div className="crl-grid">
        <div className="crls-section">
          <div className="section-header">
            <h2>Certificate Revocation Lists</h2>
            <button className="btn-secondary" onClick={() => handleGenerateCRL('all')}>
              <ArrowsClockwise size={18} weight="bold" />
              Regenerate All
            </button>
          </div>
          
          {crls.length === 0 ? (
            <div className="empty-state">
              <ListChecks size={48} weight="duotone" />
              <p>No CRLs generated yet</p>
            </div>
          ) : (
            <div className="crls-table">
              <table>
                <thead>
                  <tr>
                    <th>CA Name</th>
                    <th>Last Updated</th>
                    <th>Next Update</th>
                    <th>Revoked</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {crls.map(crl => (
                    <tr key={crl.id}>
                      <td>{crl.ca_name}</td>
                      <td>{crl.last_update || 'Never'}</td>
                      <td>{crl.next_update || 'N/A'}</td>
                      <td><span className="badge">{crl.revoked_count || 0}</span></td>
                      <td>
                        <div className="action-buttons">
                          <button className="btn-icon" onClick={() => handleDownloadCRL(crl.id)} title="Download">
                            <Download size={18} />
                          </button>
                          <button className="btn-icon" onClick={() => handleGenerateCRL(crl.ca_id)} title="Regenerate">
                            <ArrowsClockwise size={18} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        
        <div className="ocsp-section">
          <h2>OCSP Status</h2>
          <div className="status-card">
            <div className="status-row">
              <span>Service Status</span>
              <span className={`badge ${ocspStatus?.enabled ? 'success' : 'default'}`}>
                {ocspStatus?.enabled ? 'Active' : 'Disabled'}
              </span>
            </div>
            <div className="status-row">
              <span>Requests Today</span>
              <span className="value">{ocspStatus?.requests_today || 0}</span>
            </div>
            <div className="status-row">
              <span>Response Time</span>
              <span className="value">{ocspStatus?.avg_response_time || '0'}ms</span>
            </div>
            <div className="status-row">
              <span>Uptime</span>
              <span className="value">{ocspStatus?.uptime || '0%'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
