import { useState } from 'react'
import { Gear, EnvelopeSimple, IdentificationCard, Broadcast, Database } from '@phosphor-icons/react'
import './Settings.css'

export default function Settings() {
  const [activeTab, setActiveTab] = useState('general')
  
  const tabs = [
    { id: 'general', label: 'General', icon: Gear },
    { id: 'email', label: 'Email', icon: EnvelopeSimple },
    { id: 'ldap', label: 'LDAP', icon: IdentificationCard },
    { id: 'webhooks', label: 'Webhooks', icon: Broadcast },
    { id: 'backup', label: 'Backup', icon: Database }
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
