/**
 * Sidebar Component - Accordion navigation sidebar (~200px)
 * Groups: Dashboard (direct), PKI, Protocols, Tools, Governance, Admin
 * Each group expands/collapses inline to show sub-items
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  House, Certificate, ShieldCheck, FileText, List, User, Key, Gear,
  SignOut, Check, UserCircle, Lightning, ClockCounterClockwise, Robot,
  UsersThree, Shield, Lock, FileX, Vault, Wrench, Globe, CaretRight,
  Gavel, Stamp, ChartBar, Stack, Broadcast, CaretDown, MagnifyingGlass
} from '@phosphor-icons/react'
import { Link, useNavigate } from 'react-router-dom'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { useTheme } from '../contexts/ThemeContext'
import { useAuth } from '../contexts/AuthContext'
import { usePermission } from '../hooks'
import { cn } from '../lib/utils'
import { Logo } from './Logo'
import { WebSocketIndicator } from './WebSocketIndicator'
import { useMobile } from '../contexts/MobileContext'
import { certificatesService } from '../services'
import { languages } from '../i18n'

// Navigation groups — each has a trigger icon and child items
const navGroups = [
  {
    id: 'pki',
    icon: Certificate,
    labelKey: 'common.navPki',
    children: [
      { id: 'certificates', icon: Certificate, labelKey: 'common.certificates', path: '/certificates' },
      { id: 'cas', icon: ShieldCheck, labelKey: 'common.cas', path: '/cas' },
      { id: 'csrs', icon: FileText, labelKey: 'common.csrs', path: '/csrs' },
      { id: 'templates', icon: List, labelKey: 'common.templates', path: '/templates' },
    ]
  },
  {
    id: 'protocols',
    icon: Broadcast,
    labelKey: 'common.navProtocols',
    children: [
      { id: 'acme', icon: Key, labelKey: 'common.acme', path: '/acme', permission: 'read:acme' },
      { id: 'scep', icon: Robot, labelKey: 'common.scep', path: '/scep-config', permission: 'read:scep' },
      { id: 'est', icon: Globe, labelKey: 'common.est', path: '/est-config', permission: 'read:est' },
      { id: 'crl-ocsp', icon: FileX, labelKey: 'common.crlOcsp', path: '/crl-ocsp', permission: 'read:crl' },
    ]
  },
  {
    id: 'tools',
    icon: Wrench,
    labelKey: 'common.navTools',
    children: [
      { id: 'truststore', icon: Vault, labelKey: 'common.trustStore', path: '/truststore', permission: 'read:truststore' },
      { id: 'operations', icon: Lightning, labelKey: 'common.operations', path: '/operations', adminOnly: true },
      { id: 'tools', icon: Wrench, labelKey: 'common.tools', path: '/tools' },
    ]
  },
  {
    id: 'governance',
    icon: Gavel,
    labelKey: 'common.navGovernance',
    children: [
      { id: 'policies', icon: Gavel, labelKey: 'common.policies', path: '/policies', permission: 'read:policies' },
      { id: 'approvals', icon: Stamp, labelKey: 'common.approvals', path: '/approvals', permission: 'read:approvals' },
      { id: 'reports', icon: ChartBar, labelKey: 'common.reports', path: '/reports', permission: 'read:audit' },
      { id: 'discovery', icon: MagnifyingGlass, labelKey: 'common.discovery', path: '/discovery', permission: 'read:certificates' },
    ]
  },
  {
    id: 'admin',
    icon: Shield,
    labelKey: 'common.navAdmin',
    children: [
      { id: 'users', icon: User, labelKey: 'common.users', path: '/users', adminOnly: true },
      { id: 'rbac', icon: Shield, labelKey: 'common.rbac', path: '/rbac', adminOnly: true },
      { id: 'hsm', icon: Lock, labelKey: 'common.hsm', path: '/hsm', permission: 'read:hsm' },
      { id: 'audit', icon: ClockCounterClockwise, labelKey: 'common.audit', path: '/audit', permission: 'read:audit' },
    ]
  },
]

function NavGroup({ group, activePage, isAdmin, hasPermission, expanded, onToggle, expiringCount, isBadgeDismissed, dismissBadge, t }) {
  const visibleChildren = group.children.filter(child => {
    if (child.adminOnly && !isAdmin()) return false
    if (child.permission && !isAdmin() && !hasPermission(child.permission)) return false
    return true
  })

  if (visibleChildren.length === 0) return null

  const groupHasActive = visibleChildren.some(c => c.id === activePage)
  const GroupIcon = group.icon
  const isOpen = expanded

  return (
    <div className="w-full">
      {/* Group header — click to expand/collapse */}
      <button
        type="button"
        onClick={onToggle}
        title={t(group.labelKey)}
        className={cn(
          "w-full flex items-center gap-2 px-2.5 py-[7px] rounded-md text-[11px] font-semibold tracking-wide transition-colors",
          groupHasActive
            ? "text-accent-primary"
            : "text-text-tertiary hover:text-text-secondary hover:bg-bg-tertiary"
        )}
      >
        <GroupIcon size={14} weight={groupHasActive ? 'fill' : 'regular'} className="shrink-0 opacity-70" />
        <span className="flex-1 text-left truncate">{t(group.labelKey)}</span>
        {/* Expiring badge on PKI */}
        {group.id === 'pki' && expiringCount > 0 && !isBadgeDismissed && (
          <span
            onClick={dismissBadge}
            className="w-4 h-4 rounded-full bg-status-warning flex items-center justify-center cursor-pointer hover:opacity-70"
            title={t('common.dismiss')}
          >
            <span className="text-3xs font-bold text-black/80">{expiringCount > 9 ? '9+' : expiringCount}</span>
          </span>
        )}
        <CaretDown
          size={10}
          weight="bold"
          className={cn("transition-transform duration-200 shrink-0 opacity-50", isOpen ? "" : "-rotate-90")}
        />
      </button>

      {/* Expandable children */}
      <div
        className={cn(
          "overflow-hidden transition-all duration-200 ease-out",
          isOpen ? "max-h-[300px] opacity-100" : "max-h-0 opacity-0"
        )}
      >
        <div className="py-0.5 pl-2">
          {visibleChildren.map(child => {
            const ChildIcon = child.icon
            const isActive = activePage === child.id
            const showCertBadge = child.id === 'certificates' && expiringCount > 0 && !isBadgeDismissed
            const label = t(child.labelKey)
            return (
              <Link
                key={child.id}
                to={child.path}
                title={label}
                className={cn(
                  "flex items-center gap-2 px-2 py-[5px] rounded-md text-[13px] transition-all duration-150 relative",
                  isActive
                    ? "bg-accent-primary-op15 text-accent-primary font-medium"
                    : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                )}
              >
                {isActive && (
                  <div className="absolute left-0 w-[3px] h-4 bg-accent-primary rounded-r-full" />
                )}
                <ChildIcon size={15} weight={isActive ? 'fill' : 'regular'} className="shrink-0" />
                <span className="truncate">{label}</span>
                {showCertBadge && (
                  <span className="ml-auto text-3xs px-1 py-0.5 rounded-full bg-status-warning text-black/80 font-bold shrink-0">
                    {expiringCount > 9 ? '9+' : expiringCount}
                  </span>
                )}
              </Link>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export function Sidebar({ activePage }) {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, themes, isLight } = useTheme()
  const { user, logout } = useAuth()
  const { isAdmin, canRead, canWrite, hasPermission } = usePermission()
  const { isLargeScreen } = useMobile()
  
  // Accordion state — persist which groups are expanded
  const [expandedGroups, setExpandedGroups] = useState(() => {
    try {
      const stored = localStorage.getItem('ucm_nav_expanded')
      return stored ? JSON.parse(stored) : ['pki']
    } catch { return ['pki'] }
  })

  // Auto-expand group containing active page
  useEffect(() => {
    const activeGroup = navGroups.find(g => g.children.some(c => c.id === activePage))
    if (activeGroup && !expandedGroups.includes(activeGroup.id)) {
      setExpandedGroups(prev => {
        const next = [...prev, activeGroup.id]
        try { localStorage.setItem('ucm_nav_expanded', JSON.stringify(next)) } catch {}
        return next
      })
    }
  }, [activePage]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleGroup = useCallback((groupId) => {
    setExpandedGroups(prev => {
      const next = prev.includes(groupId) ? prev.filter(id => id !== groupId) : [...prev, groupId]
      try { localStorage.setItem('ucm_nav_expanded', JSON.stringify(next)) } catch {}
      return next
    })
  }, [])

  // Expiring certificates badge
  const [expiringCount, setExpiringCount] = useState(0)
  const [badgeDismissed, setBadgeDismissed] = useState(() => {
    try {
      const stored = localStorage.getItem('ucm_badge_dismissed')
      return stored ? JSON.parse(stored) : { count: 0, at: 0 }
    } catch { return { count: 0, at: 0 } }
  })
  
  const isBadgeDismissed = badgeDismissed.count === expiringCount && expiringCount > 0
  
  const dismissBadge = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    const state = { count: expiringCount, at: Date.now() }
    setBadgeDismissed(state)
    try { localStorage.setItem('ucm_badge_dismissed', JSON.stringify(state)) } catch {}
  }, [expiringCount])
  
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
    const interval = setInterval(loadExpiringCount, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="w-[200px] h-full border-r border-border bg-bg-secondary flex flex-col py-2.5 overflow-hidden">
      {/* Logo + App name */}
      <Link to="/" className="flex items-center gap-2.5 px-3.5 mb-1 shrink-0" title={t('common.dashboard')}>
        <Logo variant="icon" withText={false} size="xs" />
        <div className="flex flex-col min-w-0">
          <span className="text-xs font-bold text-text-primary leading-tight">UCM</span>
          <span className="text-3xs text-text-tertiary leading-tight truncate">Certificate Manager</span>
        </div>
      </Link>

      <div className="h-px bg-border mx-3 my-2 shrink-0" />

      {/* Dashboard - direct link */}
      <div className="px-2 mb-1 shrink-0">
        <Link
          to="/"
          className={cn(
            "flex items-center gap-2 px-2.5 py-[6px] rounded-md text-[13px] transition-all duration-150 relative w-full",
            activePage === ''
              ? "bg-accent-primary-op15 text-accent-primary font-medium"
              : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
          )}
        >
          {activePage === '' && (
            <div className="absolute left-0 w-[3px] h-4 bg-accent-primary rounded-r-full" />
          )}
          <House size={15} weight={activePage === '' ? 'fill' : 'regular'} className="shrink-0" />
          <span>{t('common.dashboard')}</span>
        </Link>
      </div>

      {/* Scrollable nav groups */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2 space-y-0.5 scrollbar-thin">
        {navGroups.map(group => (
          <NavGroup
            key={group.id}
            group={group}
            activePage={activePage}
            isAdmin={isAdmin}
            hasPermission={hasPermission}
            expanded={expandedGroups.includes(group.id)}
            onToggle={() => toggleGroup(group.id)}
            expiringCount={expiringCount}
            isBadgeDismissed={isBadgeDismissed}
            dismissBadge={dismissBadge}
            t={t}
          />
        ))}
      </nav>

      {/* Bottom section */}
      <div className="shrink-0 mt-1 px-2">
        <div className="h-px bg-border mx-1 mb-1.5" />

        {/* Settings */}
        {(isAdmin() || canRead('settings')) && (
          <Link
            to="/settings"
            className={cn(
              "flex items-center gap-2 px-2.5 py-[6px] rounded-md text-[13px] transition-all duration-150 relative w-full",
              activePage === 'settings'
                ? "bg-accent-primary-op15 text-accent-primary font-medium"
                : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
            )}
          >
            {activePage === 'settings' && (
              <div className="absolute left-0 w-[3px] h-4 bg-accent-primary rounded-r-full" />
            )}
            <Gear size={15} weight={activePage === 'settings' ? 'fill' : 'regular'} className="shrink-0" />
            <span>{t('common.settings')}</span>
          </Link>
        )}

        {/* User Menu — with integrated WebSocket status dot */}
        <div className="mt-1.5 pt-1.5 border-t border-border">
          <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button className="w-full flex items-center gap-2.5 px-2 py-2 rounded-md hover:bg-bg-tertiary transition-colors">
              <div className="relative shrink-0">
                <div className="w-7 h-7 rounded-full bg-accent-primary-op15 border border-accent-primary-op20 flex items-center justify-center">
                  <UserCircle size={16} weight="bold" className="text-accent-primary" />
                </div>
                <WebSocketIndicator variant="dot" className="absolute -bottom-0.5 -right-0.5" />
              </div>
              <div className="flex-1 min-w-0 text-left">
                <div className="text-[13px] font-medium text-text-primary truncate">{user?.username || 'User'}</div>
                <div className="text-3xs text-text-tertiary capitalize">{user?.role || ''}</div>
              </div>
              <CaretRight size={10} className="text-text-tertiary shrink-0 opacity-60" />
            </button>
          </DropdownMenu.Trigger>

          <DropdownMenu.Portal>
            <DropdownMenu.Content 
              className="min-w-[200px] bg-bg-secondary border border-border rounded-lg shadow-xl p-1 z-50"
              sideOffset={5}
              side="right"
              align="end"
            >
              {/* User identity header */}
              <div className="px-3 py-2 mb-1">
                <div className="text-sm font-semibold text-text-primary truncate">{user?.username || 'User'}</div>
                <div className="text-xs text-text-tertiary capitalize">{user?.role || ''}</div>
              </div>
              <DropdownMenu.Separator className="h-px bg-border mb-1" />

              <DropdownMenu.Item
                onClick={() => navigate('/account')}
                className="flex items-center gap-3 px-3 py-2 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
              >
                <UserCircle size={16} />
                <span>{t('common.account')}</span>
              </DropdownMenu.Item>

              {(isAdmin() || canRead('settings')) && (
              <DropdownMenu.Item
                onClick={() => navigate('/settings')}
                className="flex items-center gap-3 px-3 py-2 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
              >
                <Gear size={16} />
                <span>{t('common.settings')}</span>
              </DropdownMenu.Item>
              )}

              <DropdownMenu.Separator className="h-px bg-border my-1" />

              {/* Theme sub-section */}
              <DropdownMenu.Label className="px-3 py-1.5 text-xs text-text-tertiary uppercase tracking-wider">
                {t('settings.colorTheme')}
              </DropdownMenu.Label>
              {themes.map(theme => (
                <DropdownMenu.Item
                  key={theme.id}
                  onClick={() => setThemeFamily(theme.id)}
                  className="flex items-center gap-3 px-3 py-2 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
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
                  className="flex items-center gap-3 px-3 py-2 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
                >
                  <span className="flex-1">{t(opt.labelKey)}</span>
                  {mode === opt.id && (
                    <Check size={16} weight="bold" className="text-accent-primary" />
                  )}
                </DropdownMenu.Item>
              ))}

              <DropdownMenu.Separator className="h-px bg-border my-1" />

              {/* Language sub-section */}
              <DropdownMenu.Label className="px-3 py-1.5 text-xs text-text-tertiary uppercase tracking-wider">
                {t('settings.language')}
              </DropdownMenu.Label>
              <DropdownMenu.Sub>
                <DropdownMenu.SubTrigger className="flex items-center gap-3 px-3 py-2 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors data-[state=open]:bg-bg-tertiary">
                  <Globe size={16} />
                  <span className="flex-1">{languages.find(l => l.code === (i18n.language?.split('-')[0] || 'en'))?.flag} {languages.find(l => l.code === (i18n.language?.split('-')[0] || 'en'))?.name || 'English'}</span>
                  <CaretRight size={12} className="text-text-tertiary" />
                </DropdownMenu.SubTrigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.SubContent className="min-w-[180px] bg-bg-secondary border border-border rounded-lg shadow-lg p-1 z-50">
                    {languages.map(lang => (
                      <DropdownMenu.Item
                        key={lang.code}
                        onClick={() => {
                          i18n.changeLanguage(lang.code)
                          try { localStorage.setItem('i18nextLng', lang.code) } catch {}
                        }}
                        className="flex items-center gap-3 px-3 py-2 text-sm rounded-md cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
                      >
                        <span>{lang.flag}</span>
                        <span className="flex-1">{lang.name}</span>
                        {(i18n.language?.split('-')[0] || 'en') === lang.code && (
                          <Check size={16} weight="bold" className="text-accent-primary" />
                        )}
                      </DropdownMenu.Item>
                    ))}
                  </DropdownMenu.SubContent>
                </DropdownMenu.Portal>
              </DropdownMenu.Sub>

              <DropdownMenu.Separator className="h-px bg-border my-1" />

              <DropdownMenu.Item
                onClick={handleLogout}
                className="flex items-center gap-3 px-3 py-2 text-sm rounded-md cursor-pointer outline-none hover:bg-status-danger-op10 text-status-danger transition-colors"
              >
                <SignOut size={16} />
                <span>{t('auth.logout')}</span>
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        </div>
      </div>
    </div>
  )
}

// Export navGroups for use by AppShell mobile nav
export { navGroups }
