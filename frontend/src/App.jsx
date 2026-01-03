import React, { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [systemInfo, setSystemInfo] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/system/info')
      .then(res => res.json())
      .then(data => {
        setSystemInfo(data)
        setLoading(false)
      })
      .catch(err => {
        console.error('Error fetching system info:', err)
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="app">
        <div className="container">
          <h1>Loading...</h1>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="header">
        <h1>🔐 {systemInfo?.app_name || 'Ultimate CA Manager'}</h1>
        <p>Version {systemInfo?.version || '1.0.0'}</p>
      </header>

      <main className="container">
        <div className="card">
          <h2>🚧 Under Construction</h2>
          <p>The Ultimate CA Manager frontend is currently being built.</p>
          
          <div className="status">
            <h3>System Status</h3>
            <ul>
              <li>✅ Backend API: Running</li>
              <li>✅ HTTPS: Enabled</li>
              <li>{systemInfo?.scep_enabled ? '✅' : '⏸️'} SCEP: {systemInfo?.scep_enabled ? 'Enabled' : 'Disabled'}</li>
            </ul>
          </div>

          <div className="features">
            <h3>Coming Soon</h3>
            <ul>
              <li>🔑 Certificate Authority Management</li>
              <li>📜 Certificate Operations</li>
              <li>📋 CRL Management</li>
              <li>🔄 SCEP Server Configuration</li>
              <li>🔗 OPNsense Import Wizard</li>
              <li>👥 User Management</li>
              <li>⚙️ System Configuration</li>
              <li>🎨 Theme Customization</li>
            </ul>
          </div>

          <div className="login-hint">
            <h3>Default Credentials</h3>
            <code>Username: admin</code>
            <br />
            <code>Password: changeme123</code>
            <p className="warning">⚠️ Change this password immediately!</p>
          </div>
        </div>
      </main>

      <footer className="footer">
        <p>Ultimate CA Manager - A complete Certificate Authority solution</p>
        <p>BSD 3-Clause License</p>
      </footer>
    </div>
  )
}

export default App
