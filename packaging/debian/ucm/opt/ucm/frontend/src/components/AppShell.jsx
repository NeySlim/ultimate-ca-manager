/**
 * AppShell Component - Main application layout with mobile support
 */
import { useState, useEffect } from 'react'
import { Outlet, useLocation, Link, useNavigate } from 'react-router-dom'
import { 
  List, X, MagnifyingGlass,
  House, Certificate, ShieldCheck, FileText, List as ListIcon, User, Key, Gear,
  UploadSimple, ClockCounterClockwise, Robot, FileX, Vault, Shield, Lock,
  UserCircle, Palette, Question, Detective
} from '@phosphor-icons/react'
import { Sidebar } from './Sidebar'
import { CommandPalette, useKeyboardShortcuts } from './CommandPalette'
import { WebSocketIndicator } from './WebSocketIndicator'
import { HelpModal } from './ui/HelpModal'
import { cn } from '../lib/utils'
import { Logo } from './Logo'
import { useTheme } from '../contexts/ThemeContext'
import { useNotification } from '../contexts/NotificationContext'
import { certificatesService } from '../services'

// Mobile navigation items (grid menu)
const mobileNavItems = [
  { id: '', icon: House, label: 'Dashboard', path: '/' },
  { id: 'certificates', icon: Certificate, label: 'Certificates', path: '/certificates' },
  { id: 'cas', icon: ShieldCheck, label: 'CAs', path: '/cas' },
  { id: 'csrs', icon: FileText, label: 'CSRs', path: '/csrs' },
  { id: 'templates', icon: ListIcon, label: 'Templates', path: '/templates' },
  { id: 'users', icon: User, label: 'Users', path: '/users' },
  { id: 'acme', icon: Key, label: 'ACME', path: '/acme' },
  { id: 'scep', icon: Robot, label: 'SCEP', path: '/scep-config' },
  { id: 'crl-ocsp', icon: FileX, label: 'CRL/OCSP', path: '/crl-ocsp' },
  { id: 'truststore', icon: Vault, label: 'Trust Store', path: '/truststore' },
  { id: 'import', icon: UploadSimple, label: 'Import', path: '/import' },
  { id: 'audit', icon: ClockCounterClockwise, label: 'Audit', path: '/audit' },
  { id: 'settings', icon: Gear, label: 'Settings', path: '/settings' },
]

