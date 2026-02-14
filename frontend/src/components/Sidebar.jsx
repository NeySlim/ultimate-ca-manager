/**
 * Sidebar Component - 56px navigation sidebar
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  House, Certificate, ShieldCheck, FileText, List, User, Key, Gear,
  SignOut, Check, UserCircle, Lightning, ClockCounterClockwise, Robot,
  UsersThree, Shield, Lock, FileX, Vault, Wrench
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

export function Sidebar({ activePage }) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, themes, isLight } = useTheme()
  const { user, logout } = useAuth()
  const { isLargeScreen } = useMobile()
  
  // Expiring certificates badge
  const [expiringCount, setExpiringCount] = useState(0)
  const [badgeDismissed, setBadgeDismissed] = useState(() => {
    const stored = localStorage.getItem('ucm_badge_dismissed')
    return stored ? JSON.parse(stored) : { count: 0, at: 0 }
  })
  
  const isBadgeDismissed = badgeDismissed.count === expiringCount && expiringCount > 0
  
  const dismissBadge = (e) => {
    e.preventDefault()
    e.stopPropagation()
    const state = { count: expiringCount, at: Date.now() }
    setBadgeDismissed(state)
    localStorage.setItem('ucm_badge_dismissed', JSON.stringify(state))
  }
  
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
  
  // Sizes based on screen width
  const iconSize = isLargeScreen ? 22 : 18
  const buttonSize = isLargeScreen ? 'w-10 h-9' : 'w-8 h-7'
  const sidebarWidth = isLargeScreen ? 'w-[52px]' : 'w-10'

  const pages = [
    // Dashboard
    { id: '', icon: House, labelKey: 'common.dashboard', path: '/' },
    'separator',
    // PKI
    { id: 'certificates', icon: Certificate, labelKey: 'common.certificates', path: '/certificates' },
    { id: 'cas', icon: ShieldCheck, labelKey: 'common.cas', path: '/cas' },
    { id: 'csrs', icon: FileText, labelKey: 'common.csrs', path: '/csrs' },
    { id: 'templates', icon: List, labelKey: 'common.templates', path: '/templates' },
    'separator',
    // Protocols
    { id: 'acme', icon: Key, labelKey: 'common.acme', path: '/acme' },
    { id: 'scep', icon: Robot, labelKey: 'common.scep', path: '/scep-config' },
    { id: 'crl-ocsp', icon: FileX, labelKey: 'common.crlOcsp', path: '/crl-ocsp' },
    'separator',
    // Data
    { id: 'truststore', icon: Vault, labelKey: 'common.trustStore', path: '/truststore' },
    { id: 'operations', icon: Lightning, labelKey: 'common.operations', path: '/operations' },
    { id: 'tools', icon: Wrench, labelKey: 'common.tools', path: '/tools' },
    'separator',
    // Admin
    { id: 'users', icon: User, labelKey: 'common.users', path: '/users' },
    { id: 'rbac', icon: Shield, labelKey: 'common.rbac', path: '/rbac' },
    { id: 'hsm', icon: Lock, labelKey: 'common.hsm', path: '/hsm' },
    { id: 'audit', icon: ClockCounterClockwise, labelKey: 'common.audit', path: '/audit' },
  ]

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className={cn(sidebarWidth, "h-full border-r border-border/60 bg-gradient-to-b from-bg-secondary to-bg-tertiary flex flex-col items-center py-2 gap-px")}>
      {/* Logo */}
      <Link to="/" className="flex items-center justify-center mb-2" style={{ width: isLargeScreen ? 42 : 34, height: isLargeScreen ? 42 : 34 }} title={t('common.dashboard')}>
        <Logo variant="icon" withText={false} size={isLargeScreen ? 'sm' : 'xs'} />
      </Link>

      {/* Page Icons */}
      {pages.map((page, idx) => {
        if (page === 'separator') {
          return <div key={`sep-${idx}`} className="w-6 h-px bg-border/40 my-2" />
        }
        const Icon = page.icon
        const isActive = activePage === page.id
        const showBadge = page.id === 'certificates' && expiringCount > 0 && !isBadgeDismissed
        const label = t(page.labelKey)
        return (
          <Link
            key={page.id}
            to={page.path}
            className={cn(
              buttonSize,
              "rounded-lg flex items-center justify-center transition-all duration-200 relative group",
              isActive
                ? "sidebar-active-gradient text-accent-primary border border-accent-primary/20" 
                : "text-text-secondary hover:bg-bg-tertiary/70 hover:text-text-primary"
            )}
            title={showBadge ? `${label} (${expiringCount} ${t('common.expiring').toLowerCase()})` : label}
          >
            <Icon size={iconSize} weight={isActive ? 'fill' : 'regular'} />
            {isActive && (
              <div className="absolute left-0 w-0.5 h-5 bg-accent-primary rounded-r-full" />
            )}
            {/* Expiring badge */}
            {showBadge && (
              <div
                onClick={dismissBadge}
                className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-status-warning border border-bg-secondary flex items-center justify-center cursor-pointer hover:opacity-70 transition-opacity"
                title={t('common.dismiss')}
              >
                <span className="text-3xs font-bold text-black/80">
                  {expiringCount > 9 ? '9+' : expiringCount}
                </span>
              </div>
            )}
            {/* Tooltip */}
            <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-border rounded-md text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50">
              {label}
              {showBadge && (
                <span className="ml-1 text-status-warning">({expiringCount} {t('common.expiring').toLowerCase()})</span>
              )}
            </div>
          </Link>
        )
      })}

      <div className="flex-1" />

      {/* Settings */}
      <Link
        to="/settings"
        className={cn(
          buttonSize,
          "rounded-lg flex items-center justify-center transition-all duration-200 relative group",
          activePage === 'settings'
            ? "sidebar-active-gradient text-accent-primary border border-accent-primary/20"
            : "text-text-secondary hover:bg-bg-tertiary/70 hover:text-text-primary"
        )}
        title={t('common.settings')}
      >
        <Gear size={iconSize} weight={activePage === 'settings' ? 'fill' : 'regular'} />
        {activePage === 'settings' && (
          <div className="absolute left-0 w-0.5 h-5 bg-accent-primary rounded-r-full" />
        )}
        <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-border rounded-md text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50">
          {t('common.settings')}
        </div>
      </Link>

      {/* WebSocket Indicator */}
      <WebSocketIndicator className="mx-auto" />

      {/* User Menu (with Theme) */}
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
            className="min-w-[200px] bg-bg-secondary border border-border rounded-sm shadow-lg p-1 z-50"
            sideOffset={5}
            side="right"
          >
            <DropdownMenu.Item
              onClick={() => navigate('/account')}
              className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
            >
              <UserCircle size={16} />
              <span>{t('common.account')}</span>
            </DropdownMenu.Item>

            <DropdownMenu.Item
              onClick={() => navigate('/settings')}
              className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
            >
              <Gear size={16} />
              <span>{t('common.settings')}</span>
            </DropdownMenu.Item>

            <DropdownMenu.Separator className="h-px bg-border my-1" />

            {/* Theme sub-section */}
            <DropdownMenu.Label className="px-3 py-1.5 text-xs text-text-tertiary uppercase tracking-wider">
              {t('settings.colorTheme')}
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
              {t('settings.appearanceMode')}
            </DropdownMenu.Label>
            {[
              { id: 'system', labelKey: 'settings.followSystem' },
              { id: 'dark', labelKey: 'settings.dark' },
              { id: 'light', labelKey: 'settings.light' }
            ].map(opt => (
              <DropdownMenu.Item
                key={opt.id}
                onClick={() => setMode(opt.id)}
                className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
              >
                <span className="flex-1">{t(opt.labelKey)}</span>
                {mode === opt.id && (
                  <Check size={16} weight="bold" className="text-accent-primary" />
                )}
              </DropdownMenu.Item>
            ))}

            <DropdownMenu.Separator className="h-px bg-border my-1" />

            <DropdownMenu.Item
              onClick={handleLogout}
              className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:status-danger-bg status-danger-text transition-colors"
            >
              <SignOut size={16} />
              <span>{t('auth.logout')}</span>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  )
}
