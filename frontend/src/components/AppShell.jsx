/**
 * AppShell Component - Main application layout with mobile support
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, Link, useNavigate } from 'react-router-dom'
import { 
  List, X, MagnifyingGlass,
  House, Certificate, ShieldCheck, FileText, List as ListIcon, User, Key, Gear,
  Lightning, ClockCounterClockwise, Robot, FileX, Vault, Shield, Lock, Wrench,
  UserCircle, Palette, Question, SignOut, Globe, Check, CaretRight
} from '@phosphor-icons/react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Sidebar } from './Sidebar'
import { CommandPalette, useKeyboardShortcuts } from './CommandPalette'
import { WebSocketIndicator } from './WebSocketIndicator'
import { FloatingHelpPanel } from './ui/FloatingHelpPanel'
import { StatusFooter } from './ui/StatusFooter'
import { cn } from '../lib/utils'
import { Logo } from './Logo'
import { useTheme } from '../contexts/ThemeContext'
import { useNotification } from '../contexts/NotificationContext'
import { useAuth } from '../contexts/AuthContext'
import { usePermission } from '../hooks'
import { certificatesService } from '../services'
import { languages } from '../i18n'

// Mobile navigation items — must match desktop sidebar (Sidebar.jsx)
const mobileNavItems = [
  { id: '', icon: House, labelKey: 'common.dashboard', shortKey: 'common.dashboardShort', path: '/' },
  { id: 'certificates', icon: Certificate, labelKey: 'common.certificates', shortKey: 'common.certificatesShort', path: '/certificates' },
  { id: 'cas', icon: ShieldCheck, labelKey: 'common.cas', shortKey: 'common.casShort', path: '/cas' },
  { id: 'csrs', icon: FileText, labelKey: 'common.csrs', shortKey: 'common.csrsShort', path: '/csrs' },
  { id: 'templates', icon: ListIcon, labelKey: 'common.templates', shortKey: 'common.templatesShort', path: '/templates' },
  { id: 'acme', icon: Key, labelKey: 'common.acme', shortKey: 'common.acmeShort', path: '/acme', permission: 'read:acme' },
  { id: 'scep', icon: Robot, labelKey: 'common.scep', shortKey: 'common.scepShort', path: '/scep-config', permission: 'read:scep' },
  { id: 'crl-ocsp', icon: FileX, labelKey: 'common.crlOcsp', shortKey: 'common.crlOcspShort', path: '/crl-ocsp', permission: 'read:crl' },
  { id: 'truststore', icon: Vault, labelKey: 'common.trustStore', shortKey: 'common.trustStoreShort', path: '/truststore', permission: 'read:truststore' },
  { id: 'operations', icon: Lightning, labelKey: 'common.operations', shortKey: 'common.operationsShort', path: '/operations', adminOnly: true },
  { id: 'tools', icon: Wrench, labelKey: 'common.tools', shortKey: 'common.toolsShort', path: '/tools' },
  { id: 'policies', icon: undefined, labelKey: 'common.policies', shortKey: 'common.policiesShort', path: '/policies', permission: 'read:policies' },
  { id: 'approvals', icon: undefined, labelKey: 'common.approvals', shortKey: 'common.approvalsShort', path: '/approvals', permission: 'read:approvals' },
  { id: 'reports', icon: undefined, labelKey: 'common.reports', shortKey: 'common.reportsShort', path: '/reports', permission: 'read:audit' },
  { id: 'users', icon: User, labelKey: 'common.users', shortKey: 'common.usersShort', path: '/users', adminOnly: true },
  { id: 'rbac', icon: Shield, labelKey: 'common.rbac', shortKey: 'common.rbacShort', path: '/rbac', adminOnly: true },
  { id: 'hsm', icon: Lock, labelKey: 'common.hsm', shortKey: 'common.hsmShort', path: '/hsm', permission: 'read:hsm' },
  { id: 'audit', icon: ClockCounterClockwise, labelKey: 'common.audit', shortKey: 'common.auditShort', path: '/audit', permission: 'read:audit' },
  { id: 'settings', icon: Gear, labelKey: 'common.settings', shortKey: 'common.settingsShort', path: '/settings', adminOnly: true },
]

export function AppShell() {
  const { t, i18n } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const { user, logout } = useAuth()
  const { isAdmin, hasPermission } = usePermission()
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [themeMenuOpen, setThemeMenuOpen] = useState(false)
  const [helpModalOpen, setHelpModalOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [isLargeScreen, setIsLargeScreen] = useState(false)
  const [isDesktopFrame, setIsDesktopFrame] = useState(false)
  const { showWarning } = useNotification()
  
  // Extract current page from pathname (empty string for dashboard)
  const rawPage = location.pathname.split('/')[1] || ''
  // Map URL segments to nav item IDs when they differ
  const pageIdMap = { 'scep-config': 'scep' }
  const activePage = pageIdMap[rawPage] || rawPage
  
  // Map URL paths to helpContent keys
  const helpPageKeyMap = {
    '': 'dashboard',
    'audit': 'auditLogs',
    'crl-ocsp': 'crlocsp',
    'users': 'usersGroups',
    'tools': 'certTools'
  }
  const helpPageKey = helpPageKeyMap[activePage] || activePage
  
  // Pages that have contextual help
  const pagesWithHelp = [
    // Core pages
    'certificates', 'cas', 'csrs', 'users', 'templates', 
    'acme', 'scep', 'settings', 'truststore', 'crl-ocsp', 
    'tools', 'audit', 'account', 'operations',
    // Pro pages
    'rbac', 'hsm'
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

  // All nav items for mobile menu — filtered by permission
  const allNavItems = mobileNavItems.filter(item => {
    if (item.adminOnly && !isAdmin()) return false
    if (item.permission && !isAdmin() && !hasPermission(item.permission)) return false
    return true
  })

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
          
          {/* Page title - use nav item labels for consistency */}
          <span className="text-xs font-medium text-text-primary truncate max-w-[140px]">
            {(() => {
              const navItem = mobileNavItems.find(item => item.id === activePage)
              return navItem ? t(navItem.labelKey) : activePage.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
            })()}
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
          
          {/* User dropdown menu */}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button className="w-7 h-7 flex items-center justify-center rounded-md text-text-secondary hover:bg-bg-tertiary">
                <UserCircle size={16} />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content 
                className="min-w-[180px] bg-bg-secondary border border-border rounded-lg shadow-lg p-1 z-[60]"
                sideOffset={5}
                align="end"
                collisionPadding={8}
              >
                {user?.username && (
                  <DropdownMenu.Label className="px-2.5 py-1.5 text-xs text-text-tertiary border-b border-border mb-0.5">
                    {user.username}
                  </DropdownMenu.Label>
                )}
                <DropdownMenu.Item
                  onClick={() => { setMobileMenuOpen(false); navigate('/account') }}
                  className="flex items-center gap-2.5 px-2.5 py-1.5 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary"
                >
                  <UserCircle size={15} />
                  <span>{t('common.account')}</span>
                </DropdownMenu.Item>
                {isAdmin() && (
                <DropdownMenu.Item
                  onClick={() => { setMobileMenuOpen(false); navigate('/settings') }}
                  className="flex items-center gap-2.5 px-2.5 py-1.5 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary"
                >
                  <Gear size={15} />
                  <span>{t('common.settings')}</span>
                </DropdownMenu.Item>
                )}

                <DropdownMenu.Separator className="h-px bg-border my-0.5" />

                {/* Language sub-menu */}
                <DropdownMenu.Sub>
                  <DropdownMenu.SubTrigger className="flex items-center gap-2.5 px-2.5 py-1.5 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary data-[state=open]:bg-bg-tertiary">
                    <Globe size={15} />
                    <span className="flex-1">{languages.find(l => l.code === (i18n.language?.split('-')[0] || 'en'))?.flag} {languages.find(l => l.code === (i18n.language?.split('-')[0] || 'en'))?.name || 'English'}</span>
                    <CaretRight size={12} className="text-text-tertiary" />
                  </DropdownMenu.SubTrigger>
                  <DropdownMenu.Portal>
                    <DropdownMenu.SubContent 
                      className="min-w-[160px] max-h-[50vh] overflow-auto bg-bg-secondary border border-border rounded-lg shadow-lg p-1 z-[60]"
                      sideOffset={4}
                      collisionPadding={8}
                    >
                      {languages.map(lang => (
                        <DropdownMenu.Item
                          key={lang.code}
                          onClick={() => {
                            i18n.changeLanguage(lang.code)
                            try { localStorage.setItem('i18nextLng', lang.code) } catch {}
                          }}
                          className="flex items-center gap-2 px-2.5 py-1.5 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary"
                        >
                          <span>{lang.flag}</span>
                          <span className="flex-1">{lang.name}</span>
                          {(i18n.language?.split('-')[0] || 'en') === lang.code && (
                            <Check size={14} weight="bold" className="text-accent-primary" />
                          )}
                        </DropdownMenu.Item>
                      ))}
                    </DropdownMenu.SubContent>
                  </DropdownMenu.Portal>
                </DropdownMenu.Sub>

                <DropdownMenu.Separator className="h-px bg-border my-0.5" />

                <DropdownMenu.Item
                  onClick={() => { setMobileMenuOpen(false); logout() }}
                  className="flex items-center gap-2.5 px-2.5 py-1.5 text-sm rounded-md cursor-pointer outline-none hover:bg-status-danger/10 text-status-danger"
                >
                  <SignOut size={15} />
                  <span>{t('auth.logout')}</span>
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
          
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
                        {t(item.shortKey)}
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
              
              {/* Footer: Logout only (language is in user dropdown) */}
              <div className="mt-3 pt-3 border-t border-border flex items-center justify-end">
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

        {/* Main Content + Footer (flex column) */}
        <div className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden">
          <div className="flex-1 flex min-h-0 min-w-0 overflow-auto">
            <Outlet />
          </div>

          {/* Status Footer — desktop only, not on dashboard */}
          {!isMobile && activePage !== '' && activePage !== 'dashboard' && <StatusFooter />}
        </div>
      </div>

      {/* Command Palette */}
      <CommandPalette 
        open={commandPaletteOpen} 
        onOpenChange={setCommandPaletteOpen}
      />
      
      {/* Help Panel (floating desktop / bottom sheet mobile) */}
      <FloatingHelpPanel
        isOpen={helpModalOpen}
        onClose={() => setHelpModalOpen(false)}
        pageKey={helpPageKey}
      />
    </div>
    </div>
  )
}
