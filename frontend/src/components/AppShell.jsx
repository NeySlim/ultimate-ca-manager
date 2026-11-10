/**
 * AppShell Component - Atelier layout: top bar, page, status bar
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation } from 'react-router-dom'
import { TopBar } from './shell/TopBar'
import { StatusBar } from './shell/StatusBar'
import { usePins } from './shell/pins'
import { resolveActivePageId } from './shell/activePage'
import { CommandPalette, useKeyboardShortcuts } from './CommandPalette'
import { FloatingHelpPanel } from './ui/FloatingHelpPanel'
import { UpdatePopup } from './UpdatePopup'
import { KofiSupportCard } from './KofiSupportCard'
import { StatusFooter } from './ui/StatusFooter'
import { useNotification } from '../contexts/NotificationContext'
import { usePermission } from '../hooks'
import { certificatesService } from '../services'

export function AppShell() {
  const { t } = useTranslation()
  const location = useLocation()
  const { isAdmin, hasPermission } = usePermission()
  const can = { isAdmin, hasPermission }
  const { pins, toggle: togglePin } = usePins(can)
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [helpModalOpen, setHelpModalOpen] = useState(false)
  // Help key requested by the shell itself (navigation help); cleared on close
  const [helpOverride, setHelpOverride] = useState(null)
  const [isMobile, setIsMobile] = useState(false)
  const { showWarning } = useNotification()

  // Derive the active nav item from the URL (see resolveActivePageId)
  const activePage = resolveActivePageId(location.pathname)
  
  // Map URL paths to helpContent keys
  // Use full path for nested routes (e.g. /ssh/cas → sshCas)
  const fullPath = location.pathname.replace(/^\//, '').replace(/\/$/, '')
  const helpPageKeyMap = {
    '': 'dashboard',
    'audit': 'auditLogs',
    'crl-ocsp': 'crlocsp',
    'users': 'usersGroups',
    'tools': 'certTools',
    'ssh/cas': 'sshCas',
    'ssh/certificates': 'sshCertificates'
  }
  const helpPageKey = helpPageKeyMap[fullPath] || helpPageKeyMap[activePage] || activePage
  
  // Pages that have contextual help
  const pagesWithHelp = [
    // Core pages
    'certificates', 'cas', 'csrs', 'users', 'templates',
    'acme', 'scep', 'est', 'tsa', 'settings', 'truststore', 'crl-ocsp',
    'tools', 'audit', 'account', 'operations', 'user-certificates',
    // Pro pages
    'rbac', 'hsm',
    // SSH pages
    'ssh-cas', 'ssh-certificates',
    // Governance pages
    'keyRecovery', 'policies', 'approvals', 'reports', 'discovery'
  ]
  const hasHelp = pagesWithHelp.includes(activePage) || activePage === ''

  // Phone width: the window-manager footer is desktop only
  useEffect(() => {
    const checkViewport = () => setIsMobile(window.innerWidth < 768)
    checkViewport()
    window.addEventListener('resize', checkViewport)
    return () => window.removeEventListener('resize', checkViewport)
  }, [])

  // Check for expiring certificates on mount (once per session)
  useEffect(() => {
    // Cancelling the timer was not enough: once the 2s delay had elapsed the
    // request was already in flight, and its continuation raised the expiry
    // warning after the shell had unmounted — i.e. a toast landing on the
    // login screen, for a session that had just ended.
    let cancelled = false
    const checkExpiringCerts = async () => {
      // Check if we already showed the alert this session
      const alreadyShown = sessionStorage.getItem('ucm-expiring-alert-shown')
      if (alreadyShown) return

      try {
        const stats = await certificatesService.getStats()
        if (cancelled) return
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
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [showWarning, t])

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onCommandPalette: () => setCommandPaletteOpen(true)
  })

  // ? key opens help panel (when not typing in an input)
  useEffect(() => {
    const handleHelpKey = (e) => {
      if (e.key === '?' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) && !e.target.isContentEditable) {
        e.preventDefault()
        setHelpModalOpen(prev => !prev)
      }
    }
    window.addEventListener('keydown', handleHelpKey)
    return () => window.removeEventListener('keydown', handleHelpKey)
  }, [])

  const openHelp = (key) => {
    setHelpOverride(typeof key === 'string' ? key : null)
    setHelpModalOpen(true)
  }

  return (
    <div className="shell-root">
      <TopBar
        can={can}
        pins={pins}
        onTogglePin={togglePin}
        activeId={activePage}
        onOpenSearch={() => setCommandPaletteOpen(true)}
        onOpenHelp={openHelp}
        hasHelp={hasHelp}
      />

      <div className="shell-main">
        <div className="shell-content">
          <div className="flex-1 flex min-h-0 min-w-0 overflow-auto">
            <Outlet />
          </div>

          {/* Window-manager footer: desktop only, not on the dashboard */}
          {!isMobile && activePage !== '' && activePage !== 'dashboard' && <StatusFooter />}
        </div>
      </div>

      <StatusBar />

      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={setCommandPaletteOpen}
      />

      {/* Help Panel (floating desktop / bottom sheet mobile) */}
      <FloatingHelpPanel
        isOpen={helpModalOpen}
        onClose={() => { setHelpModalOpen(false); setHelpOverride(null) }}
        pageKey={helpOverride || helpPageKey}
      />

      {/* Optional what's-new window after an update (#308) */}
      <UpdatePopup />

      {/* Ko-fi support card, once per version for admins */}
      <KofiSupportCard />
    </div>
  )
}