// Pro items (added dynamically)
const proNavItems = [
  { id: 'security', icon: Detective, label: 'Security', path: '/security', pro: true },
  { id: 'rbac', icon: Shield, label: 'RBAC', path: '/rbac', pro: true },
  { id: 'hsm', icon: Lock, label: 'HSM', path: '/hsm', pro: true },
]

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [helpModalOpen, setHelpModalOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [isPro, setIsPro] = useState(false)
  const { showWarning } = useNotification()
  
  // Extract current page from pathname (empty string for dashboard)
  const activePage = location.pathname.split('/')[1] || ''
  
  // Map URL paths to helpContent keys
  const helpPageKeyMap = {
    '': 'dashboard',
    'scep-config': 'scep',
    'import': 'importExport',
    'audit': 'auditLogs',
    'crl-ocsp': 'crlocsp'
  }
  const helpPageKey = helpPageKeyMap[activePage] || activePage
  
  // Pages that have contextual help
  const pagesWithHelp = [
    // Core pages
    'certificates', 'cas', 'csrs', 'users', 'templates', 
    'acme', 'scep-config', 'settings', 'truststore', 'crl-ocsp', 
    'import', 'tools', 'audit', 'account',
    // Pro pages
    'rbac', 'hsm', 'security'
  ]
  const hasHelp = pagesWithHelp.includes(activePage) || activePage === ''

  // Check for mobile viewport
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Check for Pro module
  useEffect(() => {
    import('../pro')
      .then(() => setIsPro(true))
      .catch(() => setIsPro(false))
  }, [])
  
  // Check for expiring certificates on mount (once per session)
  useEffect(() => {
    const checkExpiringCerts = async () => {
      // Check if we already showed the alert this session
      const alreadyShown = sessionStorage.getItem('ucm-expiring-alert-shown')
      if (alreadyShown) return
      
      try {
        const stats = await certificatesService.getStats()
        const expiring = stats?.data?.expiring || 0
        const expired = stats?.data?.expired || 0
        
        if (expiring > 0 || expired > 0) {
          sessionStorage.setItem('ucm-expiring-alert-shown', 'true')
          
          if (expired > 0 && expiring > 0) {
            showWarning(`${expired} certificate${expired > 1 ? 's have' : ' has'} expired and ${expiring} ${expiring > 1 ? 'are' : 'is'} expiring soon`)
          } else if (expired > 0) {
            showWarning(`${expired} certificate${expired > 1 ? 's have' : ' has'} expired`)
          } else {
            showWarning(`${expiring} certificate${expiring > 1 ? 's are' : ' is'} expiring soon`)
          }
        }
      } catch {
        // Ignore errors
      }
    }
    
    // Delay check to let the app settle
    const timer = setTimeout(checkExpiringCerts, 2000)
    return () => clearTimeout(timer)
  }, [showWarning])

  // Close mobile menu on navigation
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onCommandPalette: () => setCommandPaletteOpen(true)
  })

  // All nav items (including Pro if available)
  const allNavItems = isPro ? [...mobileNavItems, ...proNavItems] : mobileNavItems

  return (
    <div className="flex h-full w-full overflow-hidden justify-center items-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Window container with frame effect */}
      <div className={cn(
        "flex flex-col h-full w-full max-w-[1920px] overflow-hidden bg-bg-primary relative",
        // Frame effect on large screens only
        "2xl:h-[calc(100%-24px)] 2xl:my-3 2xl:mx-4 2xl:rounded-xl 2xl:shadow-2xl 2xl:border 2xl:border-white/10"
      )}>
        
      {/* Mobile Header - OUTSIDE the row flex, in a column layout */}
      {isMobile && (
        <div className="shrink-0 h-10 bg-bg-secondary border-b border-border/50 flex items-center px-2 z-40 navbar-mobile-accent">
          {/* Logo - LEFT */}
          <div className="shrink-0 opacity-80 scale-[0.7] origin-left">
            <Logo variant="compact" size="sm" />
          </div>
          
          {/* Spacer */}
          <div className="flex-1" />
          
          {/* Page title - custom labels for some pages */}
          <span className="text-xs font-medium text-text-primary truncate max-w-[140px]">
            {activePage === '' ? 'Dashboard' : 
             activePage === 'import' ? 'Import / Export' :
             activePage === 'scep-config' ? 'SCEP Protocol' :
             activePage === 'crl-ocsp' ? 'CRL & OCSP' :
             activePage.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
          </span>
          
          {/* Help button - only if page has help */}
          {hasHelp && (
            <button
              onClick={() => setHelpModalOpen(true)}
              className="w-7 h-7 flex items-center justify-center rounded-md text-text-secondary hover:bg-bg-tertiary"
            >
              <Question size={16} />
            </button>
          )}
          
          {/* Search button (global) */}
          <button
            onClick={() => setCommandPaletteOpen(true)}
            className="w-7 h-7 flex items-center justify-center rounded-md text-text-secondary hover:bg-bg-tertiary"
          >
            <MagnifyingGlass size={16} />
          </button>
          
          {/* Theme button */}
          <button
            onClick={() => setThemeMenuOpen(!themeMenuOpen)}
            className="w-7 h-7 flex items-center justify-center rounded-md text-text-secondary hover:bg-bg-tertiary"
          >
            <Palette size={16} />
          </button>
          
          {/* WebSocket indicator */}
          <WebSocketIndicator className="ml-0.5 scale-90" />
          
          {/* Account button */}
          <button
            onClick={() => { setMobileMenuOpen(false); navigate('/account') }}
            className="w-7 h-7 flex items-center justify-center rounded-md text-text-secondary hover:bg-bg-tertiary"
          >
            <UserCircle size={16} />
          </button>
          
          {/* Hamburger menu */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="w-8 h-8 flex items-center justify-center rounded-md text-text-secondary hover:bg-bg-tertiary shrink-0"
          >
            {mobileMenuOpen ? <X size={18} /> : <List size={18} />}
          </button>
        </div>
      )}

      {/* Theme selector popup (mobile) */}
      {isMobile && themeMenuOpen && (
        <>
          <div 
            className="fixed inset-0 z-40"
            onClick={() => setThemeMenuOpen(false)}
          />
          <div className="fixed top-10 right-2 z-50 bg-bg-secondary border border-border rounded-lg shadow-xl p-1.5 min-w-[160px] max-h-[60vh] overflow-auto">
            {/* Color Themes */}
            <div className="px-2 py-0.5 text-3xs text-text-tertiary uppercase tracking-wider">Color</div>
            {themes.map((theme) => (
              <button
                key={theme.id}
                onClick={() => { setThemeFamily(theme.id); setThemeMenuOpen(false) }}
                className={cn(
                  "w-full px-2 py-1.5 text-left text-xs rounded flex items-center gap-2",
                  "hover:bg-bg-tertiary transition-colors",
                  themeFamily === theme.id && "text-accent-primary bg-accent-primary/10"
                )}
              >
                <div 
                  className="w-2.5 h-2.5 rounded-full border border-border"
                  style={{ background: theme.accent }}
                />
                {theme.name}
              </button>
            ))}
            
            {/* Separator */}
            <div className="h-px bg-border my-1.5" />
            
            {/* Mode */}
            <div className="px-2 py-0.5 text-3xs text-text-tertiary uppercase tracking-wider">Appearance</div>
            {[
              { id: 'system', label: 'System' },
              { id: 'dark', label: 'Dark' },
              { id: 'light', label: 'Light' }
            ].map(opt => (
              <button
                key={opt.id}
                onClick={() => { setMode(opt.id); setThemeMenuOpen(false) }}
                className={cn(
                  "w-full px-2 py-1.5 text-left text-xs rounded",
                  "hover:bg-bg-tertiary transition-colors",
                  mode === opt.id && "text-accent-primary bg-accent-primary/10"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </>
      )}

      {/* Mobile Grid Menu Overlay */}
      {isMobile && mobileMenuOpen && (
        <>
          {/* Backdrop */}
          <div 
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
            onClick={() => setMobileMenuOpen(false)}
          />
          
          {/* Grid Menu Panel */}
          <div className="fixed top-10 right-0 left-0 z-50 p-2 animate-in slide-in-from-top-2 duration-200">
            <div className="bg-bg-secondary border border-border rounded-xl shadow-2xl p-3 max-h-[65vh] overflow-auto">
              {/* Navigation Grid - 5 columns on small screens */}
              <div className="grid grid-cols-5 gap-1.5">
                {allNavItems.map((item) => {
                  const Icon = item.icon
                  const isActive = activePage === item.id
                  
                  return (
                    <Link
                      key={item.id}
                      to={item.path}
                      className={cn(
                        "flex flex-col items-center justify-center gap-1 p-2 rounded-lg transition-all",
                        "hover:bg-bg-tertiary active:scale-95",
                        isActive 
                          ? "bg-accent-primary/15 text-accent-primary" 
                          : "text-text-secondary hover:text-text-primary"
                      )}
                    >
                      <Icon size={20} weight={isActive ? "fill" : "regular"} />
                      <span className="text-3xs font-medium text-center leading-tight">
                        {item.label}
                      </span>
                      {item.pro && (
                        <span className="text-3xs px-0.5 py-0.5 status-warning-bg status-warning-text rounded">
                          PRO
                        </span>
                      )}
                    </Link>
                  )
                })}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Content area: Sidebar + Main (flex row) */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Desktop Sidebar - Hidden on mobile */}
        {!isMobile && (
          <div className="flex-shrink-0">
            <Sidebar activePage={activePage} />
          </div>
        )}

        {/* Main Content */}
        <div className="flex-1 flex min-h-0 min-w-0 overflow-hidden">
          <Outlet />
        </div>
      </div>

      {/* Command Palette */}
      <CommandPalette 
        open={commandPaletteOpen} 
        onOpenChange={setCommandPaletteOpen}
        isPro={isPro}
      />
      
      {/* Mobile Help Modal */}
      {isMobile && (
        <HelpModal
          isOpen={helpModalOpen}
          onClose={() => setHelpModalOpen(false)}
          pageKey={helpPageKey}
        />
      )}
    </div>
    </div>
  )
}
