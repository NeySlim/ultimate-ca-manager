import { useState } from 'react'
import { Gear, EnvelopeSimple, IdentificationCard, Broadcast, Database, DownloadSimple } from '@phosphor-icons/react'
import { api } from '../lib/api'
import './Settings.css'

export default function Settings() {
  const [activeTab, setActiveTab] = useState('general')
  
  const tabs = [
    { id: 'general', label: 'General', icon: Gear },
    { id: 'email', label: 'Email', icon: EnvelopeSimple },
    { id: 'ldap', label: 'LDAP', icon: IdentificationCard },
    { id: 'webhooks', label: 'Webhooks', icon: Broadcast },
    { id: 'backup', label: 'Backup', icon: Database },
    { id: 'import', label: 'Import', icon: DownloadSimple }
  ]
  
  return (
    <div className="settings-page">
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p className="subtitle">Configure UCM system settings</p>
        </div>
      </div>
      
      <div className="settings-container">
        <div className="settings-tabs">
          {tabs.map(tab => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                className={`settings-tab ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                <Icon size={20} />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </div>
        
        <div className="settings-content">
          {activeTab === 'general' && <GeneralTab />}
          {activeTab === 'email' && <EmailTab />}
          {activeTab === 'ldap' && <LDAPTab />}
          {activeTab === 'webhooks' && <WebhooksTab />}
          {activeTab === 'backup' && <BackupTab />}
          {activeTab === 'import' && <ImportTab />}
        </div>
      </div>
    </div>
  )
}

function GeneralTab() {
  return (
    <div className="settings-tab-content">
      <h2>General Settings</h2>
      <div className="form-group">
        <label>System FQDN</label>
        <input type="text" defaultValue="ucm.example.com" />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>HTTPS Port</label>
          <input type="number" defaultValue={8443} />
        </div>
        <div className="form-group">
          <label>Session Timeout (minutes)</label>
          <input type="number" defaultValue={30} />
        </div>
      </div>
      <div className="form-actions">
        <button className="btn-secondary">Reset</button>
        <button className="btn-primary">Save Changes</button>
      </div>
    </div>
  )
}

function EmailTab() {
  return (
    <div className="settings-tab-content">
      <h2>Email Notifications</h2>
      <div className="form-group">
        <label>SMTP Server</label>
        <input type="text" placeholder="smtp.example.com" />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>SMTP Port</label>
          <input type="number" defaultValue={587} />
        </div>
        <div className="form-group">
          <label>Encryption</label>
          <select defaultValue="tls">
            <option value="none">None</option>
            <option value="tls">TLS</option>
            <option value="ssl">SSL</option>
          </select>
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Username</label>
          <input type="text" />
        </div>
        <div className="form-group">
          <label>Password</label>
          <input type="password" />
        </div>
      </div>
      <div className="form-actions">
        <button className="btn-secondary">Test Connection</button>
        <button className="btn-primary">Save Changes</button>
      </div>
    </div>
  )
}

function LDAPTab() {
  return (
    <div className="settings-tab-content">
      <h2>LDAP Authentication</h2>
      <div className="form-group">
        <label>LDAP Server</label>
        <input type="text" placeholder="ldap://dc.example.com" />
      </div>
      <div className="form-group">
        <label>Base DN</label>
        <input type="text" placeholder="dc=example,dc=com" />
      </div>
      <div className="form-group">
        <label>Bind DN</label>
        <input type="text" placeholder="cn=admin,dc=example,dc=com" />
      </div>
      <div className="form-group">
        <label>Bind Password</label>
        <input type="password" />
      </div>
      <div className="form-actions">
        <button className="btn-secondary">Test Connection</button>
        <button className="btn-primary">Save Changes</button>
      </div>
    </div>
  )
}

function WebhooksTab() {
  return (
    <div className="settings-tab-content">
      <h2>Webhooks</h2>
      <p className="tab-description">Configure webhook endpoints for certificate events</p>
      <div className="webhooks-list">
        <div className="webhook-item">
          <div className="webhook-info">
            <strong>Certificate Issued</strong>
            <p className="monospace small">https://api.example.com/webhooks/cert-issued</p>
          </div>
          <button className="btn-secondary small">Edit</button>
        </div>
        <div className="webhook-item">
          <div className="webhook-info">
            <strong>Certificate Revoked</strong>
            <p className="monospace small">https://api.example.com/webhooks/cert-revoked</p>
          </div>
          <button className="btn-secondary small">Edit</button>
        </div>
      </div>
      <button className="btn-primary">Add Webhook</button>
    </div>
  )
}

function BackupTab() {
  return (
    <div className="settings-tab-content">
      <h2>Backup & Restore</h2>
      <div className="backup-section">
        <h3>Export Database</h3>
        <p>Export all certificates, CAs, and settings</p>
        <button className="btn-primary">Download Backup</button>
      </div>
      <div className="backup-section">
        <h3>Import Database</h3>
        <p>Restore from a previous backup</p>
        <input type="file" accept=".db,.sql,.zip" />
        <button className="btn-secondary">Upload & Restore</button>
      </div>
      <div className="backup-section warning">
        <h3>⚠️ Danger Zone</h3>
        <p>Reset all data and start fresh</p>
        <button className="btn-danger">Reset Database</button>
      </div>
    </div>
  )
}

function ImportTab() {
  const [config, setConfig] = useState({
    host: '',
    port: 443,
    api_key: '',
    api_secret: '',
    verify_ssl: false
  })
  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [testing, setTesting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  
  async function handleTestConnection() {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.testOPNsenseConnection(config)
      if (result.success) {
        setItems(result.items || [])
        setStats(result.stats)
        setTestResult({ success: true, message: `Found ${result.stats.cas} CAs and ${result.stats.certificates} certificates` })
      } else {
        setTestResult({ success: false, message: result.error || 'Connection failed' })
      }
    } catch (err) {
      setTestResult({ success: false, message: err.message })
    } finally {
      setTesting(false)
    }
  }
  
  async function handleImport() {
    const selectedIds = items.filter(item => item.selected).map(item => item.id)
    if (selectedIds.length === 0) {
      alert('Please select at least one item to import')
      return
    }
    
    setImporting(true)
    try {
      const result = await api.importFromOPNsense({
        ...config,
        items: selectedIds
      })
      
      if (result.success) {
        alert(`Successfully imported ${result.imported.cas} CAs and ${result.imported.certificates} certificates!\nSkipped: ${result.skipped}`)
        // Reset
        setItems([])
        setStats(null)
        setTestResult(null)
      } else {
        alert('Import failed: ' + (result.error || 'Unknown error'))
      }
    } catch (err) {
      alert('Import failed: ' + err.message)
    } finally {
      setImporting(false)
    }
  }
  
  function toggleItem(id) {
    setItems(items.map(item => 
      item.id === id ? { ...item, selected: !item.selected } : item
    ))
  }
  
  function toggleAll() {
    const allSelected = items.every(item => item.selected)
    setItems(items.map(item => ({ ...item, selected: !allSelected })))
  }
  
  return (
    <div className="settings-tab-content">
      <h2>Import from OPNsense</h2>
      <p style={{ marginBottom: '24px', color: 'var(--text-secondary)' }}>
        Connect to your OPNsense firewall and import Certificate Authorities and Certificates
      </p>
      
      <div className="form-row">
        <div className="form-group" style={{ flex: 2 }}>
          <label>OPNsense Host *</label>
          <input 
            type="text" 
            value={config.host}
            onChange={e => setConfig({ ...config, host: e.target.value })}
            placeholder="192.168.1.1 or opnsense.example.com"
          />
        </div>
        <div className="form-group" style={{ flex: 1 }}>
          <label>Port</label>
          <input 
            type="number" 
            value={config.port}
            onChange={e => setConfig({ ...config, port: parseInt(e.target.value) })}
          />
        </div>
      </div>
      
      <div className="form-row">
        <div className="form-group">
          <label>API Key *</label>
          <input 
            type="text" 
            value={config.api_key}
            onChange={e => setConfig({ ...config, api_key: e.target.value })}
            placeholder="Enter OPNsense API key"
          />
        </div>
        <div className="form-group">
          <label>API Secret *</label>
          <input 
            type="password" 
            value={config.api_secret}
            onChange={e => setConfig({ ...config, api_secret: e.target.value })}
            placeholder="Enter OPNsense API secret"
          />
        </div>
      </div>
      
      <div className="form-group">
        <label className="checkbox-label">
          <input 
            type="checkbox"
            checked={config.verify_ssl}
            onChange={e => setConfig({ ...config, verify_ssl: e.target.checked })}
          />
          Verify SSL certificate
        </label>
        <small>Disable this if OPNsense uses a self-signed certificate</small>
      </div>
      
      <div className="form-actions">
        <button 
          className="btn-primary" 
          onClick={handleTestConnection}
          disabled={testing || !config.host || !config.api_key || !config.api_secret}
        >
          {testing ? 'Testing...' : 'Test Connection'}
        </button>
      </div>
      
      {testResult && (
        <div className={`alert ${testResult.success ? 'alert-success' : 'alert-error'}`} style={{ marginTop: '16px' }}>
          {testResult.message}
        </div>
      )}
      
      {items.length > 0 && (
        <>
          <div style={{ marginTop: '32px', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3>Available Items ({items.length})</h3>
            <button className="btn-secondary" onClick={toggleAll}>
              {items.every(item => item.selected) ? 'Deselect All' : 'Select All'}
            </button>
          </div>
          
          <div style={{ maxHeight: '400px', overflow: 'auto', border: '1px solid var(--border-color)', borderRadius: '8px' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '40px' }}>
                    <input 
                      type="checkbox" 
                      checked={items.every(item => item.selected)}
                      onChange={toggleAll}
                    />
                  </th>
                  <th>Type</th>
                  <th>Name</th>
                  <th>Subject</th>
                  <th>Valid Until</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id}>
                    <td>
                      <input 
                        type="checkbox" 
                        checked={item.selected}
                        onChange={() => toggleItem(item.id)}
                      />
                    </td>
                    <td>
                      <span className={`badge ${item.type === 'CA' ? 'badge-primary' : 'badge-secondary'}`}>
                        {item.type}
                      </span>
                    </td>
                    <td>{item.name}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: '12px' }}>{item.subject}</td>
                    <td>{item.validUntil}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          <div className="form-actions" style={{ marginTop: '24px' }}>
            <button 
              className="btn-primary" 
              onClick={handleImport}
              disabled={importing || !items.some(item => item.selected)}
            >
              {importing ? 'Importing...' : `Import Selected (${items.filter(i => i.selected).length})`}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
