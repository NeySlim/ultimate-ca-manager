/**
 * AppShell Component - Main application layout with mobile support
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, Link, useNavigate } from 'react-router-dom'
import { 
  List, X, MagnifyingGlass,
  House, Certificate, ShieldCheck, FileText, List as ListIcon, User, Key, Gear,
  UploadSimple, ClockCounterClockwise, Robot, FileX, Vault, Shield, Lock,
  UserCircle, Palette, Question, Detective, SignOut, Globe
} from '@phosphor-icons/react'
import { Sidebar } from './Sidebar'
import { CommandPalette, useKeyboardShortcuts } from './CommandPalette'
import { WebSocketIndicator } from './WebSocketIndicator'
import { HelpModal } from './ui/HelpModal'
import LanguageSelector from './ui/LanguageSelector'
import { cn } from '../lib/utils'
import { Logo } from './Logo'
import { useTheme } from '../contexts/ThemeContext'
import { useNotification } from '../contexts/NotificationContext'
import { useAuth } from '../contexts/AuthContext'
import { certificatesService } from '../services'

// Mobile navigation items (grid menu) - labels are i18n keys
const mobileNavItems = [
  { id: '', icon: House, labelKey: 'common.dashboard', path: '/' },
  { id: 'certificates', icon: Certificate, labelKey: 'common.certificates', path: '/certificates' },
  { id: 'cas', icon: ShieldCheck, labelKey: 'common.cas', path: '/cas' },
  { id: 'csrs', icon: FileText, labelKey: 'common.csrs', path: '/csrs' },
  { id: 'templates', icon: ListIcon, labelKey: 'common.templates', path: '/templates' },
  { id: 'users', icon: User, labelKey: 'common.users', path: '/users' },
  { id: 'acme', icon: Key, labelKey: 'common.acme', path: '/acme' },
  { id: 'scep', icon: Robot, labelKey: 'common.scep', path: '/scep-config' },
  { id: 'crl-ocsp', icon: FileX, labelKey: 'common.crlOcsp', path: '/crl-ocsp' },
  { id: 'truststore', icon: Vault, labelKey: 'common.trustStore', path: '/truststore' },
  { id: 'import', icon: UploadSimple, labelKey: 'common.importExport', path: '/import' },
  { id: 'audit', icon: ClockCounterClockwise, labelKey: 'common.audit', path: '/audit' },
  { id: 'settings', icon: Gear, labelKey: 'common.settings', path: '/settings' },
]

// Advanced features (formerly Pro) - labels are i18n keys
const advancedNavItems = [
  { id: 'security', icon: Detective, labelKey: 'common.security', path: '/security' },
  { id: 'rbac', icon: Shield, labelKey: 'common.rbac', path: '/rbac' },
  { id: 'hsm', icon: Lock, labelKey: 'common.hsm', path: '/hsm' },
]

export function AppShell() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const { logout } = useAuth()
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [helpModalOpen, setHelpModalOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [isLargeScreen, setIsLargeScreen] = useState(false)
  const [isDesktopFrame, setIsDesktopFrame] = useState(false)
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
    const checkViewport = () => {
      setIsMobile(window.innerWidth < 768)
      setIsLargeScreen(window.innerWidth >= 1280)
      setIsDesktopFrame(window.innerWidth >= 900)
    }
    checkViewport()
    window.addEventListener('resize', checkViewport)
    return () => window.removeEventListener('resize', checkViewport)
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
            showWarning(t('notifications.certificatesExpiredAndExpiring', { expired, expiring }))
          } else if (expired > 0) {
            showWarning(t('notifications.certificatesExpired', { count: expired }))
          } else {
            showWarning(t('notifications.certificatesExpiringSoon', { count: expiring }))
          }
        }
      } catch {
        // Ignore errors
      }
    }
    
    // Delay check to let the app settle
    const timer = setTimeout(checkExpiringCerts, 2000)
    return () => clearTimeout(timer)
  }, [showWarning, t])

  // Close mobile menu on navigation
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onCommandPalette: () => setCommandPaletteOpen(true)
  })

  // All nav items (including Pro if available)
  const allNavItems = [...mobileNavItems, ...advancedNavItems]

  return (
    <div className={cn(
      "flex h-full w-full overflow-hidden justify-center items-center",
      isDesktopFrame ? "bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900" : "bg-bg-primary"
    )}>
      {/* App container - frame effect on desktop (>= 900px) */}
      <div className={cn(
        "flex flex-col w-full overflow-hidden bg-bg-primary relative",
        isDesktopFrame
          ? "max-w-[min(calc(100%-48px),1900px)] h-[calc(100%-24px)] rounded-xl shadow-2xl border border-white/10"
          : "h-full"
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
            {activePage === '' ? t('common.dashboard') : 
             activePage === 'import' ? t('common.importExport') :
             activePage === 'scep-config' ? t('common.scep') :
             activePage === 'crl-ocsp' ? t('common.crlOcsp') :
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
            <div className="px-2 py-0.5 text-3xs text-text-tertiary uppercase tracking-wider">{t('settings.color')}</div>
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
            <div className="px-2 py-0.5 text-3xs text-text-tertiary uppercase tracking-wider">{t('settings.tabs.appearance')}</div>
            {[
              { id: 'system', labelKey: 'settings.followSystem' },
              { id: 'dark', labelKey: 'settings.dark' },
              { id: 'light', labelKey: 'settings.light' }
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
                {t(opt.labelKey)}
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
                        {t(item.labelKey)}
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
              
              {/* Footer: Language selector + Logout */}
              <div className="mt-3 pt-3 border-t border-border flex items-center justify-between">
                <LanguageSelector className="flex-1" />
                <button
                  onClick={() => { setMobileMenuOpen(false); logout(); }}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-status-danger hover:bg-status-danger/10 transition-colors"
                >
                  <SignOut size={18} />
                  <span className="text-sm font-medium">{t('auth.logout')}</span>
                </button>
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
