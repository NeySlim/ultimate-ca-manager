import { useState, useEffect } from 'react'
import { FilePlus, FileText, Eye, Check, XCircle, UploadSimple } from '@phosphor-icons/react'
import './CSRs.css'

export default function CSRs() {
  const [csrs, setCSRs] = useState([])
  const [loading, setLoading] = useState(true)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [showSignModal, setShowSignModal] = useState(false)
  const [selectedCSR, setSelectedCSR] = useState(null)
  
  useEffect(() => {
    fetchCSRs()
  }, [])
  
  async function fetchCSRs() {
    try {
      // Mock data
      const mockCSRs = [
        {
          id: 1,
          commonName: 'new-app.example.com',
          organization: 'Example Inc',
          country: 'US',
          status: 'pending',
          uploadedAt: '2024-01-20 14:30',
          keySize: 2048,
          algorithm: 'RSA',
          subject: 'CN=new-app.example.com, O=Example Inc, C=US'
        },
        {
          id: 2,
          commonName: 'test-service.local',
          organization: 'Dev Team',
          country: 'US',
          status: 'pending',
          uploadedAt: '2024-01-19 10:15',
          keySize: 4096,
          algorithm: 'RSA',
          subject: 'CN=test-service.local, O=Dev Team, C=US'
        },
        {
          id: 3,
          commonName: 'api-v2.company.com',
          organization: 'Company Ltd',
          country: 'UK',
          status: 'signed',
          uploadedAt: '2024-01-18 16:45',
          signedAt: '2024-01-18 17:00',
          certificateId: 'cert-12345',
          keySize: 2048,
          algorithm: 'RSA',
          subject: 'CN=api-v2.company.com, O=Company Ltd, C=UK'
        }
      ]
      
      setCSRs(mockCSRs)
      setLoading(false)
    } catch (err) {
      console.error('Error fetching CSRs:', err)
      setLoading(false)
    }
  }
  
  if (loading) {
    return (
      <div className="csrs-page">
        <h1>Certificate Signing Requests</h1>
        <p>Loading...</p>
      </div>
    )
  }
  
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
              <button className="btn-secondary" onClick={() => setShowUploadModal(true)}>
                Upload CSR
              </button>
            </div>
          ) : (
            <div className="csrs-list">
              {pending.map(csr => (
                <div key={csr.id} className="csr-card">
                  <div className="csr-card-header">
                    <div className="csr-icon">
                      <FileText size={24} weight="duotone" />
                    </div>
                    <div className="csr-info">
                      <h3>{csr.commonName}</h3>
                      <p className="csr-meta">{csr.organization} • {csr.keySize} bits {csr.algorithm}</p>
                      <p className="csr-date">Uploaded {csr.uploadedAt}</p>
                    </div>
                    <span className="status-badge warning">pending</span>
                  </div>
                  <div className="csr-card-actions">
                    <button className="btn-secondary" onClick={() => { setSelectedCSR(csr); setShowSignModal(true); }}>
                      <Check size={16} />
                      Sign CSR
                    </button>
                    <button className="icon-btn">
                      <Eye size={16} />
                    </button>
                    <button className="icon-btn danger">
                      <XCircle size={16} />
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
            <div className="empty-state-small">
              <p>No signed CSRs yet</p>
            </div>
          ) : (
            <div className="csrs-list">
              {signed.map(csr => (
                <div key={csr.id} className="csr-card signed">
                  <div className="csr-card-header">
                    <div className="csr-icon">
                      <Check size={24} weight="bold" />
                    </div>
                    <div className="csr-info">
                      <h3>{csr.commonName}</h3>
                      <p className="csr-meta">{csr.organization} • Certificate #{csr.certificateId}</p>
                      <p className="csr-date">Signed {csr.signedAt}</p>
                    </div>
                    <span className="status-badge success">signed</span>
                  </div>
                  <div className="csr-card-actions">
                    <button className="icon-btn">
                      <Eye size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      
      {showUploadModal && (
        <UploadCSRModal onClose={() => setShowUploadModal(false)} onUpload={fetchCSRs} />
      )}
      
      {showSignModal && selectedCSR && (
        <SignCSRModal csr={selectedCSR} onClose={() => setShowSignModal(false)} onSign={fetchCSRs} />
      )}
    </div>
  )
}

function UploadCSRModal({ onClose, onUpload }) {
  const [csrText, setCSRText] = useState('')
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Upload Certificate Signing Request</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label>CSR (PEM format)</label>
            <textarea
              rows="15"
              placeholder="-----BEGIN CERTIFICATE REQUEST-----&#10;MIICvDCCAaQCAQAwdzELMAkGA1UEBhMCVVMxCzAJBgNVBAgMAlNUMQ4wDAYDVQQH&#10;...&#10;-----END CERTIFICATE REQUEST-----"
              value={csrText}
              onChange={e => setCSRText(e.target.value)}
              className="csr-textarea"
            />
            <span className="form-hint">Paste your CSR in PEM format (including BEGIN/END lines)</span>
          </div>
          
          <div className="upload-hint">
            <FilePlus size={24} />
            <p>Or drop a .csr file here</p>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => { onUpload(); onClose(); }} disabled={!csrText}>
            <UploadSimple size={16} />
            Upload CSR
          </button>
        </div>
      </div>
    </div>
  )
}

function SignCSRModal({ csr, onClose, onSign }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Sign Certificate Request</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="detail-group">
            <label>CSR Subject</label>
            <p className="monospace">{csr.subject}</p>
          </div>
          
          <div className="detail-row">
            <div className="detail-group">
              <label>Key Size</label>
              <p>{csr.keySize} bits</p>
            </div>
            <div className="detail-group">
              <label>Algorithm</label>
              <p>{csr.algorithm}</p>
            </div>
          </div>
          
          <div className="form-group">
            <label>Issuing CA</label>
            <select>
              <option>Intermediate CA - Production</option>
              <option>Intermediate CA - Development</option>
              <option>Sub CA - Web Services</option>
            </select>
          </div>
          
          <div className="form-group">
            <label>Certificate Template (optional)</label>
            <select>
              <option value="">-- No template --</option>
              <option>Web Server Template</option>
              <option>Email Certificate Template</option>
              <option>VPN Certificate Template</option>
            </select>
          </div>
          
          <div className="form-group">
            <label>Validity (days)</label>
            <input type="number" defaultValue={365} min="1" max="825" />
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => { onSign(); onClose(); }}>
            <Check size={16} />
            Sign & Issue Certificate
          </button>
        </div>
      </div>
    </div>
  )
}
