/**
 * The console's frame, the mockup's render(): masthead, session banner and notification panel,
 * the stage (the page and its banners; a zone draws its own dock), the status bar. The shell's own parts are
 * drawn under .atl (atl-island: no box of its own); the page slot is not, a page brings its own.
 */
import { Suspense, useState, useEffect, useCallback } from 'react'
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
import { HelpDialog } from './shell/HelpDialog'
import { guideHref } from '../navigation/guide'
import { UpdatePopup } from './UpdatePopup'
import { KofiSupportCard } from './KofiSupportCard'
import { usePermission } from '../hooks'
import { useNotification } from '../contexts/NotificationContext'
import { useThemeColor } from '../lib/themeColor'
import { BANNER_SLOT } from '../lib/sessionBannerSlot'
import { NOTIF_SLOT } from './shell/NotificationBell'
import { ShellBannersContext } from './shell/bannersSlot'
import { usePanel, openedPanel } from './shell/openPanel'

export function AppShell() {
  const { t } = useTranslation()
  const location = useLocation()
  const { isAdmin, hasPermission } = usePermission()
  const can = { isAdmin, hasPermission }
  const { pins, toggle: togglePin } = usePins(can)
  // The shell's own messages (refused pin, network back), in the app's message area
  const messages = useNotification()
  const notice = (text) => messages?.showInfo?.(text)
  // The palette and the help are panels of the shell: opening one closes the bar's menu or panel open
  const [commandPaletteOpen, setCommandPaletteOpen] = usePanel('palette')
  // The help asked: { key } requested by the shell itself (navigation help, else the page's), { returnTo } the
  // id that takes the focus back
  const [helpOpen, setHelpOpen] = usePanel('help')
  const [helpAsk, setHelpAsk] = useState({})
  const help = helpOpen ? helpAsk : null
  const setHelp = useCallback((ask) => { if (ask) setHelpAsk(ask); setHelpOpen(!!ask) }, [setHelpOpen])
  // Cluster nodes, read from the service status (read:settings), from the bar or the HA banner
  const [nodesOpen, setNodesOpen] = useState(false)
  const ha = haState(useHealth())
  const showNodes = hasPermission('read:settings') ? () => setNodesOpen(true) : undefined
  // Offline or in maintenance, every write control of every page waits, pointing to the banner
  useCentralWriteGuard(useWriteGuard())
  // A zone drawn from the mockup shows the banners in its page content and claims them
  const [claims, setClaims] = useState(0)
  const claim = useCallback(() => { setClaims(c => c + 1); return () => setClaims(c => c - 1) }, [])
  const bannerNode = <StateBanners onShowNodes={showNodes} onNotice={notice} />
  const banners = { claim, node: bannerNode }

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
  useThemeColor()

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
        setHelp(openedPanel() === 'help' ? null : {})
      }
    }
    window.addEventListener('keydown', handleHelpKey)
    return () => window.removeEventListener('keydown', handleHelpKey)
  }, [setHelp])

  const openHelp = (key, returnTo) => setHelp({ key: typeof key === 'string' ? key : null, returnTo })

  const skipToPage = (e) => {
    e.preventDefault()
    ;(document.getElementById('main') || document.getElementById('shell-page'))?.focus()
  }

  return (
    <ShellBannersContext.Provider value={banners}>
    <div className="shell-app">
      <div className="atl atl-island">
        <a className="skip" href="#main" onClick={skipToPage}>{t('shell.skipToContent')}</a>
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
        {/* The session expiry banner and the notification panel follow the bar, in the tab order too */}
        <div id={BANNER_SLOT} style={{ display: 'contents' }} />
        <div id={NOTIF_SLOT} style={{ display: 'contents' }} />
      </div>

      <div className="shell-main">
        <div className="shell-content">
          {claims === 0 && <div className="atl atl-island"><div className="stage shell-banners">{bannerNode}</div></div>}
          <div className="shell-page" id="shell-page" tabIndex={-1}>
            {/* A page whose code is still loading waits here, the bars on screen. One boundary per page:
                a navigation (a transition) then shows the wait and the link asked for at once */}
            <Suspense key={activePage} fallback={<div className="shell-page-wait" role="status" aria-label={t('common.loading')}><LoadingSpinner size="lg" /></div>}>
              <Outlet />
            </Suspense>
          </div>
        </div>
      </div>

      <div className="atl atl-island"><StatusBar onShowNodes={showNodes} can={can} /></div>
      {showNodes && <NodesDialog open={nodesOpen} onClose={() => setNodesOpen(false)} ha={ha} />}

      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={setPalette}
        can={can}
        onOpenHelp={hasHelp ? () => openHelp(null, 'shell-search') : undefined}
        guideHref={guideHref(helpPageKey)}
      />

      {/* The help of the page, the mockup's help dialog */}
      <HelpDialog
        open={!!help}
        onClose={() => setHelp(null)}
        pageKey={help?.key || helpPageKey}
        returnTo={help?.returnTo}
      />

      {/* Optional what's-new window after an update (#308) */}
      <UpdatePopup />

      {/* Ko-fi support card, once per version for admins; the overview shows it in its own flow */}
      {!onOverview && <KofiSupportCard />}
    </div>
    </ShellBannersContext.Provider>
  )
}
