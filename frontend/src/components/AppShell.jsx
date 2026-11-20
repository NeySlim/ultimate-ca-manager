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
import { usePermission } from '../hooks'
import { InspectorDock } from './inspector/InspectorDock'
import { useDockPlacement } from './inspector/placement'

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
  // The inspector sits in the page flow: under the page, or beside it on the right
  const dockPlacement = useDockPlacement()

  // Derive the active nav item from the URL (see resolveActivePageId)
  const activePage = resolveActivePageId(location.pathname)
  const onOverview = activePage === '' || activePage === 'dashboard'
  
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

  // No arrival notice on expiries: the state counters and the bell already say them

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
      {/* The stage holds the page and the inspector; the status bar stays under both */}
      <div className="shell-stage">
      <TopBar
        can={can}
        pins={pins}
        onTogglePin={togglePin}
        activeId={activePage}
        onOpenSearch={() => setCommandPaletteOpen(true)}
        onOpenHelp={openHelp}
        hasHelp={hasHelp}
      />

      <div className={`shell-main${dockPlacement === 'right' ? ' has-dock-right' : ''}`}>
        <div className="shell-content">
          <div className="flex-1 flex min-h-0 min-w-0 overflow-auto">
            <Outlet />
          </div>
        </div>
        <InspectorDock />
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

      {/* Ko-fi support card, once per version for admins; the overview shows it in its own flow */}
      {!onOverview && <KofiSupportCard />}
    </div>
  )
}
