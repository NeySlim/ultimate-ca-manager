import React, { useState } from 'react';
import { Cloud, Plus, Users, ShoppingCart, Calendar, ChartLine, FloppyDisk, Copy, Funnel, CheckCircle, ArrowsLeftRight, Database } from '@phosphor-icons/react';
import './ACMEPage.css';

const ACMEPage = () => {
  const [activeTab, setActiveTab] = useState('internal');

  return (
    <div className="content">
      {/* TABS */}
      <div className="tabs">
        <button className={`tab ${activeTab === 'internal' ? 'active' : ''}`} onClick={() => setActiveTab('internal')}>
          Internal ACME
        </button>
        <button className={`tab ${activeTab === 'leproxy' ? 'active' : ''}`} onClick={() => setActiveTab('leproxy')}>
          Let's Encrypt Proxy
        </button>
      </div>

      {/* TAB 1: INTERNAL ACME */}
      {activeTab === 'internal' && (
        <div className="tab-content active">
          {/* STATS ROW */}
          <div className="stats-row">
            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Total Accounts</span>
                <Users className="stat-icon" size={20} />
              </div>
              <div className="stat-value">23</div>
              <div className="stat-description">18 active, 5 disabled</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Total Orders</span>
                <ShoppingCart className="stat-icon" size={20} />
              </div>
              <div className="stat-value">156</div>
              <div className="stat-description">12 pending, 144 valid</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">This Month</span>
                <Calendar className="stat-icon" size={20} />
              </div>
              <div className="stat-value">42</div>
              <div className="stat-description">+15% vs last month</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Success Rate</span>
                <ChartLine className="stat-icon" size={20} />
              </div>
              <div className="stat-value">97.3%</div>
              <div className="stat-description">4 failed validations</div>
            </div>
          </div>

          {/* ACME CONFIGURATION */}
          <div className="config-section">
            <div className="config-header">
              <span className="config-title">Internal ACME Configuration</span>
              <button className="btn btn-primary">
                <FloppyDisk size={16} />
                Save Changes
              </button>
            </div>
            <div className="config-content">
              <div className="config-row">
                <div className="config-group">
                  <label className="config-label">Directory URL</label>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="text" className="config-input" value="https://acme.ucm.local/directory" readOnly style={{ flex: 1 }} />
                    <button className="btn" style={{ flexShrink: 0 }}>
                      <Copy size={16} />
                    </button>
                  </div>
                </div>
                <div className="config-group">
                  <label className="config-label">Certificate Authority</label>
                  <select className="config-select">
                    <option>Internal Root CA</option>
                    <option>Production Intermediate CA</option>
                    <option>Development Intermediate CA</option>
                    <option>ECDSA Root CA</option>
                  </select>
                </div>
                <div className="config-group">
                  <label className="config-label">Default Certificate Validity</label>
                  <div className="config-input-unit">
                    <input type="number" className="config-input" defaultValue="90" />
                    <span className="config-unit">days</span>
                  </div>
                </div>
                <div className="config-group">
                  <label className="config-label">Require External Account Binding</label>
                  <input type="checkbox" className="config-checkbox" />
                </div>
              </div>
            </div>
          </div>

          {/* TWO COLUMNS */}
          <div className="two-columns">
            {/* ACCOUNTS COLUMN */}
            <div className="column-section">
              <div className="section-header">
                <span className="section-title">ACME Accounts</span>
                <button className="btn">
                  <Funnel size={16} />
                  Filter
                </button>
              </div>
              <div className="section-content">
                <table>
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Orders</th>
                      <th>Status</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="mono">admin@example.com</td>
                      <td>28</td>
                      <td><span className="badge badge-success">Active</span></td>
                      <td>2024-01-15</td>
                    </tr>
                    <tr>
                      <td className="mono">ops@company.io</td>
                      <td>19</td>
                      <td><span className="badge badge-success">Active</span></td>
                      <td>2024-01-18</td>
                    </tr>
                    <tr>
                      <td className="mono">devops@startup.dev</td>
                      <td>15</td>
                      <td><span className="badge badge-success">Active</span></td>
                      <td>2024-02-03</td>
                    </tr>
                    <tr>
                      <td className="mono">ssl@webhost.net</td>
                      <td>12</td>
                      <td><span className="badge badge-success">Active</span></td>
                      <td>2024-02-12</td>
                    </tr>
                    <tr>
                      <td className="mono">certs@platform.tech</td>
                      <td>11</td>
                      <td><span className="badge badge-success">Active</span></td>
                      <td>2024-02-20</td>
                    </tr>
                    <tr>
                      <td className="mono">security@corp.com</td>
                      <td>9</td>
                      <td><span className="badge badge-success">Active</span></td>
                      <td>2024-02-28</td>
                    </tr>
                    <tr>
                      <td className="mono">infra@cloud.services</td>
                      <td>8</td>
                      <td><span className="badge badge-success">Active</span></td>
                      <td>2024-03-05</td>
                    </tr>
                    <tr>
                      <td className="mono">automation@deploy.ai</td>
                      <td>7</td>
                      <td><span className="badge badge-success">Active</span></td>
                      <td>2024-03-08</td>
                    </tr>
                    <tr>
                      <td className="mono">tls@secure.zone</td>
                      <td>6</td>
                      <td><span className="badge badge-success">Active</span></td>
                      <td>2024-03-10</td>
                    </tr>
                    <tr>
                      <td className="mono">legacy@old-system.org</td>
                      <td>5</td>
                      <td><span className="badge badge-warning">Disabled</span></td>
                      <td>2023-11-22</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* ORDERS COLUMN */}
            <div className="column-section">
              <div className="section-header">
                <span className="section-title">Recent Orders</span>
                <button className="btn">
                  <Funnel size={16} />
                  Filter
                </button>
              </div>
              <div className="section-content">
                <table>
                  <thead>
                    <tr>
                      <th>Domain</th>
                      <th>Account</th>
                      <th>Status</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="mono">api.example.com</td>
                      <td className="mono">admin@example.com</td>
                      <td><span className="badge badge-success">Valid</span></td>
                      <td>2024-03-17</td>
                    </tr>
                    <tr>
                      <td className="mono">app.company.io</td>
                      <td className="mono">ops@company.io</td>
                      <td><span className="badge badge-success">Valid</span></td>
                      <td>2024-03-17</td>
                    </tr>
                    <tr>
                      <td className="mono">*.startup.dev</td>
                      <td className="mono">devops@startup.dev</td>
                      <td><span className="badge badge-info">Pending</span></td>
                      <td>2024-03-17</td>
                    </tr>
                    <tr>
                      <td className="mono">cdn.webhost.net</td>
                      <td className="mono">ssl@webhost.net</td>
                      <td><span className="badge badge-success">Valid</span></td>
                      <td>2024-03-16</td>
                    </tr>
                    <tr>
                      <td className="mono">dashboard.platform.tech</td>
                      <td className="mono">certs@platform.tech</td>
                      <td><span className="badge badge-success">Valid</span></td>
                      <td>2024-03-16</td>
                    </tr>
                    <tr>
                      <td className="mono">vpn.corp.com</td>
                      <td className="mono">security@corp.com</td>
                      <td><span className="badge badge-success">Valid</span></td>
                      <td>2024-03-16</td>
                    </tr>
                    <tr>
                      <td className="mono">*.cloud.services</td>
                      <td className="mono">infra@cloud.services</td>
                      <td><span className="badge badge-info">Pending</span></td>
                      <td>2024-03-15</td>
                    </tr>
                    <tr>
                      <td className="mono">ci.deploy.ai</td>
                      <td className="mono">automation@deploy.ai</td>
                      <td><span className="badge badge-success">Valid</span></td>
                      <td>2024-03-15</td>
                    </tr>
                    <tr>
                      <td className="mono">mail.secure.zone</td>
                      <td className="mono">tls@secure.zone</td>
                      <td><span className="badge badge-success">Valid</span></td>
                      <td>2024-03-15</td>
                    </tr>
                    <tr>
                      <td className="mono">staging.env</td>
                      <td className="mono">test@staging.env</td>
                      <td><span className="badge badge-success">Valid</span></td>
                      <td>2024-03-14</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: LETSENCRYPT PROXY */}
      {activeTab === 'leproxy' && (
        <div className="tab-content active">
          {/* STATS ROW */}
          <div className="stats-row">
            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Proxy Enabled</span>
                <CheckCircle className="stat-icon" size={20} style={{ color: 'var(--status-success)' }} />
              </div>
              <div className="stat-value">Active</div>
              <div className="stat-description">Forwarding to production</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Proxied Requests</span>
                <ArrowsLeftRight className="stat-icon" size={20} />
              </div>
              <div className="stat-value">387</div>
              <div className="stat-description">+23 this week</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Success Rate</span>
                <ChartLine className="stat-icon" size={20} />
              </div>
              <div className="stat-value">98.7%</div>
              <div className="stat-description">5 failed validations</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Cached Certs</span>
                <Database className="stat-icon" size={20} />
              </div>
              <div className="stat-value">142</div>
              <div className="stat-description">45.2 MB total</div>
            </div>
          </div>

          {/* PROXY CONFIG */}
          <div className="config-section">
            <div className="config-header">
              <span className="config-title">Proxy Configuration</span>
              <button className="btn btn-primary">
                <FloppyDisk size={16} />
                Save Changes
              </button>
            </div>
            <div className="config-content">
              <div className="config-row">
                <div className="config-group">
                  <label className="config-label">Proxy Enabled</label>
                  <input type="checkbox" className="config-checkbox" defaultChecked />
                </div>
                <div className="config-group">
                  <label className="config-label">Proxy Directory URL</label>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="text" className="config-input" value="https://acme.ucm.local/le-proxy/directory" readOnly style={{ flex: 1 }} />
                    <button className="btn" style={{ flexShrink: 0 }}>
                      <Copy size={16} />
                    </button>
                  </div>
                </div>
                <div className="config-group">
                  <label className="config-label">Upstream Server</label>
                  <select className="config-select">
                    <option>Let's Encrypt Production</option>
                    <option>Let's Encrypt Staging</option>
                  </select>
                </div>
                <div className="config-group">
                  <label className="config-label">Cache Certificates</label>
                  <input type="checkbox" className="config-checkbox" defaultChecked />
                </div>
              </div>
              <div className="config-info" style={{ marginTop: 'var(--spacing-lg)', padding: 'var(--spacing-md)', background: 'var(--bg-tertiary)', border: '1px solid var(--border-primary)', borderRadius: 'var(--radius)', fontSize: '12px', color: 'var(--text-secondary)' }}>
                <i className="ph ph-info" style={{ color: 'var(--status-info)' }}></i>
                Proxy mode allows clients to obtain certificates from Let's Encrypt through UCM. All requests to the proxy directory are transparently forwarded to the upstream Let's Encrypt server.
              </div>
            </div>
          </div>

          {/* PROXY REQUESTS TABLE */}
          <div className="column-section">
            <div className="section-header">
              <span className="section-title">Recent Proxy Requests</span>
              <button className="btn">
                <Funnel size={16} />
                Filter
              </button>
            </div>
            <div className="section-content">
              <table>
                <thead>
                  <tr>
                    <th>Domain</th>
                    <th>Client IP</th>
                    <th>Status</th>
                    <th>Upstream Response</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="mono">shop.example.com</td>
                    <td className="mono">192.168.1.50</td>
                    <td><span className="badge badge-success">Issued</span></td>
                    <td>200 OK</td>
                    <td>2024-03-17 14:23</td>
                  </tr>
                  <tr>
                    <td className="mono">blog.startup.io</td>
                    <td className="mono">10.0.5.120</td>
                    <td><span className="badge badge-success">Issued</span></td>
                    <td>200 OK</td>
                    <td>2024-03-17 13:45</td>
                  </tr>
                  <tr>
                    <td className="mono">*.cloud-apps.dev</td>
                    <td className="mono">172.16.8.90</td>
                    <td><span className="badge badge-info">Pending</span></td>
                    <td>202 Accepted</td>
                    <td>2024-03-17 13:12</td>
                  </tr>
                  <tr>
                    <td className="mono">api.platform.tech</td>
                    <td className="mono">192.168.1.51</td>
                    <td><span className="badge badge-success">Issued</span></td>
                    <td>200 OK</td>
                    <td>2024-03-17 12:58</td>
                  </tr>
                  <tr>
                    <td className="mono">cdn.webhost.net</td>
                    <td className="mono">10.0.5.121</td>
                    <td><span className="badge badge-success">Issued</span></td>
                    <td>200 OK</td>
                    <td>2024-03-17 11:34</td>
                  </tr>
                  <tr>
                    <td className="mono">test.invalid-domain.xyz</td>
                    <td className="mono">192.168.1.52</td>
                    <td><span className="badge badge-error">Failed</span></td>
                    <td>400 Bad Request</td>
                    <td>2024-03-17 10:22</td>
                  </tr>
                  <tr>
                    <td className="mono">mail.secure.zone</td>
                    <td className="mono">172.16.8.91</td>
                    <td><span className="badge badge-success">Issued</span></td>
                    <td>200 OK</td>
                    <td>2024-03-17 09:47</td>
                  </tr>
                  <tr>
                    <td className="mono">vpn.corp.com</td>
                    <td className="mono">10.0.5.122</td>
                    <td><span className="badge badge-success">Issued</span></td>
                    <td>200 OK</td>
                    <td>2024-03-17 08:15</td>
                  </tr>
                  <tr>
                    <td className="mono">*.microservices.app</td>
                    <td className="mono">192.168.1.53</td>
                    <td><span className="badge badge-info">Pending</span></td>
                    <td>202 Accepted</td>
                    <td>2024-03-17 07:33</td>
                  </tr>
                  <tr>
                    <td className="mono">gateway.edge.network</td>
                    <td className="mono">172.16.8.92</td>
                    <td><span className="badge badge-success">Issued</span></td>
                    <td>200 OK</td>
                    <td>2024-03-16 23:41</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ACMEPage;
