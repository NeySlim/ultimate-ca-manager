import { useState, useEffect } from 'react'
import { Folder, TreeStructure, SquaresFour, Plus, Eye, Trash, Download } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import './CAs.css'

export default function CAs() {
  const [cas, setCAs] = useState([])
  const [view, setView] = useState('tree')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [selectedCA, setSelectedCA] = useState(null)
  
  useEffect(() => {
    fetchCAs()
  }, [])
  
  async function fetchCAs() {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getCAs()
      setCAs(data || [])
    } catch (err) {
      console.error('CAs fetch error:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading Certificate Authorities..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchCAs} />
  
  const rootCAs = cas.filter(ca => !ca.parent_id || ca.parent_id === null)
  const intermediateCAs = cas.filter(ca => ca.parent_id && ca.parent_id !== null)
  
  return (
    <div className="cas-page">
      <div className="page-header">
        <div>
          <h1>Certificate Authorities</h1>
          <p className="subtitle">Manage your PKI hierarchy • {rootCAs.length} Root CAs • {intermediateCAs.length} Intermediates</p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button className="btn-secondary">
            <Download size={16} />
            Import CA
          </button>
          <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
            <Plus size={16} />
            Create CA
          </button>
        </div>
      </div>
      
      <div className="view-toggle">
        <button 
          className={`toggle-btn ${view === 'tree' ? 'active' : ''}`}
          onClick={() => setView('tree')}
        >
          <TreeStructure size={16} />
          Tree
        </button>
        <button 
          className={`toggle-btn ${view === 'grid' ? 'active' : ''}`}
          onClick={() => setView('grid')}
        >
          <SquaresFour size={16} />
          Grid
        </button>
      </div>
      
      {cas.length === 0 ? (
        <div className="empty-state">
          <Folder size={48} weight="duotone" />
          <p>No Certificate Authorities</p>
          <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
            Create Your First CA
          </button>
        </div>
      ) : (
        view === 'tree' ? <TreeView cas={cas} onSelect={setSelectedCA} /> : <GridView cas={cas} onSelect={setSelectedCA} />
      )}
      
      {showCreateModal && <CreateCAModal onClose={() => setShowCreateModal(false)} onCreate={fetchCAs} />}
      {selectedCA && <CADetailsModal ca={selectedCA} onClose={() => setSelectedCA(null)} />}
    </div>
  )
}

function TreeView({ cas, onSelect }) {
  const buildTree = () => {
    const roots = cas.filter(ca => !ca.parent_id)
    return roots.map(root => ({
      ...root,
      children: cas.filter(ca => ca.parent_id === root.id || ca.parent_id === root.caref)
    }))
  }
  
  const tree = buildTree()
  
  return (
    <div className="tree-view">
      {tree.map(root => (
        <CANode key={root.id || root.caref} ca={root} level={0} onSelect={onSelect} />
      ))}
    </div>
  )
}

function CANode({ ca, level, onSelect }) {
  const [expanded, setExpanded] = useState(true)
  const hasChildren = ca.children && ca.children.length > 0
  
  return (
    <div className="ca-node-container">
      <div className="ca-node" style={{ paddingLeft: `${level * 24}px` }}>
        {hasChildren && (
          <button className="expand-btn" onClick={() => setExpanded(!expanded)}>
            {expanded ? '−' : '+'}
          </button>
        )}
        
        <div className="ca-icon">
          <Folder size={20} weight="duotone" />
        </div>
        
        <div className="ca-info">
          <div className="ca-name">{ca.common_name}</div>
          <div className="ca-details">
            {ca.descr || 'Root CA'} • Expires {ca.expires || ca.expiry} • {ca.certs || 0} certificates
          </div>
        </div>
        
        <div className="ca-actions">
          <button className="icon-btn" onClick={() => onSelect(ca)}>
            <Eye size={16} />
          </button>
        </div>
      </div>
      
      {expanded && hasChildren && (
        <div className="ca-children">
          {ca.children.map(child => (
            <CANode key={child.id || child.caref} ca={child} level={level + 1} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  )
}

function GridView({ cas, onSelect }) {
  return (
    <div className="grid-view">
      {cas.map(ca => (
        <div key={ca.id || ca.caref} className="ca-card" onClick={() => onSelect(ca)}>
          <div className="ca-card-icon">
            <Folder size={32} weight="duotone" />
          </div>
          <h3>{ca.common_name}</h3>
          <p className="ca-card-type">{ca.descr || 'Certificate Authority'}</p>
          <div className="ca-card-stats">
            <div className="stat">
              <span className="stat-value">{ca.certs || 0}</span>
              <span className="stat-label">Certificates</span>
            </div>
            <div className="stat">
              <span className="stat-value">{ca.expires || ca.expiry}</span>
              <span className="stat-label">Expires</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function CreateCAModal({ onClose, onCreate }) {
  const [formData, setFormData] = useState({
    type: 'root',
    common_name: '',
    organization: '',
    country: '',
    validity_days: 3650,
    key_size: 4096
  })
  
  async function handleSubmit(e) {
    e.preventDefault()
    try {
      await api.createCA(formData)
      onCreate()
      onClose()
    } catch (err) {
      alert('Error creating CA: ' + err.message)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Certificate Authority</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>CA Type</label>
              <select value={formData.type} onChange={e => setFormData({...formData, type: e.target.value})}>
                <option value="root">Root CA</option>
                <option value="intermediate">Intermediate CA</option>
                <option value="sub">Sub CA</option>
              </select>
            </div>
            
            <div className="form-group">
              <label>Common Name (CN)</label>
              <input type="text" required value={formData.common_name} onChange={e => setFormData({...formData, common_name: e.target.value})} />
            </div>
            
            <div className="form-row">
              <div className="form-group">
                <label>Organization</label>
                <input type="text" value={formData.organization} onChange={e => setFormData({...formData, organization: e.target.value})} />
              </div>
              <div className="form-group">
                <label>Country</label>
                <input type="text" maxLength="2" value={formData.country} onChange={e => setFormData({...formData, country: e.target.value})} />
              </div>
            </div>
            
            <div className="form-row">
              <div className="form-group">
                <label>Validity (days)</label>
                <input type="number" value={formData.validity_days} onChange={e => setFormData({...formData, validity_days: parseInt(e.target.value)})} />
              </div>
              <div className="form-group">
                <label>Key Size</label>
                <select value={formData.key_size} onChange={e => setFormData({...formData, key_size: parseInt(e.target.value)})}>
                  <option value="2048">2048 bits</option>
                  <option value="4096">4096 bits</option>
                  <option value="8192">8192 bits</option>
                </select>
              </div>
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Create CA</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function CADetailsModal({ ca, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>CA Details</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="detail-group">
            <label>Common Name</label>
            <p>{ca.common_name}</p>
          </div>
          
          <div className="detail-row">
            <div className="detail-group">
              <label>Type</label>
              <p>{ca.descr || 'Root CA'}</p>
            </div>
            <div className="detail-group">
              <label>Expires</label>
              <p>{ca.expires || ca.expiry}</p>
            </div>
          </div>
          
          <div className="detail-group">
            <label>Certificates Issued</label>
            <p>{ca.certs || 0} certificates</p>
          </div>
          
          <div className="detail-group">
            <label>CA Reference</label>
            <p className="monospace">{ca.caref || ca.id}</p>
          </div>
          
          {ca.has_private_key !== undefined && (
            <div className="detail-group">
              <label>Private Key</label>
              <p>{ca.has_private_key ? '✅ Available' : '❌ Not available'}</p>
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Close</button>
          <button className="btn-primary">
            <Download size={16} />
            Export CA
          </button>
        </div>
      </div>
    </div>
  )
}

function ImportCAModal({ onClose, onImport }) {
  const [certData, setCertData] = useState('')
  const [keyData, setKeyData] = useState('')
  const [file, setFile] = useState(null)
  const [uploadMethod, setUploadMethod] = useState('paste')
  
  async function handleSubmit(e) {
    e.preventDefault()
    try {
      if (uploadMethod === 'paste') {
        await api.importCA({ certificate: certData, private_key: keyData })
      } else {
        const formData = new FormData()
        formData.append('ca_file', file)
        await api.importCA(formData)
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
          <h2>Import Certificate Authority</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>Import Method</label>
              <div className="radio-group" style={{ display: 'flex', gap: '16px', marginTop: '8px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <input 
                    type="radio"
                    checked={uploadMethod === 'paste'}
                    onChange={() => setUploadMethod('paste')}
                  />
                  Paste PEM
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
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
              <>
                <div className="form-group">
                  <label>CA Certificate (PEM format) *</label>
                  <textarea 
                    required
                    value={certData}
                    onChange={e => setCertData(e.target.value)}
                    placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                    rows={8}
                    style={{ fontFamily: 'monospace', fontSize: '12px' }}
                  />
                </div>
                <div className="form-group">
                  <label>Private Key (PEM format, optional)</label>
                  <textarea 
                    value={keyData}
                    onChange={e => setKeyData(e.target.value)}
                    placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----"
                    rows={8}
                    style={{ fontFamily: 'monospace', fontSize: '12px' }}
                  />
                  <small>Only needed if you want to issue certificates with this CA</small>
                </div>
              </>
            ) : (
              <div className="form-group">
                <label>CA Bundle File (PEM/P12) *</label>
                <input 
                  type="file"
                  required
                  accept=".pem,.p12,.pfx"
                  onChange={e => setFile(e.target.files[0])}
                />
                <small>Accepted formats: PEM, P12, PFX</small>
              </div>
            )}
          </div>
          
          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Import CA</button>
          </div>
        </form>
      </div>
    </div>
  )
}
