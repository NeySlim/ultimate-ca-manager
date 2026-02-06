/**
 * Sidebar Component - 56px navigation sidebar
 * Supports Pro features when license is active (dynamic import)
 */
import { useState, useEffect } from 'react'
import { 
  House, Certificate, ShieldCheck, FileText, List, User, Key, Gear,
  SignOut, Palette, Check, UserCircle, UploadSimple, ClockCounterClockwise, Robot,
  UsersThree, Shield, Crown, Lock, FileX, Vault, Wrench, Detective
} from '@phosphor-icons/react'
import { Link, useNavigate } from 'react-router-dom'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { useTheme } from '../contexts/ThemeContext'
import { useAuth } from '../contexts/AuthContext'
import { cn } from '../lib/utils'
import { Logo } from './Logo'
import { WebSocketIndicator } from './WebSocketIndicator'
import { useMobile } from '../contexts/MobileContext'
import { certificatesService } from '../services'
import { loadProModule } from '../proLoader.jsx'

export function Sidebar({ activePage }) {
  const navigate = useNavigate()
  const { themeFamily, setThemeFamily, mode, setMode, themes, isLight } = useTheme()
  const { user, logout } = useAuth()
  const { isLargeScreen } = useMobile()
  
  // Expiring certificates badge
  const [expiringCount, setExpiringCount] = useState(0)
  
  // Load expiring count on mount and periodically
  useEffect(() => {
    const loadExpiringCount = async () => {
      try {
        const stats = await certificatesService.getStats()
        const expiring = stats?.data?.expiring || 0
        const expired = stats?.data?.expired || 0
        setExpiringCount(expiring + expired)
      } catch {
        // Ignore errors
      }
    }
    
    loadExpiringCount()
    const interval = setInterval(loadExpiringCount, 5 * 60 * 1000) // Refresh every 5 min
    return () => clearInterval(interval)
  }, [])
  
  // Sizes based on screen width (smaller icons for refined look)
  const iconSize = isLargeScreen ? 20 : 16
  const buttonSize = isLargeScreen ? 'w-10 h-10' : 'w-9 h-9'
  
  // Dynamic Pro module loading
  const [proModule, setProModule] = useState(null)
  const [license, setLicense] = useState({ isPro: false, loading: true })
  
  useEffect(() => {
    // Try to dynamically import Pro module
    loadProModule()
      .then(mod => {
        setProModule(mod)
        // Pro module loaded = Pro features enabled (no license check needed)
        setLicense({ isPro: true, loading: false })
      })
      .catch(() => {
        // Pro module not available - community version
        setLicense({ isPro: false, loading: false })
      })
  }, [])
  
  // Pro is enabled by module presence, no API call needed
  // (keeping this effect empty for backwards compatibility)

  const pages = [
    { id: '', icon: House, label: 'Dashboard', path: '/' },
    { id: 'certificates', icon: Certificate, label: 'Certificates', path: '/certificates' },
    { id: 'cas', icon: ShieldCheck, label: 'CAs', path: '/cas' },
    { id: 'csrs', icon: FileText, label: 'CSRs', path: '/csrs' },
    { id: 'templates', icon: List, label: 'Templates', path: '/templates' },
    { id: 'users', icon: User, label: 'Users', path: '/users' },
    { id: 'acme', icon: Key, label: 'ACME', path: '/acme' },
    { id: 'scep', icon: Robot, label: 'SCEP', path: '/scep-config' },
    { id: 'crl-ocsp', icon: FileX, label: 'CRL/OCSP', path: '/crl-ocsp' },
    { id: 'truststore', icon: Vault, label: 'Trust Store', path: '/truststore' },
    { id: 'import', icon: UploadSimple, label: 'Import', path: '/import' },
    { id: 'tools', icon: Wrench, label: 'Tools', path: '/tools' },
    { id: 'audit', icon: ClockCounterClockwise, label: 'Audit', path: '/audit' },
    { id: 'settings', icon: Gear, label: 'Settings', path: '/settings' },
  ]

  // Pro-only pages (only shown when license is active)
  // SSO is now in Settings, Groups is now in Users
  const proPages = [
    { id: 'rbac', icon: Shield, label: 'RBAC', path: '/rbac' },
    { id: 'hsm', icon: Lock, label: 'HSM', path: '/hsm' },
    { id: 'security', icon: Detective, label: 'Security', path: '/security' },
  ]

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="w-14 h-full border-r border-border/60 bg-gradient-to-b from-bg-secondary to-bg-tertiary flex flex-col items-center py-2 gap-px">
      {/* Logo */}
      <Link to="/" className={cn(buttonSize, "flex items-center justify-center mb-2")} title="UCM Dashboard">
        <Logo variant="compact" size="sm" withText={false} />
      </Link>

      {/* Page Icons */}
      {pages.map(page => {
        const Icon = page.icon
        const isActive = activePage === page.id
        const showBadge = page.id === 'certificates' && expiringCount > 0
        return (
          <Link
            key={page.id}
            to={page.path}
            className={cn(
              buttonSize,
              "rounded-lg flex items-center justify-center transition-all duration-200 relative group",
              isActive
                ? "bg-accent-primary/10 text-accent-primary border border-accent-primary/20" 
                : "text-text-secondary hover:bg-bg-tertiary/70 hover:text-text-primary"
            )}
            title={showBadge ? `${page.label} (${expiringCount} expiring)` : page.label}
          >
            <Icon size={iconSize} weight={isActive ? 'fill' : 'regular'} />
            {isActive && (
              <div className="absolute left-0 w-0.5 h-5 bg-accent-primary rounded-r-full" />
            )}
            {/* Expiring badge */}
            {showBadge && (
              <div className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-status-warning border border-bg-secondary flex items-center justify-center">
                <span className="text-3xs font-bold text-white">
                  {expiringCount > 9 ? '9+' : expiringCount}
                </span>
              </div>
            )}
            {/* Tooltip */}
            <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-border rounded-md text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50">
              {page.label}
              {showBadge && (
                <span className="ml-1 text-status-warning">({expiringCount} expiring)</span>
              )}
            </div>
          </Link>
        )
      })}

      {/* Pro Pages - only show if license is active */}
      {license.isPro && !license.loading && (
        <>
          <div className="w-7 border-t border-border/60 my-1" />
          {proPages.map(page => {
            const Icon = page.icon
            const isActive = activePage === page.id
            return (
              <Link
                key={page.id}
                to={page.path}
                className={cn(
                  buttonSize,
                  "rounded-lg flex items-center justify-center transition-all duration-200 relative group",
                  isActive
                    ? "bg-accent-pro/20 text-accent-pro border border-accent-pro/30" 
                    : "text-accent-pro/60 hover:bg-accent-pro/10 hover:text-accent-pro"
                )}
                title={`${page.label} (Pro)`}
              >
                <Icon size={iconSize} weight={isActive ? 'fill' : 'regular'} />
                {isActive && (
                  <div className="absolute left-0 w-0.5 h-5 bg-accent-pro rounded-r-full" />
                )}
                {/* Tooltip */}
                <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-accent-pro/30 rounded-md text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50 flex items-center gap-1.5">
                  <Crown size={12} className="text-accent-pro" />
                  {page.label}
                </div>
              </Link>
            )
          })}
        </>
      )}

      <div className="flex-1" />

      {/* Theme Selector */}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button className={cn(buttonSize, "rounded-sm flex items-center justify-center text-text-secondary hover:bg-bg-tertiary hover:text-text-primary transition-all group")}>
            <Palette size={iconSize} />
            <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-border rounded-sm text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
              Theme
            </div>
          </button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content 
            className="min-w-[200px] bg-bg-secondary border border-border rounded-sm shadow-lg p-1 z-50"
            sideOffset={5}
            side="right"
          >
            <DropdownMenu.Label className="px-3 py-1.5 text-xs text-text-tertiary uppercase tracking-wider">
              Color Theme
            </DropdownMenu.Label>
            {themes.map(theme => (
              <DropdownMenu.Item
                key={theme.id}
                onClick={() => setThemeFamily(theme.id)}
                className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
              >
                <div 
                  className="w-3 h-3 rounded-full border border-border"
                  style={{ background: theme.accent }}
                />
                <span className="flex-1">{theme.name}</span>
                {themeFamily === theme.id && (
                  <Check size={16} weight="bold" className="text-accent-primary" />
                )}
              </DropdownMenu.Item>
            ))}
            
            <DropdownMenu.Separator className="h-px bg-border my-1" />
            
            <DropdownMenu.Label className="px-3 py-1.5 text-xs text-text-tertiary uppercase tracking-wider">
              Appearance
            </DropdownMenu.Label>
            {[
              { id: 'system', label: 'Follow System' },
              { id: 'dark', label: 'Dark' },
              { id: 'light', label: 'Light' }
            ].map(opt => (
              <DropdownMenu.Item
                key={opt.id}
                onClick={() => setMode(opt.id)}
                className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
              >
                <span className="flex-1">{opt.label}</span>
                {mode === opt.id && (
                  <Check size={16} weight="bold" className="text-accent-primary" />
                )}
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      {/* WebSocket Indicator */}
      <WebSocketIndicator className="mx-auto" />

      {/* User Menu */}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button className={cn(buttonSize, "rounded-sm bg-accent-primary/10 border border-accent-primary/20 flex items-center justify-center text-accent-primary hover:bg-accent-primary/20 transition-all group")}>
            <UserCircle size={iconSize} weight="bold" />
            <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-border rounded-sm text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
              {user?.username || 'User'}
            </div>
          </button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content 
            className="min-w-[180px] bg-bg-secondary border border-border rounded-sm shadow-lg p-1 z-50"
            sideOffset={5}
            side="right"
          >
            <DropdownMenu.Item
              onClick={() => navigate('/account')}
              className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
            >
              <UserCircle size={16} />
              <span>Account</span>
            </DropdownMenu.Item>

            <DropdownMenu.Item
              onClick={() => navigate('/settings')}
              className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
            >
              <Gear size={16} />
              <span>Settings</span>
            </DropdownMenu.Item>

            <DropdownMenu.Separator className="h-px bg-border my-1" />

            <DropdownMenu.Item
              onClick={handleLogout}
              className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:status-danger-bg status-danger-text transition-colors"
            >
              <SignOut size={16} />
              <span>Sign Out</span>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  )
}
