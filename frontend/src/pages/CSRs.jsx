import { useState, useEffect } from 'react'
import { FileText, UploadSimple, Check } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'

export default function CSRs() {
  const [csrs, setCSRs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [showSignModal, setShowSignModal] = useState(false)
  const [selectedCSR, setSelectedCSR] = useState(null)
  
  useEffect(() => {
    fetchCSRs()
  }, [])
  
  async function fetchCSRs() {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getCSRs()
      setCSRs(data || [])
    } catch (err) {
      console.error('CSRs fetch error:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading CSRs..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchCSRs} />
  
  const pending = csrs.filter(c => c.status === 'pending')
  const signed = csrs.filter(c => c.status === 'signed')
  
  return (
    <div className="csrs-page">
      <div className="page-header">
        <div>
          <h1>Certificate Signing Requests</h1>
          <p className="subtitle">{pending.length} pending, {signed.length} signed</p>
        </div>
        <button className="btn-primary" onClick={() => setShowUploadModal(true)}>
          <UploadSimple size={16} />
          Upload CSR
        </button>
      </div>
      
      <div className="csrs-sections">
        <div className="csr-section">
          <h2>Pending CSRs</h2>
          {pending.length === 0 ? (
            <div className="empty-state">
              <FileText size={48} />
              <p>No pending CSRs</p>
            </div>
          ) : (
            <div className="csrs-list">
              {pending.map(csr => (
                <div key={csr.id} className="csr-card">
                  <div className="csr-card-header">
                    <div className="csr-info">
                      <h3>{csr.common_name || csr.subject}</h3>
                      <p className="csr-meta">{csr.organization || ''}</p>
                    </div>
                    <span className="status-badge warning">pending</span>
                  </div>
                  <div className="csr-card-actions">
                    <button className="btn-secondary" onClick={() => { setSelectedCSR(csr); setShowSignModal(true); }}>
                      <Check size={16} /> Sign CSR
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        <div className="csr-section">
          <h2>Signed CSRs</h2>
          {signed.length === 0 ? (
            <p className="empty-message">No signed CSRs yet</p>
          ) : (
            <div className="csrs-list">
              {signed.map(csr => (
                <div key={csr.id} className="csr-card">
                  <div className="csr-card-header">
                    <div className="csr-info">
                      <h3>{csr.common_name}</h3>
                      <p className="csr-meta">Signed {csr.signed_at}</p>
                    </div>
                    <span className="status-badge success">signed</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      
      {showUploadModal && <UploadCSRModal onClose={() => setShowUploadModal(false)} onUpload={fetchCSRs} />}
      {showSignModal && selectedCSR && <SignCSRModal csr={selectedCSR} onClose={() => setShowSignModal(false)} onSign={fetchCSRs} />}
    </div>
  )
}

function UploadCSRModal({ onClose, onUpload }) {
  const [csrText, setCSRText] = useState('')
  
  async function handleUpload() {
    try {
      await api.uploadCSR(csrText)
      onUpload()
      onClose()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Upload CSR</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label>CSR (PEM format)</label>
            <textarea rows="15" className="csr-textarea" value={csrText} onChange={e => setCSRText(e.target.value)} />
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={handleUpload} disabled={!csrText}>Upload</button>
        </div>
      </div>
    </div>
  )
}

function SignCSRModal({ csr, onClose, onSign }) {
  async function handleSign() {
    try {
      await api.signCSR(csr.id, { validity_days: 365 })
      onSign()
      onClose()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Sign CSR</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="detail-group">
            <label>Subject</label>
            <p>{csr.subject}</p>
          </div>
          <div className="form-group">
            <label>Validity (days)</label>
            <input type="number" defaultValue={365} />
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={handleSign}>Sign</button>
        </div>
      </div>
    </div>
  )
}
