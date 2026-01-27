import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { MagnifyingGlass, Gear, CaretDown, Bell, SignOut, Plus, Certificate, ShieldCheck, FileText, Key, Users as UsersIcon, UserCircle } from '@phosphor-icons/react'
import './AppShell.css'

export default function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [showMoreMenu, setShowMoreMenu] = useState(false)
  const [showNewMenu, setShowNewMenu] = useState(false)
  
  function isActive(path) {
    return location.pathname === path
  }
  
  async function handleLogout() {
    try {
      await fetch('/api/v2/auth/logout', { method: 'POST', credentials: 'include' })
    } catch (err) {
      console.error(err)
    }
    navigate('/login')
  }
  
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-left">
          <div className="logo">
            <ShieldCheck size={28} weight="duotone" />
            <span>UCM</span>
          </div>
          
          <button className="search-button">
            <MagnifyingGlass size={18} />
            <span>Search...</span>
            <kbd>⌘K</kbd>
          </button>
        </div>
        
        <div className="header-right">
          <button className="btn-icon" onClick={() => setShowNewMenu(!showNewMenu)}>
            <Plus size={20} weight="bold" />
            <span>New</span>
            <CaretDown size={14} />
          </button>
          
          {showNewMenu && (
            <div className="dropdown-menu new-menu">
              <button className="dropdown-item" onClick={() => navigate('/cas')}>
                <ShieldCheck size={18} />
                <span>Create CA</span>
              </button>
              <button className="dropdown-item" onClick={() => navigate('/certificates')}>
                <Certificate size={18} />
                <span>Issue Certificate</span>
              </button>
              <button className="dropdown-item" onClick={() => navigate('/csrs')}>
                <FileText size={18} />
                <span>Upload CSR</span>
              </button>
              <div className="dropdown-divider"></div>
              <button className="dropdown-item" onClick={() => navigate('/templates')}>
                <FileText size={18} />
                <span>New Template</span>
              </button>
            </div>
          )}
          
          <button className="btn-icon">
            <Bell size={20} />
          </button>
          
          <button className="btn-icon" onClick={() => setShowMoreMenu(!showMoreMenu)}>
            <Gear size={20} />
            <span>More</span>
            <CaretDown size={14} />
          </button>
          
          {showMoreMenu && (
            <div className="dropdown-menu more-menu">
              <button className="dropdown-item" onClick={() => navigate('/settings')}>
                <Gear size={18} />
                <span>Settings</span>
              </button>
              <button className="dropdown-item" onClick={() => navigate('/users')}>
                <UsersIcon size={18} />
                <span>Users</span>
              </button>
              <button className="dropdown-item" onClick={() => navigate('/account')}>
                <UserCircle size={18} />
                <span>Account</span>
              </button>
              <div className="dropdown-divider"></div>
              <button className="dropdown-item danger" onClick={handleLogout}>
                <SignOut size={18} />
                <span>Logout</span>
              </button>
            </div>
          )}
        </div>
      </header>
      
      <nav className="tab-nav">
        <button className={isActive('/dashboard') ? 'active' : ''} onClick={() => navigate('/dashboard')}>Dashboard</button>
        <button className={isActive('/cas') ? 'active' : ''} onClick={() => navigate('/cas')}>CAs</button>
        <button className={isActive('/certificates') ? 'active' : ''} onClick={() => navigate('/certificates')}>Certificates</button>
        <button className={isActive('/csrs') ? 'active' : ''} onClick={() => navigate('/csrs')}>CSRs</button>
        <button className={isActive('/acme') ? 'active' : ''} onClick={() => navigate('/acme')}>ACME</button>
        <button className={isActive('/crl') ? 'active' : ''} onClick={() => navigate('/crl')}>CRL/OCSP</button>
        <button className={isActive('/scep') ? 'active' : ''} onClick={() => navigate('/scep')}>SCEP</button>
        <button className={isActive('/templates') ? 'active' : ''} onClick={() => navigate('/templates')}>Templates</button>
        <button className={isActive('/truststore') ? 'active' : ''} onClick={() => navigate('/truststore')}>TrustStore</button>
      </nav>
      
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  )
}
