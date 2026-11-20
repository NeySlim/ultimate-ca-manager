/**
 * AppShell Component - Atelier layout: top bar, page, status bar
 */
import { Suspense, useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation } from 'react-router-dom'
import { LoadingSpinner } from './LoadingSpinner'
import { TopBar } from './shell/TopBar'
import { StatusBar } from './shell/StatusBar'
import { StateBanners } from './shell/StateBanners'
import { NodesDialog } from './shell/NodesDialog'
import { haState, useHealth, useWriteGuard } from './shell/health'
import { useCentralWriteGuard } from './shell/writeGuard'
import { moduleById } from '../navigation/registry'
import { usePins } from './shell/pins'
import { resolveActivePageId } from './shell/activePage'
import { CommandPalette, useKeyboardShortcuts } from './CommandPalette'
import { FloatingHelpPanel } from './ui/FloatingHelpPanel'
import { UpdatePopup } from './UpdatePopup'
import { KofiSupportCard } from './KofiSupportCard'
import { usePermission } from '../hooks'
import { useNotification } from '../contexts/NotificationContext'
import { InspectorDock } from './inspector/InspectorDock'
import { useDockPlacement } from './inspector/placement'

export function AppShell() {
  const { t } = useTranslation()
  const location = useLocation()
  const { isAdmin, hasPermission } = usePermission()
  const can = { isAdmin, hasPermission }
  const { pins, toggle: togglePin } = usePins(can)
  // The shell's own messages (refused pin, network back), in the app's message area
  const messages = useNotification()
  const notice = (text) => messages?.showInfo?.(text)
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [helpModalOpen, setHelpModalOpen] = useState(false)
  // Help key requested by the shell itself (navigation help); cleared on close
  const [helpOverride, setHelpOverride] = useState(null)
  // The inspector sits in the page flow: under the page, or beside it on the right
  const dockPlacement = useDockPlacement()
  // Cluster nodes, read from the service status (read:settings), from the bar or the HA banner
  const [nodesOpen, setNodesOpen] = useState(false)
  const ha = haState(useHealth())
  const showNodes = hasPermission('read:settings') ? () => setNodesOpen(true) : undefined
  // Offline or in maintenance, every write control of every page waits, pointing to the banner
  useCentralWriteGuard(useWriteGuard())

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

  // The tab names the page; the browser chrome takes the theme's background
  const pageModule = moduleById(activePage === '' ? 'dashboard' : activePage)
  const pageName = pageModule ? t(pageModule.barKey || pageModule.labelKey) : ''
  useEffect(() => {
    document.title = pageName ? `${pageName} · UCM` : 'UCM'
  }, [pageName])
  useEffect(() => {
    const root = document.documentElement
    const paint = () => {
      let meta = document.querySelector('meta[name="theme-color"]')
      if (!meta) {
        meta = document.createElement('meta')
        meta.name = 'theme-color'
        document.head.appendChild(meta)
      }
      const bg = getComputedStyle(root).getPropertyValue('--bg').trim()
      if (bg) meta.content = bg
    }
    paint()
    const observer = new MutationObserver(paint)
    observer.observe(root, { attributes: true, attributeFilter: ['data-theme', 'data-mode'] })
    return () => observer.disconnect()
  }, [])

  // Closing the palette gives the focus back to the search button when nothing else took it
  const setPalette = (open) => {
    setCommandPaletteOpen(open)
    if (!open) {
      setTimeout(() => {
        const active = document.activeElement
        if (!active || active === document.body) document.getElementById('shell-search')?.focus()
      }, 0)
    }
  }

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
      <a className="shell-skip" href="#shell-page" onClick={(e) => { e.preventDefault(); document.getElementById('shell-page')?.focus() }}>
        {t('shell.skipToContent')}
      </a>
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
        onNotice={notice}
      />

      <div className={`shell-main${dockPlacement === 'right' ? ' has-dock-right' : ''}`}>
        <div className="shell-content">
          <StateBanners onShowNodes={showNodes} onNotice={notice} />
          <div className="shell-page" id="shell-page" tabIndex={-1}>
            {/* A page whose code is still loading waits here: the bars stay on screen */}
            <Suspense fallback={<div className="shell-page-wait" role="status" aria-label={t('common.loading')}><LoadingSpinner size="lg" /></div>}>
              <Outlet />
            </Suspense>
          </div>
        </div>
        <InspectorDock />
      </div>
      </div>

      <StatusBar onShowNodes={showNodes} can={can} />
      {showNodes && <NodesDialog open={nodesOpen} onClose={() => setNodesOpen(false)} ha={ha} />}

      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={setPalette}
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
