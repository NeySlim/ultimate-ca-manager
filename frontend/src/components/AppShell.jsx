import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { MagnifyingGlass, Lock, User, Gear, Question, Plus, CaretDown } from '@phosphor-icons/react'
import './AppShell.css'

export default function AppShell({ children }) {
  const [searchOpen, setSearchOpen] = useState(false)
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
          <button className="icon-btn" title="Account">
            <User size={20} />
          </button>
          <button className="icon-btn" title="Settings">
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
            onClick={() => setSearchOpen(!searchOpen)}
          >
            <MagnifyingGlass size={16} />
            <span>Search...</span>
            <kbd>⌘K</kbd>
          </button>
          
          <div className="tabs">
            {tabs.map(tab => (
              <button
                key={tab.id}
                className={`tab ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => tab.path && navigate(tab.path)}
              >
                {tab.label}
                {tab.dropdown && <CaretDown size={14} />}
              </button>
            ))}
          </div>
        </div>
        
        <div className="nav-right">
          <button className="new-btn">
            <Plus size={16} weight="bold" />
            <span>New</span>
            <CaretDown size={14} />
          </button>
        </div>
      </nav>
      
      {/* Content */}
      <main className="content">
        {children}
      </main>
    </div>
  )
}
