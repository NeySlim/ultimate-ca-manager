import { useState, useEffect } from 'react'
import { Certificate, MagnifyingGlass, Funnel, Download, ArrowsClockwise, XCircle, Eye, Plus, Check } from '@phosphor-icons/react'
import { api } from '../lib/api'
import './Certificates.css'

export default function Certificates() {
  const [certificates, setCertificates] = useState([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({
    status: 'all',
    ca: 'all',
    search: ''
  })
  const [selectedCerts, setSelectedCerts] = useState([])
  const [showDetailsModal, setShowDetailsModal] = useState(false)
  const [showIssueModal, setShowIssueModal] = useState(false)
  const [selectedCert, setSelectedCert] = useState(null)
  
  useEffect(() => {
    fetchCertificates()
  }, [])
  
  async function fetchCertificates() {
    try {
      // Mock data
      const mockCerts = [
        {
          id: 1,
          commonName: 'api.example.com',
          subject: 'CN=api.example.com, O=Example Inc, C=US',
          issuer: 'CN=Intermediate CA Production, O=UCM, C=US',
          serialNumber: '0xABCD1234',
          status: 'active',
          validFrom: '2024-01-15',
          validTo: '2025-01-15',
          daysRemaining: 354,
          keyUsage: 'Digital Signature, Key Encipherment',
          extKeyUsage: 'TLS Web Server Authentication',
          san: 'DNS:api.example.com, DNS:www.example.com',
          algorithm: 'SHA256-RSA',
          keySize: 2048
        },
        {
          id: 2,
          commonName: 'mail.company.com',
          subject: 'CN=mail.company.com, O=Company Ltd, C=UK',
          issuer: 'CN=Intermediate CA Production, O=UCM, C=US',
          serialNumber: '0x5678ABCD',
          status: 'active',
          validFrom: '2024-03-01',
          validTo: '2026-03-01',
          daysRemaining: 765,
          keyUsage: 'Digital Signature',
          extKeyUsage: 'Email Protection',
          san: 'DNS:mail.company.com, DNS:smtp.company.com',
          algorithm: 'SHA256-RSA',
          keySize: 4096
        },
        {
          id: 3,
          commonName: 'old-server.local',
          subject: 'CN=old-server.local, O=Legacy Systems, C=US',
          issuer: 'CN=Root CA 2020, O=UCM Legacy, C=US',
          serialNumber: '0x99887766',
          status: 'expired',
          validFrom: '2020-06-01',
          validTo: '2024-06-01',
          daysRemaining: -208,
          keyUsage: 'Digital Signature, Key Encipherment',
          extKeyUsage: 'TLS Web Server Authentication',
          san: 'DNS:old-server.local',
          algorithm: 'SHA1-RSA',
          keySize: 1024
        },
        {
          id: 4,
          commonName: '*.staging.com',
          subject: 'CN=*.staging.com, O=DevOps Team, C=US',
          issuer: 'CN=Intermediate CA Development, O=UCM, C=US',
          serialNumber: '0xDEADBEEF',
          status: 'active',
          validFrom: '2024-01-01',
          validTo: '2025-01-01',
          daysRemaining: 340,
          keyUsage: 'Digital Signature, Key Encipherment',
          extKeyUsage: 'TLS Web Server Authentication',
          san: 'DNS:*.staging.com, DNS:staging.com',
          algorithm: 'SHA256-RSA',
          keySize: 2048
        },
        {
          id: 5,
          commonName: 'test.local',
          subject: 'CN=test.local, O=Test, C=US',
          issuer: 'CN=Intermediate CA Development, O=UCM, C=US',
          serialNumber: '0x11111111',
          status: 'revoked',
          validFrom: '2023-01-01',
          validTo: '2025-01-01',
          daysRemaining: 340,
          revokedDate: '2024-01-20',
          revokedReason: 'Key Compromise',
          keyUsage: 'Digital Signature',
          extKeyUsage: 'TLS Web Server Authentication',
          san: 'DNS:test.local',
          algorithm: 'SHA256-RSA',
          keySize: 2048
        },
        {
          id: 6,
          commonName: 'vpn.company.com',
          subject: 'CN=vpn.company.com, O=Company Ltd, C=UK',
          issuer: 'CN=Intermediate CA Production, O=UCM, C=US',
          serialNumber: '0xCAFEBABE',
          status: 'expiring',
          validFrom: '2024-01-01',
          validTo: '2024-02-15',
          daysRemaining: 20,
          keyUsage: 'Digital Signature, Key Encipherment',
          extKeyUsage: 'TLS Web Server Authentication, TLS Web Client Authentication',
          san: 'DNS:vpn.company.com, IP:192.168.1.100',
          algorithm: 'SHA256-RSA',
          keySize: 2048
        }
      ]
      
      setCertificates(mockCerts)
      setLoading(false)
    } catch (err) {
      console.error('Error fetching certificates:', err)
      setLoading(false)
    }
  }
  
  function getFilteredCertificates() {
    return certificates.filter(cert => {
      if (filters.status !== 'all' && cert.status !== filters.status) return false
      if (filters.search && !cert.commonName.toLowerCase().includes(filters.search.toLowerCase()) &&
          !cert.subject.toLowerCase().includes(filters.search.toLowerCase())) return false
      return true
    })
  }
  
  function getStatusColor(status) {
    switch (status) {
      case 'active': return 'success'
      case 'expiring': return 'warning'
      case 'expired': return 'danger'
      case 'revoked': return 'gray'
      default: return 'gray'
    }
  }
  
  function handleSelectAll(e) {
    if (e.target.checked) {
      setSelectedCerts(getFilteredCertificates().map(c => c.id))
    } else {
      setSelectedCerts([])
    }
  }
  
  function handleSelectCert(id) {
    if (selectedCerts.includes(id)) {
      setSelectedCerts(selectedCerts.filter(cid => cid !== id))
    } else {
      setSelectedCerts([...selectedCerts, id])
    }
  }
  
  if (loading) {
    return (
      <div className="certificates-page">
        <h1>Certificates</h1>
        <p>Loading...</p>
      </div>
    )
  }
  
  const filtered = getFilteredCertificates()
  
  return (
    <div className="certificates-page">
      <div className="page-header">
        <div>
          <h1>Certificates</h1>
          <p className="subtitle">{certificates.length} certificates total</p>
        </div>
        <div className="page-actions">
          <button className="btn-primary" onClick={() => setShowIssueModal(true)}>
            <Plus size={16} />
            Issue Certificate
          </button>
        </div>
      </div>
      
      <div className="filters-bar">
        <div className="search-box">
          <MagnifyingGlass size={18} />
          <input
            type="text"
            placeholder="Search certificates..."
            value={filters.search}
            onChange={e => setFilters({...filters, search: e.target.value})}
          />
        </div>
        
        <div className="filter-group">
          <Funnel size={18} />
          <select value={filters.status} onChange={e => setFilters({...filters, status: e.target.value})}>
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="expiring">Expiring Soon</option>
            <option value="expired">Expired</option>
            <option value="revoked">Revoked</option>
          </select>
          
          <select value={filters.ca} onChange={e => setFilters({...filters, ca: e.target.value})}>
            <option value="all">All CAs</option>
            <option value="prod">Production CA</option>
            <option value="dev">Development CA</option>
          </select>
        </div>
        
        {selectedCerts.length > 0 && (
          <div className="bulk-actions">
            <span>{selectedCerts.length} selected</span>
            <button className="btn-secondary">
              <Download size={16} />
              Export Selected
            </button>
            <button className="btn-secondary">
              <XCircle size={16} />
              Revoke Selected
            </button>
          </div>
        )}
      </div>
      
      <div className="certificates-table-container">
        <table className="certificates-table">
          <thead>
            <tr>
              <th style={{width: '40px'}}>
                <input
                  type="checkbox"
                  checked={selectedCerts.length === filtered.length && filtered.length > 0}
                  onChange={handleSelectAll}
                />
              </th>
              <th>Common Name</th>
              <th>Issuer</th>
              <th>Status</th>
              <th>Valid Until</th>
              <th>Days Left</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(cert => (
              <tr key={cert.id} className={selectedCerts.includes(cert.id) ? 'selected' : ''}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedCerts.includes(cert.id)}
                    onChange={() => handleSelectCert(cert.id)}
                  />
                </td>
                <td className="cert-cn">
                  <Certificate size={16} />
                  <span>{cert.commonName}</span>
                </td>
                <td className="cert-issuer">{cert.issuer.split(',')[0].replace('CN=', '')}</td>
                <td>
                  <span className={`status-badge ${getStatusColor(cert.status)}`}>
                    {cert.status}
                  </span>
                </td>
                <td>{cert.validTo}</td>
                <td className={cert.daysRemaining < 30 ? 'days-warning' : cert.daysRemaining < 0 ? 'days-expired' : ''}>
                  {cert.daysRemaining > 0 ? `${cert.daysRemaining} days` : 'Expired'}
                </td>
                <td className="cert-actions">
                  <button className="icon-btn" onClick={() => { setSelectedCert(cert); setShowDetailsModal(true); }} title="View details">
                    <Eye size={16} />
                  </button>
                  {cert.status === 'active' && (
                    <>
                      <button className="icon-btn" title="Renew">
                        <ArrowsClockwise size={16} />
                      </button>
                      <button className="icon-btn" title="Revoke">
                        <XCircle size={16} />
                      </button>
                    </>
                  )}
                  <button className="icon-btn" title="Download">
                    <Download size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {showDetailsModal && selectedCert && (
        <CertificateDetailsModal cert={selectedCert} onClose={() => setShowDetailsModal(false)} />
      )}
      
      {showIssueModal && (
        <IssueCertificateModal onClose={() => setShowIssueModal(false)} onIssue={fetchCertificates} />
      )}
    </div>
  )
}

function CertificateDetailsModal({ cert, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Certificate Details</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="detail-group">
            <label>Common Name (CN)</label>
            <p>{cert.commonName}</p>
          </div>
          
          <div className="detail-group">
            <label>Subject</label>
            <p className="monospace">{cert.subject}</p>
          </div>
          
          <div className="detail-group">
            <label>Issuer</label>
            <p className="monospace">{cert.issuer}</p>
          </div>
          
          <div className="detail-row">
            <div className="detail-group">
              <label>Serial Number</label>
              <p className="monospace">{cert.serialNumber}</p>
            </div>
            <div className="detail-group">
              <label>Algorithm</label>
              <p>{cert.algorithm}</p>
            </div>
          </div>
          
          <div className="detail-row">
            <div className="detail-group">
              <label>Valid From</label>
              <p>{cert.validFrom}</p>
            </div>
            <div className="detail-group">
              <label>Valid To</label>
              <p>{cert.validTo}</p>
            </div>
          </div>
          
          <div className="detail-group">
            <label>Status</label>
            <p>
              <span className={`status-badge ${cert.status === 'active' ? 'success' : cert.status === 'expired' ? 'danger' : 'gray'}`}>
                {cert.status}
              </span>
              {cert.status === 'revoked' && cert.revokedReason && (
                <span className="revoked-info"> - {cert.revokedReason} ({cert.revokedDate})</span>
              )}
            </p>
          </div>
          
          <div className="detail-group">
            <label>Key Usage</label>
            <p>{cert.keyUsage}</p>
          </div>
          
          <div className="detail-group">
            <label>Extended Key Usage</label>
            <p>{cert.extKeyUsage}</p>
          </div>
          
          <div className="detail-group">
            <label>Subject Alternative Names (SAN)</label>
            <p>{cert.san}</p>
          </div>
          
          <div className="detail-row">
            <div className="detail-group">
              <label>Key Size</label>
              <p>{cert.keySize} bits</p>
            </div>
            <div className="detail-group">
              <label>Days Remaining</label>
              <p className={cert.daysRemaining < 30 ? 'text-warning' : cert.daysRemaining < 0 ? 'text-danger' : ''}>
                {cert.daysRemaining > 0 ? `${cert.daysRemaining} days` : 'Expired'}
              </p>
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Close</button>
          <button className="btn-primary">
            <Download size={16} />
            Download PEM
          </button>
        </div>
      </div>
    </div>
  )
}

function IssueCertificateModal({ onClose, onIssue }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Issue New Certificate</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label>Issuing CA</label>
            <select>
              <option>Intermediate CA - Production</option>
              <option>Intermediate CA - Development</option>
              <option>Sub CA - Web Services</option>
            </select>
          </div>
          
          <div className="form-group">
            <label>Common Name (CN)</label>
            <input type="text" placeholder="e.g., www.example.com" />
          </div>
          
          <div className="form-group">
            <label>Organization (O)</label>
            <input type="text" placeholder="e.g., Example Inc" />
          </div>
          
          <div className="form-row">
            <div className="form-group">
              <label>Country (C)</label>
              <input type="text" placeholder="e.g., US" maxLength="2" />
            </div>
            <div className="form-group">
              <label>State/Province (ST)</label>
              <input type="text" placeholder="e.g., California" />
            </div>
            <div className="form-group">
              <label>Locality (L)</label>
              <input type="text" placeholder="e.g., San Francisco" />
            </div>
          </div>
          
          <div className="form-group">
            <label>Subject Alternative Names (SAN)</label>
            <input type="text" placeholder="e.g., www.example.com,mail.example.com" />
            <span className="form-hint">Comma-separated list of DNS names or IPs</span>
          </div>
          
          <div className="form-row">
            <div className="form-group">
              <label>Validity (days)</label>
              <input type="number" defaultValue={365} min="1" max="825" />
            </div>
            <div className="form-group">
              <label>Key Size</label>
              <select defaultValue="2048">
                <option value="2048">2048 bits</option>
                <option value="4096">4096 bits</option>
              </select>
            </div>
          </div>
          
          <div className="form-group">
            <label>Key Usage</label>
            <div className="checkbox-group">
              <label><input type="checkbox" defaultChecked /> Digital Signature</label>
              <label><input type="checkbox" defaultChecked /> Key Encipherment</label>
              <label><input type="checkbox" /> Data Encipherment</label>
            </div>
          </div>
          
          <div className="form-group">
            <label>Extended Key Usage</label>
            <div className="checkbox-group">
              <label><input type="checkbox" defaultChecked /> TLS Web Server Authentication</label>
              <label><input type="checkbox" /> TLS Web Client Authentication</label>
              <label><input type="checkbox" /> Email Protection</label>
              <label><input type="checkbox" /> Code Signing</label>
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => { onIssue(); onClose(); }}>
            <Check size={16} />
            Issue Certificate
          </button>
        </div>
      </div>
    </div>
  )
}
