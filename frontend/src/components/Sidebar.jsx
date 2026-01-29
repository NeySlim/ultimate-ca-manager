/**
 * Sidebar Component - 56px navigation sidebar
 * Supports Pro features when license is active (dynamic import)
 */
import { useState, useEffect } from 'react'
import { 
  House, Certificate, ShieldCheck, FileText, List, User, Key, Gear,
  SignOut, Palette, Check, UserCircle, UploadSimple, ClockCounterClockwise, Robot,
  UsersThree, Shield, Crown, Lock
} from '@phosphor-icons/react'
import { Link, useNavigate } from 'react-router-dom'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { useTheme } from '../contexts/ThemeContext'
import { useAuth } from '../contexts/AuthContext'
import { cn } from '../lib/utils'
import { Logo } from './Logo'

export function Sidebar({ activePage }) {
  const navigate = useNavigate()
  const { currentTheme, setCurrentTheme, themes } = useTheme()
  const { user, logout } = useAuth()
  
  // Dynamic Pro module loading
  const [proModule, setProModule] = useState(null)
  const [license, setLicense] = useState({ isPro: false, loading: true })
  
  useEffect(() => {
    // Try to dynamically import Pro module
    import('../pro')
      .then(mod => {
        setProModule(mod)
      })
      .catch(() => {
        // Pro module not available - community version
        setLicense({ isPro: false, loading: false })
      })
  }, [])
  
  // Use Pro license hook if available
  useEffect(() => {
    if (proModule?.useLicense) {
      // We can't use hooks conditionally, so we call the API directly
      import('../services/apiClient').then(({ apiClient }) => {
        apiClient.get('/license')
          .then(res => {
            const data = res.data || res
            setLicense({
              isPro: data.type === 'pro' || data.type === 'enterprise' || data.pro_enabled === true,
              loading: false
            })
          })
          .catch(() => setLicense({ isPro: false, loading: false }))
      })
    }
  }, [proModule])

  const pages = [
    { id: '', icon: House, label: 'Dashboard', path: '/' },
    { id: 'certificates', icon: Certificate, label: 'Certificates', path: '/certificates' },
    { id: 'cas', icon: ShieldCheck, label: 'CAs', path: '/cas' },
    { id: 'csrs', icon: FileText, label: 'CSRs', path: '/csrs' },
    { id: 'templates', icon: List, label: 'Templates', path: '/templates' },
    { id: 'users', icon: User, label: 'Users', path: '/users' },
    { id: 'acme', icon: Key, label: 'ACME', path: '/acme' },
    { id: 'scep', icon: Robot, label: 'SCEP', path: '/scep' },
    { id: 'import', icon: UploadSimple, label: 'Import', path: '/import' },
    { id: 'audit', icon: ClockCounterClockwise, label: 'Audit', path: '/audit' },
    { id: 'settings', icon: Gear, label: 'Settings', path: '/settings' },
  ]

  // Pro-only pages (only shown when license is active)
  const proPages = [
    { id: 'groups', icon: UsersThree, label: 'Groups', path: '/groups' },
    { id: 'rbac', icon: Shield, label: 'RBAC', path: '/rbac' },
    { id: 'sso', icon: Key, label: 'SSO', path: '/sso' },
    { id: 'hsm', icon: Lock, label: 'HSM', path: '/hsm' },
  ]

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="w-14 h-full border-r border-border bg-gradient-to-b from-bg-secondary to-bg-tertiary flex flex-col items-center py-2 gap-0.5">
      {/* Logo */}
      <Link to="/" className="w-10 h-10 flex items-center justify-center mb-3" title="UCM Dashboard">
        <Logo variant="compact" size="sm" withText={false} />
      </Link>

      {/* Page Icons */}
      {pages.map(page => {
        const Icon = page.icon
        const isActive = activePage === page.id
        return (
          <Link
            key={page.id}
            to={page.path}
            className={cn(
              "w-10 h-10 rounded-sm flex items-center justify-center transition-all relative group",
              isActive
                ? "bg-bg-tertiary text-accent-primary" 
                : "text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
            )}
            title={page.label}
          >
            <Icon size={18} weight={isActive ? 'fill' : 'regular'} />
            {isActive && (
              <div className="absolute left-0 w-0.5 h-8 bg-accent-primary rounded-r-sm" />
            )}
            {/* Tooltip */}
            <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-border rounded-sm text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
              {page.label}
            </div>
          </Link>
        )
      })}

      {/* Pro Pages - only show if license is active */}
      {license.isPro && !license.loading && (
        <>
          <div className="w-8 border-t border-border my-1" />
          {proPages.map(page => {
            const Icon = page.icon
            const isActive = activePage === page.id
            return (
              <Link
                key={page.id}
                to={page.path}
                className={cn(
                  "w-10 h-10 rounded-sm flex items-center justify-center transition-all relative group",
                  isActive
                    ? "bg-accent-pro/20 text-accent-pro border border-accent-pro/30" 
                    : "text-accent-pro/60 hover:bg-accent-pro/10 hover:text-accent-pro"
                )}
                title={`${page.label} (Pro)`}
              >
                <Icon size={18} weight={isActive ? 'fill' : 'regular'} />
                {isActive && (
                  <div className="absolute left-0 w-0.5 h-8 bg-accent-pro rounded-r-sm" />
                )}
                {/* Tooltip */}
                <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-accent-pro/30 rounded-sm text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 flex items-center gap-1.5">
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
          <button className="w-10 h-10 rounded-sm flex items-center justify-center text-text-secondary hover:bg-bg-tertiary hover:text-text-primary transition-all group">
            <Palette size={18} />
            <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-border rounded-sm text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
              Theme
            </div>
          </button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content 
            className="min-w-[180px] bg-bg-secondary border border-border rounded-sm shadow-lg p-1 z-50"
            sideOffset={5}
            side="right"
          >
            {Object.values(themes).map(theme => (
              <DropdownMenu.Item
                key={theme.id}
                onClick={() => setCurrentTheme(theme.id)}
                className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-bg-tertiary text-text-primary transition-colors"
              >
                <span className="flex-1">{theme.name}</span>
                {currentTheme === theme.id && (
                  <Check size={16} weight="bold" className="text-accent-primary" />
                )}
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      {/* User Menu */}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button className="w-10 h-10 rounded-sm bg-accent-primary/10 border border-accent-primary/20 flex items-center justify-center text-accent-primary hover:bg-accent-primary/20 transition-all group">
            <UserCircle size={18} weight="bold" />
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
              className="flex items-center gap-3 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-red-500/10 text-red-500 transition-colors"
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
