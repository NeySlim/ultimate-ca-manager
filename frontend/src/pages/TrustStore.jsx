import { useState, useEffect } from 'react'
import { ShieldStar, Upload, Trash } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import './TrustStore.css'

export default function TrustStore() {
  const [trusted, setTrusted] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  useEffect(() => {
    fetchTrusted()
  }, [])
  
  async function fetchTrusted() {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getTrustedCertificates()
      setTrusted(data || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  async function handleDelete(id) {
    if (!confirm('Remove from trust store?')) return
    try {
      await api.removeTrustedCertificate(id)
      fetchTrusted()
    } catch (err) {
      alert(err.message)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading trust store..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchTrusted} />
  
  return (
    <div className="truststore-page">
      <div className="page-header">
        <div>
          <h1>Trust Store</h1>
          <p className="subtitle">Manage trusted root certificates</p>
        </div>
        <button className="btn-primary">
          <Upload size={20} weight="bold" />
          Import Certificate
        </button>
      </div>
      
      {trusted.length === 0 ? (
        <div className="empty-state">
          <ShieldStar size={48} weight="duotone" />
          <p>No trusted certificates</p>
        </div>
      ) : (
        <div className="trusted-table">
          <table>
            <thead>
              <tr>
                <th>Subject</th>
                <th>Issuer</th>
                <th>Valid Until</th>
                <th>Fingerprint</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {trusted.map(cert => (
                <tr key={cert.id}>
                  <td><strong>{cert.subject || cert.common_name}</strong></td>
                  <td>{cert.issuer}</td>
                  <td>{cert.not_after}</td>
                  <td><code className="fingerprint">{cert.fingerprint?.substring(0, 16)}...</code></td>
                  <td>
                    <button className="btn-icon-danger" onClick={() => handleDelete(cert.id)}>
                      <Trash size={18} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ImportCertificateModal({ onClose, onImport }) {
  const [certData, setCertData] = useState('')
  const [file, setFile] = useState(null)
  const [uploadMethod, setUploadMethod] = useState('paste') // paste or file
  
  async function handleSubmit(e) {
    e.preventDefault()
    try {
      if (uploadMethod === 'paste') {
        await api.importTrustedCertificate({ certificate: certData })
      } else {
        const formData = new FormData()
        formData.append('certificate', file)
        await api.importTrustedCertificate(formData)
      }
      onImport()
      onClose()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Import Trusted Certificate</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>Import Method</label>
              <div className="radio-group">
                <label className="radio-label">
                  <input 
                    type="radio"
                    checked={uploadMethod === 'paste'}
                    onChange={() => setUploadMethod('paste')}
                  />
                  Paste PEM
                </label>
                <label className="radio-label">
                  <input 
                    type="radio"
                    checked={uploadMethod === 'file'}
                    onChange={() => setUploadMethod('file')}
                  />
                  Upload File
                </label>
              </div>
            </div>
            
            {uploadMethod === 'paste' ? (
              <div className="form-group">
                <label>Certificate (PEM format) *</label>
                <textarea 
                  required
                  value={certData}
                  onChange={e => setCertData(e.target.value)}
                  placeholder="-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----"
                  rows={10}
                  style={{ fontFamily: 'monospace', fontSize: '12px' }}
                />
              </div>
            ) : (
              <div className="form-group">
                <label>Certificate File *</label>
                <input 
                  type="file"
                  required
                  accept=".pem,.crt,.cer"
                  onChange={e => setFile(e.target.files[0])}
                />
                <small>Accepted formats: PEM, CRT, CER</small>
              </div>
            )}
          </div>
          
          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Import Certificate</button>
          </div>
        </form>
      </div>
    </div>
  )
}
