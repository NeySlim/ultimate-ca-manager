import { useState, useEffect } from 'react'
import { Certificate, Plus, MagnifyingGlass, Download, X, FileText } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'

export default function Certificates() {
  const [certificates, setCertificates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ status: '', ca_id: '', search: '' })
  const [selectedCert, setSelectedCert] = useState(null)
  const [showIssueModal, setShowIssueModal] = useState(false)
  const [showExportModal, setShowExportModal] = useState(false)
  const [exportCert, setExportCert] = useState(null)
  
  useEffect(() => {
    fetchCertificates()
  }, [filters])
  
  async function fetchCertificates() {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getCertificates(filters)
      setCertificates(data || [])
    } catch (err) {
      console.error('Certificates fetch error:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading certificates..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchCertificates} />
  
  return (
    <div className="certificates-page">
      <div className="page-header">
        <div>
          <h1>Certificates</h1>
          <p className="subtitle">{certificates.length} certificates total</p>
        </div>
        <button className="btn-primary" onClick={() => setShowIssueModal(true)}>
          <Plus size={16} />
          Issue Certificate
        </button>
      </div>
      
      <div className="filters-bar">
        <div className="search-box">
          <MagnifyingGlass size={16} />
          <input 
            type="text" 
            placeholder="Search certificates..." 
            value={filters.search}
            onChange={e => setFilters({...filters, search: e.target.value})}
          />
        </div>
        
        <select value={filters.status} onChange={e => setFilters({...filters, status: e.target.value})}>
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="expired">Expired</option>
          <option value="revoked">Revoked</option>
        </select>
        
        <select value={filters.ca_id} onChange={e => setFilters({...filters, ca_id: e.target.value})}>
          <option value="">All CAs</option>
        </select>
      </div>
      
      {certificates.length === 0 ? (
        <div className="empty-state">
          <Certificate size={48} weight="duotone" />
          <p>No certificates found</p>
          <button className="btn-primary" onClick={() => setShowIssueModal(true)}>
            Issue Your First Certificate
          </button>
        </div>
      ) : (
        <div className="certificates-table-container">
          <table className="certificates-table">
            <thead>
              <tr>
                <th>Common Name</th>
                <th>Issuer</th>
                <th>Issued</th>
                <th>Expires</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {certificates.map(cert => (
                <tr key={cert.id || cert.serial}>
                  <td><strong>{cert.common_name || cert.subject}</strong></td>
                  <td className="cert-issuer">{cert.issuer || 'Unknown'}</td>
                  <td>{cert.not_before || cert.created_at}</td>
                  <td>{cert.not_after || cert.expires}</td>
                  <td>
                    <span className={`status-badge ${cert.status || 'active'}`}>
                      {cert.status || 'active'}
                    </span>
                  </td>
                  <td>
                    <div className="cert-actions">
                      <button className="icon-btn" onClick={() => setSelectedCert(cert)}>View</button>
                      <button className="icon-btn" onClick={() => {
                        if (cert.status === 'revoked') {
                          alert('Certificate already revoked')
                          return
                        }
                        if (confirm(`Revoke certificate for ${cert.common_name || cert.subject}?`)) {
                          api.revokeCertificate(cert.id || cert.serial)
                            .then(() => {
                              alert('Certificate revoked successfully')
                              fetchCertificates()
                            })
                            .catch(err => alert('Revoke failed: ' + err.message))
                        }
                      }}>Revoke</button>
                      <button className="icon-btn"><Download size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      
      {showIssueModal && <IssueCertModal onClose={() => setShowIssueModal(false)} onIssue={fetchCertificates} />}
      {selectedCert && <CertDetailsModal cert={selectedCert} onClose={() => setSelectedCert(null)} />}
      {showExportModal && exportCert && <ExportCertificateModal cert={exportCert} onClose={() => {
        setShowExportModal(false)
        setExportCert(null)
      }} />}
    </div>
  )
}

function IssueCertModal({ onClose, onIssue }) {
  const [formData, setFormData] = useState({
    common_name: '',
    organization: '',
    country: '',
    validity_days: 365
  })
  
  async function handleSubmit(e) {
    e.preventDefault()
    try {
      await api.issueCertificate(formData)
      onIssue()
      onClose()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Issue New Certificate</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>Common Name (CN)</label>
              <input type="text" required value={formData.common_name} 
                onChange={e => setFormData({...formData, common_name: e.target.value})} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Organization</label>
                <input type="text" value={formData.organization}
                  onChange={e => setFormData({...formData, organization: e.target.value})} />
              </div>
              <div className="form-group">
                <label>Country</label>
                <input type="text" maxLength="2" value={formData.country}
                  onChange={e => setFormData({...formData, country: e.target.value})} />
              </div>
            </div>
            <div className="form-group">
              <label>Validity (days)</label>
              <input type="number" value={formData.validity_days}
                onChange={e => setFormData({...formData, validity_days: parseInt(e.target.value)})} />
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Issue Certificate</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ExportCertificateModal({ cert, onClose }) {
  const [format, setFormat] = useState('pem')
  const [includeChain, setIncludeChain] = useState(false)
  const [loading, setLoading] = useState(false)
  
  async function handleExport() {
    setLoading(true)
    try {
      const options = {
        format,
        include_chain: includeChain
      }
      const result = await api.exportCertificate(cert.id, options)
      
      // Create download
      const blob = format === 'pem' 
        ? new Blob([result.content], { type: 'application/x-pem-file' })
        : new Blob([atob(result.content)], { type: 'application/octet-stream' })
      
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = result.filename || `certificate_${cert.id}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      
      onClose()
    } catch (err) {
      alert('Export failed: ' + err.message)
    } finally {
      setLoading(false)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2><FileText size={20} /> Export Certificate: {cert.common_name}</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label>Export Format</label>
            <select value={format} onChange={e => setFormat(e.target.value)}>
              <option value="pem">PEM (.crt)</option>
              <option value="der">DER (.der)</option>
              <option value="pkcs12">PKCS#12 (.p12)</option>
            </select>
          </div>
          
          <div className="form-group">
            <label className="checkbox-label">
              <input 
                type="checkbox" 
                checked={includeChain}
                onChange={e => setIncludeChain(e.target.checked)}
              />
              Include certificate chain
            </label>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button 
            className="btn-primary" 
            onClick={handleExport}
            disabled={loading}
          >
            <Download size={16} />
            {loading ? 'Exporting...' : 'Export'}
          </button>
        </div>
      </div>
    </div>
  )
}

function CertDetailsModal({ cert, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Certificate Details</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="detail-group">
            <label>Common Name</label>
            <p>{cert.common_name}</p>
          </div>
          <div className="detail-group">
            <label>Serial Number</label>
            <p className="monospace">{cert.serial}</p>
          </div>
          <div className="detail-row">
            <div className="detail-group">
              <label>Valid From</label>
              <p>{cert.not_before}</p>
            </div>
            <div className="detail-group">
              <label>Valid Until</label>
              <p>{cert.not_after}</p>
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Close</button>
          <button className="btn-primary" onClick={() => {
            onClose()
            setExportCert(cert)
            setShowExportModal(true)
          }}><Download size={16} /> Export</button>
        </div>
      </div>
    </div>
  )
}
