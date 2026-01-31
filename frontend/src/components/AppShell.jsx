/**
 * AppShell Component - Main application layout with mobile support
 */
import { useState, useEffect } from 'react'
import { Outlet, useLocation, Link } from 'react-router-dom'
import { 
  List, X, MagnifyingGlass,
  House, Certificate, ShieldCheck, FileText, List as ListIcon, User, Key, Gear,
  UploadSimple, ClockCounterClockwise, Robot, FileX, Vault, Shield, Lock
} from '@phosphor-icons/react'
import { Sidebar } from './Sidebar'
import { CommandPalette, useKeyboardShortcuts } from './CommandPalette'
import { cn } from '../lib/utils'
import { Logo } from './Logo'

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
  { id: 'rbac', icon: Shield, label: 'RBAC', path: '/rbac', pro: true },
  { id: 'hsm', icon: Lock, label: 'HSM', path: '/hsm', pro: true },
]

export function AppShell() {
  const location = useLocation()
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [isPro, setIsPro] = useState(false)
  
  // Extract current page from pathname (empty string for dashboard)
  const activePage = location.pathname.split('/')[1] || ''

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
    <div className="flex h-full w-full bg-bg-primary overflow-hidden">
      {/* Mobile Header - Search left, Hamburger right */}
      {isMobile && (
        <div className="fixed top-0 left-0 right-0 h-12 bg-bg-secondary border-b border-border flex items-center px-3 z-40">
          {/* Search button - LEFT */}
          <button
            onClick={() => setCommandPaletteOpen(true)}
            className="w-9 h-9 flex items-center justify-center rounded-md text-text-secondary hover:bg-bg-tertiary shrink-0"
          >
            <MagnifyingGlass size={20} />
          </button>
          
          {/* Logo - LEFT CENTER */}
          <div className="shrink-0 opacity-60 scale-[0.5] origin-left -ml-1">
            <Logo variant="compact" size="sm" />
          </div>
          
          {/* Spacer */}
          <div className="flex-1" />
          
          {/* Page title - RIGHT (near hamburger) */}
          <span className="text-sm font-medium text-text-primary mr-2">
            {activePage ? activePage.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : 'Dashboard'}
          </span>
          
          {/* Hamburger menu - RIGHT */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="w-9 h-9 flex items-center justify-center rounded-md text-text-secondary hover:bg-bg-tertiary shrink-0"
          >
            {mobileMenuOpen ? <X size={20} /> : <List size={20} />}
          </button>
        </div>
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
          <div className="fixed top-12 right-0 left-0 z-50 p-3 animate-in slide-in-from-top-2 duration-200">
            <div className="bg-bg-secondary border border-border rounded-xl shadow-2xl p-4 max-h-[70vh] overflow-auto">
              {/* Navigation Grid */}
              <div className="grid grid-cols-4 gap-2">
                {allNavItems.map((item) => {
                  const Icon = item.icon
                  const isActive = activePage === item.id
                  
                  return (
                    <Link
                      key={item.id}
                      to={item.path}
                      className={cn(
                        "flex flex-col items-center justify-center gap-1.5 p-3 rounded-lg transition-all",
                        "hover:bg-bg-tertiary active:scale-95",
                        isActive 
                          ? "bg-accent-primary/15 text-accent-primary" 
                          : "text-text-secondary hover:text-text-primary"
                      )}
                    >
                      <Icon size={24} weight={isActive ? "fill" : "regular"} />
                      <span className="text-[10px] font-medium text-center leading-tight">
                        {item.label}
                      </span>
                      {item.pro && (
                        <span className="text-[8px] px-1 py-0.5 bg-amber-500/20 text-amber-500 rounded">
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

      {/* Desktop Sidebar - Hidden on mobile */}
      {!isMobile && (
        <div className="flex-shrink-0">
          <Sidebar activePage={activePage} />
        </div>
      )}

      {/* Main Content */}
      <div className={cn(
        "flex-1 flex min-h-0 min-w-0 overflow-hidden",
        isMobile && "pt-12" // Account for mobile header
      )}>
        <Outlet />
      </div>

      {/* Command Palette */}
      <CommandPalette 
        open={commandPaletteOpen} 
        onOpenChange={setCommandPaletteOpen}
        isPro={isPro}
      />
    </div>
  )
}
