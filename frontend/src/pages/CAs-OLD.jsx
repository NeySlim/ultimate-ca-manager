import { useState, useEffect } from 'react'
import { Folder, Tree, SquaresFour, Plus, DownloadSimple, UploadSimple, Trash, Eye, Key, Certificate } from '@phosphor-icons/react'
import { api } from '../lib/api'
import './CAs.css'

export default function CAs() {
  const [cas, setCAs] = useState([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState('tree') // 'tree' or 'grid'
  const [selectedCA, setSelectedCA] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showDetailsModal, setShowDetailsModal] = useState(false)
  
  useEffect(() => {
    fetchCAs()
  }, [])
  
  async function fetchCAs() {
    try {
      // Mock data for now - will integrate API later
      const mockCAs = [
        {
          id: 1,
          refid: 'root-ca-2024',
          name: 'Root CA 2024',
          type: 'root',
          status: 'active',
          subject: 'CN=Root CA 2024, O=UCM, C=US',
          issuer: 'Self-signed',
          validFrom: '2024-01-01',
          validTo: '2034-01-01',
          serialNumber: '0x1234567890abcdef',
          children: [
            {
              id: 2,
              refid: 'intermediate-ca-prod',
              name: 'Intermediate CA - Production',
              type: 'intermediate',
              status: 'active',
              subject: 'CN=Intermediate CA Production, O=UCM, C=US',
              issuer: 'CN=Root CA 2024, O=UCM, C=US',
              validFrom: '2024-01-01',
              validTo: '2029-01-01',
              serialNumber: '0xabcdef1234567890',
              children: [
                {
                  id: 3,
                  refid: 'sub-ca-web',
                  name: 'Sub CA - Web Services',
                  type: 'sub',
                  status: 'active',
                  subject: 'CN=Web Services CA, O=UCM, C=US',
                  issuer: 'CN=Intermediate CA Production, O=UCM, C=US',
                  validFrom: '2024-06-01',
                  validTo: '2026-06-01',
                  serialNumber: '0x567890abcdef1234',
                  children: []
                }
              ]
            },
            {
              id: 4,
              refid: 'intermediate-ca-dev',
              name: 'Intermediate CA - Development',
              type: 'intermediate',
              status: 'active',
              subject: 'CN=Intermediate CA Development, O=UCM, C=US',
              issuer: 'CN=Root CA 2024, O=UCM, C=US',
              validFrom: '2024-01-01',
              validTo: '2027-01-01',
              serialNumber: '0xfedcba0987654321',
              children: []
            }
          ]
        },
        {
          id: 5,
          refid: 'root-ca-legacy',
          name: 'Root CA Legacy (2020)',
          type: 'root',
          status: 'expired',
          subject: 'CN=Root CA 2020, O=UCM Legacy, C=US',
          issuer: 'Self-signed',
          validFrom: '2020-01-01',
          validTo: '2024-01-01',
          serialNumber: '0x1111111111111111',
          children: []
        }
      ]
      
      setCAs(mockCAs)
      setLoading(false)
    } catch (err) {
      console.error('Error fetching CAs:', err)
      setLoading(false)
    }
  }
  
  function renderTreeView(caList, level = 0) {
    return caList.map(ca => (
      <div key={ca.id} className="tree-item" style={{ marginLeft: `${level * 24}px` }}>
        <div className={`ca-node ${ca.status}`}>
          <div className="ca-node-icon">
            {ca.type === 'root' && <Key size={18} weight="duotone" />}
            {ca.type === 'intermediate' && <Certificate size={18} weight="duotone" />}
            {ca.type === 'sub' && <Folder size={18} />}
          </div>
          <div className="ca-node-content">
            <div className="ca-node-header">
              <span className="ca-name">{ca.name}</span>
              <span className={`ca-status ${ca.status}`}>{ca.status}</span>
            </div>
            <div className="ca-node-details">
              <span className="ca-subject">{ca.subject}</span>
              <span className="ca-validity">Valid until: {ca.validTo}</span>
            </div>
          </div>
          <div className="ca-node-actions">
            <button className="icon-btn" onClick={() => { setSelectedCA(ca); setShowDetailsModal(true); }} title="View details">
              <Eye size={16} />
            </button>
            <button className="icon-btn" title="Download">
              <DownloadSimple size={16} />
            </button>
            <button className="icon-btn danger" title="Delete">
              <Trash size={16} />
            </button>
          </div>
        </div>
        {ca.children && ca.children.length > 0 && renderTreeView(ca.children, level + 1)}
      </div>
    ))
  }
  
  function renderGridView() {
    const flatCAs = []
    function flatten(caList) {
      caList.forEach(ca => {
        flatCAs.push(ca)
        if (ca.children) flatten(ca.children)
      })
    }
    flatten(cas)
    
    return (
      <div className="ca-grid">
        {flatCAs.map(ca => (
          <div key={ca.id} className={`ca-card ${ca.status}`}>
            <div className="ca-card-header">
              <div className="ca-card-icon">
                {ca.type === 'root' && <Key size={24} weight="duotone" />}
                {ca.type === 'intermediate' && <Certificate size={24} weight="duotone" />}
                {ca.type === 'sub' && <Folder size={24} />}
              </div>
              <span className={`ca-type ${ca.type}`}>{ca.type}</span>
            </div>
            <h3 className="ca-card-name">{ca.name}</h3>
            <p className="ca-card-subject">{ca.subject}</p>
            <div className="ca-card-meta">
              <span className={`ca-status ${ca.status}`}>{ca.status}</span>
              <span className="ca-validity">Until {ca.validTo}</span>
            </div>
            <div className="ca-card-actions">
              <button className="btn-secondary" onClick={() => { setSelectedCA(ca); setShowDetailsModal(true); }}>
                <Eye size={16} />
                Details
              </button>
              <button className="btn-secondary">
                <DownloadSimple size={16} />
                Export
              </button>
            </div>
          </div>
        ))}
      </div>
    )
  }
  
  if (loading) {
    return (
      <div className="cas-page">
        <div className="page-header">
          <h1>Certificate Authorities</h1>
          <p className="subtitle">Loading...</p>
        </div>
      </div>
    )
  }
  
  return (
    <div className="cas-page">
      <div className="page-header">
        <div>
          <h1>Certificate Authorities</h1>
          <p className="subtitle">Manage your PKI hierarchy</p>
        </div>
        <div className="page-actions">
          <button className="btn-secondary" onClick={() => setShowCreateModal(true)}>
            <UploadSimple size={16} />
            Import CA
          </button>
          <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
            <Plus size={16} />
            Create CA
          </button>
        </div>
      </div>
      
      <div className="toolbar">
        <div className="view-switcher">
          <button 
            className={`view-btn ${view === 'tree' ? 'active' : ''}`}
            onClick={() => setView('tree')}
          >
            <Tree size={18} />
            Tree
          </button>
          <button 
            className={`view-btn ${view === 'grid' ? 'active' : ''}`}
            onClick={() => setView('grid')}
          >
            <SquaresFour size={18} />
            Grid
          </button>
        </div>
        
        <div className="ca-stats">
          <span className="stat-item">
            <strong>{cas.length}</strong> Root CAs
          </span>
          <span className="stat-item">
            <strong>{cas.reduce((acc, ca) => acc + (ca.children?.length || 0), 0)}</strong> Intermediates
          </span>
        </div>
      </div>
      
      <div className="cas-content">
        {view === 'tree' ? (
          <div className="tree-view">
            {renderTreeView(cas)}
          </div>
        ) : (
          renderGridView()
        )}
      </div>
      
      {showDetailsModal && selectedCA && (
        <CADetailsModal ca={selectedCA} onClose={() => setShowDetailsModal(false)} />
      )}
      
      {showCreateModal && (
        <CreateCAModal onClose={() => setShowCreateModal(false)} onCreate={fetchCAs} />
      )}
    </div>
  )
}

function CADetailsModal({ ca, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>CA Details</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="detail-group">
            <label>Name</label>
            <p>{ca.name}</p>
          </div>
          <div className="detail-group">
            <label>Type</label>
            <p className={`ca-type ${ca.type}`}>{ca.type}</p>
          </div>
          <div className="detail-group">
            <label>Subject</label>
            <p className="monospace">{ca.subject}</p>
          </div>
          <div className="detail-group">
            <label>Issuer</label>
            <p className="monospace">{ca.issuer}</p>
          </div>
          <div className="detail-group">
            <label>Serial Number</label>
            <p className="monospace">{ca.serialNumber}</p>
          </div>
          <div className="detail-row">
            <div className="detail-group">
              <label>Valid From</label>
              <p>{ca.validFrom}</p>
            </div>
            <div className="detail-group">
              <label>Valid To</label>
              <p>{ca.validTo}</p>
            </div>
          </div>
          <div className="detail-group">
            <label>Status</label>
            <p><span className={`ca-status ${ca.status}`}>{ca.status}</span></p>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Close</button>
          <button className="btn-primary">
            <DownloadSimple size={16} />
            Export Certificate
          </button>
        </div>
      </div>
    </div>
  )
}

function CreateCAModal({ onClose, onCreate }) {
  const [caType, setCAType] = useState('root')
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Certificate Authority</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label>CA Type</label>
            <select value={caType} onChange={e => setCAType(e.target.value)}>
              <option value="root">Root CA</option>
              <option value="intermediate">Intermediate CA</option>
              <option value="sub">Sub CA</option>
            </select>
          </div>
          <div className="form-group">
            <label>Common Name (CN)</label>
            <input type="text" placeholder="e.g., My Root CA 2024" />
          </div>
          <div className="form-group">
            <label>Organization (O)</label>
            <input type="text" placeholder="e.g., My Company" />
          </div>
          <div className="form-group">
            <label>Country (C)</label>
            <input type="text" placeholder="e.g., US" maxLength="2" />
          </div>
          {caType !== 'root' && (
            <div className="form-group">
              <label>Parent CA</label>
              <select>
                <option>Root CA 2024</option>
                <option>Intermediate CA - Production</option>
              </select>
            </div>
          )}
          <div className="form-group">
            <label>Validity (years)</label>
            <input type="number" defaultValue={caType === 'root' ? 10 : 5} min="1" max="20" />
          </div>
          <div className="form-group">
            <label>Key Size</label>
            <select defaultValue="4096">
              <option value="2048">2048 bits</option>
              <option value="4096">4096 bits (recommended)</option>
              <option value="8192">8192 bits</option>
            </select>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => { onCreate(); onClose(); }}>
            <Plus size={16} />
            Create CA
          </button>
        </div>
      </div>
    </div>
  )
}
