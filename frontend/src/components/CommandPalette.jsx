import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { MagnifyingGlass, ArrowRight, Certificate, ShieldCheck, FileText, Gear, Users, Key } from '@phosphor-icons/react'
import './CommandPalette.css'

const COMMANDS = [
  { id: 'dashboard', label: 'Dashboard', icon: ArrowRight, path: '/dashboard', keywords: 'home overview' },
  { id: 'cas', label: 'Certificate Authorities', icon: ShieldCheck, path: '/cas', keywords: 'ca root intermediate' },
  { id: 'certificates', label: 'Certificates', icon: Certificate, path: '/certificates', keywords: 'cert ssl tls' },
  { id: 'csrs', label: 'Certificate Signing Requests', icon: FileText, path: '/csrs', keywords: 'csr sign' },
  { id: 'acme', label: 'ACME Automation', icon: Key, path: '/acme', keywords: 'letsencrypt automation' },
  { id: 'crl', label: 'CRL/OCSP', icon: FileText, path: '/crl', keywords: 'revocation revoke' },
  { id: 'scep', label: 'SCEP Enrollment', icon: Key, path: '/scep', keywords: 'device mobile' },
  { id: 'templates', label: 'Certificate Templates', icon: FileText, path: '/templates', keywords: 'template preset' },
  { id: 'truststore', label: 'Trust Store', icon: ShieldCheck, path: '/truststore', keywords: 'trusted root' },
  { id: 'settings', label: 'Settings', icon: Gear, path: '/settings', keywords: 'config configuration' },
  { id: 'users', label: 'Users', icon: Users, path: '/users', keywords: 'user rbac permissions' },
  { id: 'account', label: 'Account', icon: Users, path: '/account', keywords: 'profile password' },
]

export default function CommandPalette({ isOpen, onClose }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef(null)
  
  const filtered = COMMANDS.filter(cmd => 
    cmd.label.toLowerCase().includes(query.toLowerCase()) ||
    cmd.keywords.includes(query.toLowerCase())
  )
  
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])
  
  useEffect(() => {
    function handleKeyDown(e) {
      if (!isOpen) return
      
      if (e.key === 'Escape') {
        onClose()
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelected(prev => (prev + 1) % filtered.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelected(prev => (prev - 1 + filtered.length) % filtered.length)
      } else if (e.key === 'Enter' && filtered[selected]) {
        e.preventDefault()
        navigate(filtered[selected].path)
        onClose()
      }
    }
    
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, selected, filtered, navigate, onClose])
  
  if (!isOpen) return null
  
  return (
    <div className="command-palette-overlay" onClick={onClose}>
      <div className="command-palette" onClick={e => e.stopPropagation()}>
        <div className="command-search">
          <MagnifyingGlass size={20} />
          <input 
            ref={inputRef}
            type="text" 
            placeholder="Search commands..."
            value={query}
            onChange={e => { setQuery(e.target.value); setSelected(0) }}
          />
          <kbd>ESC</kbd>
        </div>
        
        <div className="command-results">
          {filtered.length === 0 ? (
            <div className="no-results">No results found</div>
          ) : (
            filtered.map((cmd, i) => (
              <button
                key={cmd.id}
                className={`command-item ${i === selected ? 'selected' : ''}`}
                onClick={() => { navigate(cmd.path); onClose() }}
                onMouseEnter={() => setSelected(i)}
              >
                <cmd.icon size={18} />
                <span>{cmd.label}</span>
                <ArrowRight size={16} className="arrow" />
              </button>
            ))
          )}
        </div>
        
        <div className="command-footer">
          <div className="hint">
            <kbd>↑</kbd><kbd>↓</kbd> Navigate
          </div>
          <div className="hint">
            <kbd>↵</kbd> Select
          </div>
          <div className="hint">
            <kbd>ESC</kbd> Close
          </div>
        </div>
      </div>
    </div>
  )
}
