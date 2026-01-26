import React, { useState } from 'react';
import { DeviceMobile, DownloadSimple, Key, FloppyDisk, Copy, Funnel, ArrowsClockwise, Calendar, ChartLine, ArrowDownLeft } from '@phosphor-icons/react';
import './SCEPPage.css';

const SCEPPage = () => {
  return (
    <div className="content">
      {/* STATS ROW */}
      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Total Devices</span>
            <DeviceMobile className="stat-icon" size={20} />
          </div>
          <div className="stat-value">47</div>
          <div className="stat-description">43 active, 4 expired</div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Enrollments</span>
            <ArrowDownLeft className="stat-icon" size={20} />
          </div>
          <div className="stat-value">89</div>
          <div className="stat-description">7 this week</div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Renewals</span>
            <ArrowsClockwise className="stat-icon" size={20} />
          </div>
          <div className="stat-value">34</div>
          <div className="stat-description">12 pending</div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Success Rate</span>
            <ChartLine className="stat-icon" size={20} />
          </div>
          <div className="stat-value">96.2%</div>
          <div className="stat-description">3 failed requests</div>
        </div>
      </div>

      {/* SCEP CONFIGURATION */}
      <div className="config-section">
        <div className="config-header">
          <span className="config-title">SCEP Configuration</span>
          <button className="btn btn-primary">
            <FloppyDisk size={16} />
            Save Changes
          </button>
        </div>
        <div className="config-content">
          <div className="config-row">
            <div className="config-group">
              <label className="config-label">SCEP URL</label>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input type="text" className="config-input" value="https://scep.ucm.local/scep" readOnly style={{ flex: 1 }} />
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
              <label className="config-label">Challenge Password Validity</label>
              <div className="config-input-unit">
                <input type="number" className="config-input" defaultValue="24" />
                <span className="config-unit">hours</span>
              </div>
            </div>
            <div className="config-group">
              <label className="config-label">Auto-Approve Renewals</label>
              <input type="checkbox" className="config-checkbox" defaultChecked />
            </div>
          </div>
          <div className="config-info" style={{ marginTop: 'var(--spacing-lg)', padding: 'var(--spacing-md)', background: 'var(--bg-tertiary)', border: '1px solid var(--border-primary)', borderRadius: 'var(--radius)', fontSize: '12px', color: 'var(--text-secondary)' }}>
            <i className="ph ph-info" style={{ color: 'var(--status-info)' }}></i>
            SCEP (Simple Certificate Enrollment Protocol) enables automated certificate enrollment for mobile devices and network equipment. Configure challenge passwords for device enrollment.
          </div>
        </div>
      </div>

      {/* ENROLLMENTS TABLE */}
      <div className="table-section">
        <div className="section-header">
          <span className="section-title">Device Enrollments</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn">
              <Funnel size={16} />
              Filter
            </button>
            <button className="btn">
              <DownloadSimple size={16} />
              Export
            </button>
          </div>
        </div>
        <div className="section-content">
          <table>
            <thead>
              <tr>
                <th>Device Name</th>
                <th>Serial Number</th>
                <th>Platform</th>
                <th>Status</th>
                <th>Enrolled</th>
                <th>Expires</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>iPhone 15 Pro - John</td>
                <td className="mono">A1B2C3D4E5F6</td>
                <td>iOS 17.3</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-03-10</td>
                <td>2025-03-10</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>MacBook Pro M3 - Sarah</td>
                <td className="mono">F6E5D4C3B2A1</td>
                <td>macOS 14.3</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-03-08</td>
                <td>2025-03-08</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>Samsung Galaxy S24 - Mike</td>
                <td className="mono">123456789ABC</td>
                <td>Android 14</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-03-05</td>
                <td>2025-03-05</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>iPad Air - Design Team</td>
                <td className="mono">ABC987654321</td>
                <td>iPadOS 17.3</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-03-01</td>
                <td>2025-03-01</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>Cisco Router 2900</td>
                <td className="mono">CISCO2900001</td>
                <td>IOS-XE 17.9</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-02-28</td>
                <td>2025-02-28</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>Surface Laptop 5 - Alex</td>
                <td className="mono">SURF12345678</td>
                <td>Windows 11</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-02-25</td>
                <td>2025-02-25</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>iPhone 14 - Emily</td>
                <td className="mono">EM14IPHONE01</td>
                <td>iOS 17.2</td>
                <td><span className="badge badge-warning">Expiring Soon</span></td>
                <td>2023-03-20</td>
                <td>2024-03-20</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>HP ProBook - IT Dept</td>
                <td className="mono">HPPROB456789</td>
                <td>Windows 11</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-02-20</td>
                <td>2025-02-20</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>Dell OptiPlex - Reception</td>
                <td className="mono">DELL789ABC12</td>
                <td>Windows 11</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-02-15</td>
                <td>2025-02-15</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>Meraki MX75</td>
                <td className="mono">MERAKIMX7501</td>
                <td>Meraki OS</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-02-10</td>
                <td>2025-02-10</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>Pixel 8 Pro - Dev Team</td>
                <td className="mono">PIXEL8PRO99</td>
                <td>Android 14</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-02-05</td>
                <td>2025-02-05</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td>Aruba AP-515</td>
                <td className="mono">ARUBA515AP01</td>
                <td>ArubaOS</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-01-28</td>
                <td>2025-01-28</td>
                <td>
                  <button className="btn">
                    <ArrowsClockwise size={16} />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* CHALLENGES SECTION */}
      <div className="table-section">
        <div className="section-header">
          <span className="section-title">Challenge Passwords</span>
          <button className="btn btn-primary">
            <Key size={16} />
            Generate New
          </button>
        </div>
        <div className="section-content">
          <table>
            <thead>
              <tr>
                <th>Challenge</th>
                <th>Device Name</th>
                <th>Status</th>
                <th>Created</th>
                <th>Expires</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="mono">CH-A1B2C3D4</td>
                <td>iPhone 15 Pro - Marketing</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-03-17 10:30</td>
                <td>2024-03-18 10:30</td>
                <td>
                  <button className="btn">
                    <Copy size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td className="mono">CH-E5F6G7H8</td>
                <td>MacBook Air - Finance</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-03-17 09:15</td>
                <td>2024-03-18 09:15</td>
                <td>
                  <button className="btn">
                    <Copy size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td className="mono">CH-I9J0K1L2</td>
                <td>Samsung Tab - Sales</td>
                <td><span className="badge badge-success">Active</span></td>
                <td>2024-03-17 08:45</td>
                <td>2024-03-18 08:45</td>
                <td>
                  <button className="btn">
                    <Copy size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td className="mono">CH-M3N4O5P6</td>
                <td>Cisco Switch 3750</td>
                <td><span className="badge badge-warning">Expiring Soon</span></td>
                <td>2024-03-16 14:20</td>
                <td>2024-03-17 14:20</td>
                <td>
                  <button className="btn">
                    <Copy size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td className="mono">CH-Q7R8S9T0</td>
                <td>iPad Pro - Design</td>
                <td><span className="badge badge-info">Used</span></td>
                <td>2024-03-16 11:00</td>
                <td>2024-03-17 11:00</td>
                <td>
                  <button className="btn">
                    <Copy size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td className="mono">CH-U1V2W3X4</td>
                <td>Dell Latitude - HR</td>
                <td><span className="badge badge-info">Used</span></td>
                <td>2024-03-16 10:30</td>
                <td>2024-03-17 10:30</td>
                <td>
                  <button className="btn">
                    <Copy size={16} />
                  </button>
                </td>
              </tr>
              <tr>
                <td className="mono">CH-Y5Z6A7B8</td>
                <td>Aruba Controller</td>
                <td><span className="badge badge-error">Expired</span></td>
                <td>2024-03-15 16:00</td>
                <td>2024-03-16 16:00</td>
                <td>
                  <button className="btn">
                    <Copy size={16} />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default SCEPPage;
