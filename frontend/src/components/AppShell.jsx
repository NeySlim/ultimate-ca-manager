import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { MagnifyingGlass, Lock, User, Gear, Question, Plus, CaretDown } from '@phosphor-icons/react'
import './AppShell.css'

export default function AppShell({ children }) {
  const [searchOpen, setSearchOpen] = useState(false)
  const [showMoreMenu, setShowMoreMenu] = useState(false)
  const [showNewMenu, setShowNewMenu] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', path: '/dashboard' },
    { id: 'cas', label: 'CAs', path: '/cas' },
    { id: 'certificates', label: 'Certificates', path: '/certificates' },
    { id: 'csrs', label: 'CSRs', path: '/csrs' },
    { id: 'more', label: 'More', path: null, dropdown: true },
  ]
  
  const activeTab = tabs.find(t => location.pathname.startsWith(t.path))?.id || 'dashboard'
  
  return (
    <div className="app-shell">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <div className="logo">
            <Lock size={24} weight="duotone" />
            <span>UCM</span>
          </div>
        </div>
        
        <div className="header-right">
          <button className="icon-btn" title="Account" onClick={() => navigate('/account')}>
            <User size={20} />
          </button>
          <button className="icon-btn" title="Settings" onClick={() => navigate('/settings')}>
            <Gear size={20} />
          </button>
          <button className="icon-btn" title="Help">
            <Question size={20} />
          </button>
        </div>
      </header>
      
      {/* Navigation */}
      <nav className="nav">
        <div className="nav-left">
          <button 
            className="search-btn"
            onClick={() => alert('⌘K Command Palette coming in Phase 4!')}
          >
            <MagnifyingGlass size={16} />
            <span>Search...</span>
            <kbd>⌘K</kbd>
          </button>
          
          <div className="tabs">
            {tabs.map(tab => (
              <button
                key={tab.id}
                className={`tab ${activeTab === tab.id ? 'active' : ''} ${tab.dropdown ? 'dropdown-trigger' : ''}`}
                onClick={() => {
                  if (tab.dropdown) {
                    setShowMoreMenu(!showMoreMenu)
                  } else if (tab.path) {
                    navigate(tab.path)
                  }
                }}
              >
                {tab.label}
                {tab.dropdown && <CaretDown size={14} />}
              </button>
            ))}
            
            {/* More Dropdown Menu */}
            {showMoreMenu && (
              <div className="dropdown-menu more-menu">
                <button className="dropdown-item" onClick={() => { navigate('/settings'); setShowMoreMenu(false); }}>
                  <Gear size={16} />
                  <span>Settings</span>
                </button>
                <button className="dropdown-item" onClick={() => { navigate('/users'); setShowMoreMenu(false); }}>
                  <User size={16} />
                  <span>Users</span>
                </button>
                <div className="dropdown-divider"></div>
                <button className="dropdown-item" onClick={() => { navigate('/account'); setShowMoreMenu(false); }}>
                  <User size={16} />
                  <span>Account</span>
                </button>
              </div>
            )}
          </div>
        </div>
        
        <div className="nav-right">
          <div className="new-btn-container">
            <button className="new-btn" onClick={() => setShowNewMenu(!showNewMenu)}>
              <Plus size={16} weight="bold" />
              <span>New</span>
              <CaretDown size={14} />
            </button>
            
            {/* New Dropdown Menu */}
            {showNewMenu && (
              <div className="dropdown-menu new-menu">
                <button className="dropdown-item" onClick={() => { navigate('/cas'); setShowNewMenu(false); }}>
                  <span>Create CA</span>
                </button>
                <button className="dropdown-item" onClick={() => { navigate('/certificates'); setShowNewMenu(false); }}>
                  <span>Issue Certificate</span>
                </button>
                <button className="dropdown-item" onClick={() => { navigate('/csrs'); setShowNewMenu(false); }}>
                  <span>Upload CSR</span>
                </button>
                <div className="dropdown-divider"></div>
                <button className="dropdown-item" onClick={() => { navigate('/users'); setShowNewMenu(false); }}>
                  <span>Create User</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>
      
      {/* Content */}
      <main className="content">
        {children}
      </main>
    </div>
  )
}
