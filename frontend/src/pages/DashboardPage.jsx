/**
 * Dashboard Page - Live Operational Dashboard with WebSocket
 * Real-time updates via WebSocket events
 * Draggable grid layout with react-grid-layout
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { 
  ShieldCheck, Certificate, ClockCounterClockwise, Clock,
  Plus, ArrowsClockwise, ListChecks, Gear, CaretRight, 
  User, Globe, SignIn, SignOut, Trash, PencilSimple, 
  UploadSimple, Key, Warning, WifiHigh, Heartbeat, Database, Lightning,
  SlidersHorizontal, Eye, EyeSlash, X, DotsSixVertical,
  PencilSimpleLine, ArrowCounterClockwise, Timer, Check
} from '@phosphor-icons/react'
import { Responsive } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import { Card, Button, Badge, LoadingSpinner, Modal, Logo } from '../components'
import { CertificateTrendChart, StatusPieChart } from '../components/DashboardChart'
import { dashboardService, certificatesService, acmeService, truststoreService } from '../services'
import { useNotification } from '../contexts'
import { useWebSocket, EventType } from '../hooks'
import { formatRelativeTime } from '../lib/ui'

// Default widgets configuration
const DEFAULT_WIDGETS = [
  { id: 'stats', nameKey: 'dashboard.widgetStatistics', visible: true },
  { id: 'chartTrend', nameKey: 'dashboard.widgetCertificateActivity', visible: true },
  { id: 'chartPie', nameKey: 'dashboard.widgetStatusDistribution', visible: true },
  { id: 'nextExpiry', nameKey: 'dashboard.widgetNextExpirations', visible: true },
  { id: 'system', nameKey: 'dashboard.widgetSystemStatus', visible: true },
  { id: 'activity', nameKey: 'dashboard.widgetRecentActivity', visible: true },
  { id: 'certs', nameKey: 'dashboard.widgetRecentCertificates', visible: true },
  { id: 'cas', nameKey: 'dashboard.widgetCertificateAuthorities', visible: true },
  { id: 'acme', nameKey: 'dashboard.widgetAcmeAccounts', visible: true },
  { id: 'trustExpiry', nameKey: 'dashboard.widgetTrustStoreExpiry', visible: true },
]

// Default grid layouts per breakpoint (12-column grid)
const DEFAULT_LAYOUTS = {
  lg: [
    { i: 'stats',      x: 0,  y: 0, w: 12, h: 2, static: true },
    { i: 'chartTrend', x: 0,  y: 2, w: 5,  h: 5, minW: 3, minH: 4 },
    { i: 'chartPie',   x: 5,  y: 2, w: 4,  h: 5, minW: 3, minH: 4 },
    { i: 'nextExpiry', x: 9,  y: 2, w: 3,  h: 5, minW: 3, minH: 3 },
    { i: 'certs',      x: 0,  y: 7, w: 4,  h: 4, minW: 3, minH: 3 },
    { i: 'cas',        x: 4,  y: 7, w: 4,  h: 4, minW: 3, minH: 3 },
    { i: 'activity',   x: 8,  y: 7, w: 4,  h: 4, minW: 3, minH: 3 },
    { i: 'system',     x: 0,  y: 11, w: 4,  h: 4, minW: 3, minH: 3 },
    { i: 'acme',       x: 4,  y: 11, w: 4,  h: 4, minW: 3, minH: 3 },
    { i: 'trustExpiry',x: 8,  y: 11, w: 4,  h: 4, minW: 3, minH: 3 },
  ],
  md: [
    { i: 'stats',      x: 0, y: 0, w: 6, h: 3, static: true },
    { i: 'chartTrend', x: 0, y: 3, w: 6, h: 5, minW: 3, minH: 4 },
    { i: 'chartPie',   x: 0, y: 8, w: 3, h: 5, minW: 3, minH: 4 },
    { i: 'nextExpiry', x: 3, y: 8, w: 3, h: 5, minW: 3, minH: 3 },
    { i: 'certs',      x: 0, y: 13, w: 3, h: 5, minW: 3, minH: 3 },
    { i: 'cas',        x: 3, y: 13, w: 3, h: 5, minW: 3, minH: 3 },
    { i: 'activity',   x: 0, y: 18, w: 6, h: 5, minW: 3, minH: 3 },
    { i: 'system',     x: 0, y: 23, w: 6, h: 6, minW: 3, minH: 4 },
    { i: 'acme',       x: 0, y: 29, w: 3, h: 4, minW: 3, minH: 3 },
    { i: 'trustExpiry',x: 3, y: 29, w: 3, h: 4, minW: 3, minH: 3 },
  ],
  sm: [
    { i: 'stats',      x: 0, y: 0, w: 1, h: 3, static: true },
    { i: 'chartTrend', x: 0, y: 3, w: 1, h: 5 },
    { i: 'chartPie',   x: 0, y: 8, w: 1, h: 5 },
    { i: 'nextExpiry', x: 0, y: 13, w: 1, h: 5 },
    { i: 'certs',      x: 0, y: 18, w: 1, h: 5 },
    { i: 'cas',        x: 0, y: 23, w: 1, h: 4 },
    { i: 'activity',   x: 0, y: 27, w: 1, h: 5 },
    { i: 'system',     x: 0, y: 32, w: 1, h: 6 },
    { i: 'acme',       x: 0, y: 38, w: 1, h: 4 },
    { i: 'trustExpiry',x: 0, y: 42, w: 1, h: 4 },
  ]
}

// Load widget preferences from localStorage
const loadWidgetPrefs = () => {
  try {
    const saved = localStorage.getItem('ucm-dashboard-widgets-v2')
    if (saved) {
      const parsed = JSON.parse(saved)
      return DEFAULT_WIDGETS.map(w => ({
        ...w,
        visible: parsed.find(p => p.id === w.id)?.visible ?? w.visible,
      }))
    }
  } catch {}
  return DEFAULT_WIDGETS
}

const saveWidgetPrefs = (widgets) => {
  localStorage.setItem('ucm-dashboard-widgets-v2', JSON.stringify(widgets.map(w => ({ id: w.id, visible: w.visible }))))
}

// Load grid layout from localStorage
const LAYOUT_STORAGE_KEY = 'ucm-dashboard-layouts-v2'
// Strip per-item isDraggable/isResizable to prevent layout items from overriding global props
const cleanLayoutFlags = (layouts) => {
  const clean = {}
  for (const bp of Object.keys(layouts)) {
    if (Array.isArray(layouts[bp])) {
      clean[bp] = layouts[bp].map(({ isDraggable, isResizable, moved, ...rest }) => rest)
    } else {
      clean[bp] = layouts[bp]
    }
  }
  return clean
}
const loadGridLayouts = () => {
  try {
    const saved = localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      // Validate that all default widget IDs exist in saved layouts
      const defaultIds = new Set(DEFAULT_LAYOUTS.lg.map(l => l.i))
      const savedIds = new Set((parsed.lg || []).map(l => l.i))
      const allPresent = [...defaultIds].every(id => savedIds.has(id))
      if (allPresent) return cleanLayoutFlags(parsed)
    }
  } catch {}
  return DEFAULT_LAYOUTS
}

const saveGridLayouts = (layouts) => {
  localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(cleanLayoutFlags(layouts)))
}

// Action icons mapping
const actionIcons = {
  login_success: SignIn,
  login_failed: SignIn,
  logout: SignOut,
  create: Plus,
  update: PencilSimple,
  delete: Trash,
  revoke: ClockCounterClockwise,
  export: UploadSimple,
  import: UploadSimple,
  sign: Key,
  default: ClockCounterClockwise
}

export default function DashboardPage() {
  const { t } = useTranslation()
  const { showError } = useNotification()
  const navigate = useNavigate()
  
  const [stats, setStats] = useState(null)
  const [recentCerts, setRecentCerts] = useState([])
  const [recentCAs, setRecentCAs] = useState([])
  const [recentAcme, setRecentAcme] = useState([])
  const [trustStoreExpiring, setTrustStoreExpiring] = useState({ expiring: [], expired: [], expiring_count: 0, expired_count: 0 })
  const [activityLog, setActivityLog] = useState([])
  const [systemStatus, setSystemStatus] = useState(null)
  const [nextExpirations, setNextExpirations] = useState([])
  const [certificateTrend, setCertificateTrend] = useState([])
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState(new Date())
  const [versionInfo, setVersionInfo] = useState({ version: '2.0.0', update_available: false })
  
  // Widget + layout customization
  const [widgets, setWidgets] = useState(loadWidgetPrefs)
  const [showWidgetSettings, setShowWidgetSettings] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [gridLayouts, setGridLayouts] = useState(loadGridLayouts)
  const [gridKey, setGridKey] = useState(0) // Force re-mount on reset
  const refreshTimeoutRef = useRef(null)

  // Grid layout measurement — single ResizeObserver for both width and height
  const GRID_ROWS_LG = 15
  const GRID_MARGIN = 10
  const FIXED_ROW_HEIGHT = 40
  const [gridWidth, setGridWidth] = useState(1280)
  const [dynamicRowHeight, setDynamicRowHeight] = useState(FIXED_ROW_HEIGHT)
  const [currentBreakpoint, setCurrentBreakpoint] = useState(() => {
    const w = typeof window !== 'undefined' ? window.innerWidth : 1280
    if (w >= 1024) return 'lg'
    if (w >= 640) return 'md'
    return 'sm'
  })
  const [gridMounted, setGridMounted] = useState(false)
  const gridObserverRef = useRef(null)
  
  const isDesktopGrid = currentBreakpoint === 'lg'

  // Keep breakpoint in sync with window size (needed when RGL is not rendered)
  useEffect(() => {
    const onResize = () => {
      const w = window.innerWidth
      const bp = w >= 1024 ? 'lg' : w >= 640 ? 'md' : 'sm'
      setCurrentBreakpoint(prev => prev !== bp ? bp : prev)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  
  const gridContainerRef = useCallback((el) => {
    // Clean up previous observer
    if (gridObserverRef.current) {
      gridObserverRef.current.disconnect()
      gridObserverRef.current = null
    }
    
    if (!el) return
    
    // Measure immediately
    const w = el.offsetWidth
    const h = el.offsetHeight
    if (w > 0) setGridWidth(w)
    if (w >= 1024 && h > 0) {
      const totalGaps = (GRID_ROWS_LG - 1) * GRID_MARGIN
      const rh = Math.floor((h - totalGaps) / GRID_ROWS_LG)
      setDynamicRowHeight(Math.max(20, Math.min(rh, 80)))
    }
    setGridMounted(true)
    
    const observer = new ResizeObserver((entries) => {
      const { width: ow, height: oh } = entries[0].contentRect
      if (ow > 0) setGridWidth(ow)
      if (ow >= 1024 && oh > 0) {
        const totalGaps = (GRID_ROWS_LG - 1) * GRID_MARGIN
        const rh = Math.floor((oh - totalGaps) / GRID_ROWS_LG)
        setDynamicRowHeight(Math.max(20, Math.min(rh, 80)))
      } else {
        setDynamicRowHeight(FIXED_ROW_HEIGHT)
      }
    })
    observer.observe(el)
    gridObserverRef.current = observer
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // WebSocket for live updates
  const { isConnected, subscribe } = useWebSocket({ showToasts: true })

  const loadDashboard = useCallback(async () => {
    try {
      const [statsData, casData, certsData, activityData, statusData, trendData] = await Promise.all([
        dashboardService.getStats(),
        dashboardService.getRecentCAs(5),
        certificatesService.getAll({ limit: 5, sort: 'created_at', order: 'desc' }),
        dashboardService.getActivityLog(10),
        dashboardService.getSystemStatus(),
        dashboardService.getCertificateTrend(7),
      ])
      
      setStats(statsData.data || {})
      setRecentCAs(casData.data || [])
      setRecentCerts(certsData.data?.certificates || certsData.data || [])
      setActivityLog(activityData.data?.activity || [])
      setSystemStatus(statusData.data || {})
      setCertificateTrend(trendData.data?.trend || [])
      setLastUpdate(new Date())
      
      // Get next expirations (up to 365 days)
      try {
        const expiringData = await dashboardService.getNextExpirations(6)
        setNextExpirations(expiringData.data || [])
      } catch {
        setNextExpirations([])
      }
      
      // Try to get ACME accounts
      try {
        const acmeData = await acmeService.getAccounts()
        setRecentAcme(acmeData.data?.slice(0, 5) || [])
      } catch {
        setRecentAcme([])
      }
      
      // Try to get trust store expiring certs
      try {
        const tsData = await truststoreService.getExpiring(90)
        setTrustStoreExpiring(tsData.data || { expiring: [], expired: [], expiring_count: 0, expired_count: 0 })
      } catch {
        setTrustStoreExpiring({ expiring: [], expired: [], expiring_count: 0, expired_count: 0 })
      }
    } catch (error) {
      showError(error.message || t('dashboard.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  // Load version info
  useEffect(() => {
    const loadVersion = async () => {
      try {
        const response = await fetch('/api/v2/system/updates/version')
        if (response.ok) {
          const data = await response.json()
          setVersionInfo(data.data || { version: '2.0.0', update_available: false })
        }
      } catch {}
    }
    loadVersion()
  }, [])

  // Subscribe to PKI events for auto-refresh
  useEffect(() => {
    if (!isConnected) return
    
    const debouncedRefresh = () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current)
      }
      refreshTimeoutRef.current = setTimeout(() => {
        loadDashboard()
      }, 1000)
    }
    
    const unsub1 = subscribe(EventType.CERTIFICATE_ISSUED, debouncedRefresh)
    const unsub2 = subscribe(EventType.CERTIFICATE_REVOKED, debouncedRefresh)
    const unsub3 = subscribe(EventType.CA_CREATED, debouncedRefresh)
    
    const unsub4 = subscribe(EventType.USER_LOGIN, (data) => {
      setActivityLog(prev => [{
        id: Date.now(),
        action: 'login_success',
        message: `Password login successful for ${data.username}`,
        user: data.username,
        timestamp: new Date().toISOString()
      }, ...prev.slice(0, 9)])
    })
    
    return () => {
      unsub1?.()
      unsub2?.()
      unsub3?.()
      unsub4?.()
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current)
      }
    }
  }, [isConnected, subscribe, loadDashboard])

  // Layout change handler
  const handleLayoutChange = useCallback((layout, allLayouts) => {
    if (editMode) {
      setGridLayouts(allLayouts)
      saveGridLayouts(allLayouts)
    }
  }, [editMode])

  const resetLayout = useCallback(() => {
    setGridLayouts(DEFAULT_LAYOUTS)
    saveGridLayouts(DEFAULT_LAYOUTS)
    setGridKey(k => k + 1)
  }, [])

  // Filter layouts to only include visible widgets
  const visibleLayouts = useMemo(() => {
    const visibleIds = new Set(widgets.filter(w => w.visible).map(w => w.id))
    const filtered = {}
    for (const [bp, items] of Object.entries(gridLayouts)) {
      filtered[bp] = items.filter(item => visibleIds.has(item.i))
    }
    return filtered
  }, [gridLayouts, widgets])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner message={t('dashboard.loading')} />
      </div>
    )
  }

  const totalCerts = stats?.total_certificates || 0
  const totalCAs = stats?.total_cas || 0
  const pendingCSRs = stats?.pending_csrs || 0
  const acmeAccounts = recentAcme.length
  const expiringCount = stats?.expiring_soon || 0

  // Build widget map for rendering
  const isVisible = (id) => widgets.find(w => w.id === id)?.visible

  return (
    <div className={`flex flex-col bg-bg-primary ${isDesktopGrid ? 'flex-1 h-full overflow-hidden' : 'min-h-full'}`}>
      <div className={`flex flex-col px-3 pt-2 pb-1 mx-auto w-full ${isDesktopGrid ? 'flex-1 min-h-0' : 'pb-6'}`}>
        
        {/* Dashboard Header */}
        <div className="shrink-0 relative overflow-hidden rounded-lg hero-gradient border border-accent-primary/20 px-4 py-3 mb-1.5">
          <div className="relative flex items-center justify-between gap-4">
            {/* Branding */}
            <div className="flex items-center gap-3">
              <Logo variant="icon" size="md" />
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-lg font-black tracking-tight logo-text-gradient">UCM</span>
                  <span className="text-xs text-text-tertiary">v{versionInfo.version}</span>
                  {versionInfo.update_available && (
                    <Badge variant="warning" size="sm" dot>{t('common.updateAvailable')}</Badge>
                  )}
                </div>
                <p className="text-xs text-text-tertiary mt-0.5">Ultimate Certificate Manager</p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2">
              {!editMode ? (
                <>
                  <Button size="sm" onClick={() => navigate('/certificates?action=create')}>
                    <Plus size={14} weight="bold" />
                    {t('common.cert')}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => navigate('/cas?action=create')}>
                    <Plus size={14} weight="bold" />
                    {t('common.ca')}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => navigate('/csrs')} className="hidden md:flex">
                    <ListChecks size={14} weight="bold" />
                    {t('common.csr')}
                  </Button>
                  <div className="hidden md:flex items-center gap-1 ml-1 border-l border-border/40 pl-2">
                    <Button size="sm" variant="ghost" onClick={loadDashboard} title={t('common.refresh')}>
                      <ArrowsClockwise size={14} />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowWidgetSettings(true)} title={t('dashboard.customizeDashboard')}>
                      <SlidersHorizontal size={14} />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditMode(true)} title={t('dashboard.editLayout')}>
                      <PencilSimpleLine size={14} />
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <Button size="sm" variant="ghost" onClick={resetLayout}>
                    <ArrowCounterClockwise size={14} />
                    {t('dashboard.resetLayout')}
                  </Button>
                  <Button size="sm" onClick={() => setEditMode(false)}>
                    <Check size={14} weight="bold" />
                    {t('dashboard.doneEditing')}
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Edit mode indicator */}
          {editMode && (
            <div className="mt-2 flex items-center gap-2 text-xs text-accent-primary">
              <DotsSixVertical size={14} />
              {t('dashboard.dragToReorder')}
            </div>
          )}
        </div>

        {/* Grid Layout — flex-1 fills remaining space on desktop, natural flow on mobile */}
        <div ref={gridContainerRef} className={isDesktopGrid ? 'flex-1 min-h-0' : ''}>
        {gridMounted && isDesktopGrid && (
        <Responsive
          key={gridKey}
          className={`dashboard-grid ${editMode ? 'edit-mode' : ''}`}
          layouts={visibleLayouts}
          breakpoints={{ lg: 1024, md: 640, sm: 0 }}
          cols={{ lg: 12, md: 6, sm: 1 }}
          width={gridWidth}
          rowHeight={dynamicRowHeight}
          margin={[GRID_MARGIN, GRID_MARGIN]}
          containerPadding={[0, 0]}
          onBreakpointChange={(bp) => setCurrentBreakpoint(bp)}
          dragConfig={{ enabled: editMode, handle: editMode ? '.widget-drag-handle' : undefined }}
          resizeConfig={{ enabled: editMode }}
          compactType="vertical"
          onLayoutChange={handleLayoutChange}
        >
          {/* Stats Widget */}
          {isVisible('stats') && (
          <div key="stats">
            <div className="grid grid-cols-4 gap-1.5 sm:gap-3 h-full">
              <StatCard 
                icon={Certificate}
                label={t('common.certificates')}
                value={totalCerts}
                color="blue"
                live={isConnected}
                onClick={() => navigate('/certificates')}
              />
              <StatCard 
                icon={ShieldCheck}
                label={t('common.cas')}
                value={totalCAs}
                color="purple"
                live={isConnected}
                onClick={() => navigate('/cas')}
              />
              <StatCard 
                icon={ListChecks}
                label={t('common.csrs')}
                value={pendingCSRs}
                color={pendingCSRs > 0 ? 'yellow' : 'slate'}
                badge={pendingCSRs > 0 ? t('common.pending') : null}
                onClick={() => navigate('/csrs')}
              />
              <StatCard 
                icon={Globe}
                label={t('common.acme')}
                value={acmeAccounts}
                color="emerald"
                onClick={() => navigate('/acme')}
              />
            </div>
          </div>
          )}

          {/* Certificate Activity Chart */}
          {isVisible('chartTrend') && (
          <div key="chartTrend">
            <WidgetWrapper editMode={editMode}>
              <Card variant="elevated" className="h-full flex flex-col p-0">
                <Card.Header 
                  icon={Lightning}
                  iconColor="amber"
                  title={t('dashboard.certificateActivity')}
                  subtitle={t('dashboard.last7Days')}
                />
                <Card.Body className="flex-1 min-h-0 relative !pt-0 !pb-0 !px-2">
                  <div className="absolute inset-0 px-2">
                    <CertificateTrendChart data={certificateTrend} />
                  </div>
                </Card.Body>
              </Card>
            </WidgetWrapper>
          </div>
          )}

          {/* Status Distribution Chart */}
          {isVisible('chartPie') && (
          <div key="chartPie">
            <WidgetWrapper editMode={editMode}>
              <Card variant="elevated" className="h-full flex flex-col p-0">
                <Card.Header 
                  icon={Certificate}
                  iconColor="violet"
                  title={t('dashboard.statusDistribution')}
                  subtitle={t('dashboard.currentCertificates')}
                />
                <Card.Body className="flex-1 min-h-0 relative !pt-0 !pb-0 !px-2">
                  <div className="absolute inset-0 px-2 flex items-center">
                    <StatusPieChart 
                      data={{
                        valid: Math.max(0, totalCerts - (stats?.expiring_soon || 0) - (stats?.revoked || 0)),
                        expiring: stats?.expiring_soon || 0,
                        expired: 0,
                        revoked: stats?.revoked || 0,
                      }}
                    />
                  </div>
                </Card.Body>
              </Card>
            </WidgetWrapper>
          </div>
          )}

          {/* Next Expirations Widget */}
          {isVisible('nextExpiry') && (
          <div key="nextExpiry">
            <WidgetWrapper editMode={editMode}>
              <Card variant="elevated" className="h-full flex flex-col p-0">
                <Card.Header 
                  icon={Timer}
                  iconColor="orange"
                  title={t('dashboard.nextExpirations')}
                  action={
                    expiringCount > 0 ? (
                      <Badge variant="warning" size="sm" dot>{expiringCount}</Badge>
                    ) : null
                  }
                />
                <Card.Body className="flex-1 overflow-y-auto !pt-0 !pb-2">
                  {nextExpirations.length === 0 ? (
                    <EmptyWidget icon={Timer} text={t('dashboard.noExpirations')} />
                  ) : (
                    <div className="space-y-1">
                      {nextExpirations.slice(0, 6).map((cert, i) => {
                        const daysLeft = cert.valid_to 
                          ? Math.max(0, Math.ceil((new Date(cert.valid_to) - new Date()) / (1000 * 60 * 60 * 24)))
                          : null
                        const totalLifespan = (cert.valid_from && cert.valid_to)
                          ? Math.max(1, Math.ceil((new Date(cert.valid_to) - new Date(cert.valid_from)) / (1000 * 60 * 60 * 24)))
                          : 365
                        const progress = daysLeft !== null ? Math.min(100, (daysLeft / totalLifespan) * 100) : 0
                        const urgency = daysLeft === null ? 'gray' 
                          : daysLeft <= 7 ? 'danger' 
                          : daysLeft <= 15 ? 'warning' 
                          : daysLeft <= 30 ? 'yellow' 
                          : 'success'
                        const barColor = {
                          danger: 'var(--accent-danger)',
                          warning: 'var(--accent-warning)', 
                          yellow: '#EAB308',
                          success: 'var(--accent-success)',
                          gray: 'var(--text-tertiary)'
                        }[urgency]
                        
                        return (
                          <div 
                            key={cert.id || i}
                            onClick={() => navigate(`/certificates/${cert.id}`)}
                            className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors group"
                          >
                            <div className="flex items-center justify-between gap-2 mb-1">
                              <span className="text-xs font-medium text-text-primary truncate flex-1 group-hover:text-accent-primary transition-colors">
                                {cert.common_name || cert.descr || cert.subject || '—'}
                              </span>
                              <span className={`text-[10px] font-semibold whitespace-nowrap ${
                                urgency === 'danger' ? 'status-danger-text' 
                                : urgency === 'warning' ? 'status-warning-text' 
                                : 'text-text-secondary'
                              }`}>
                                {daysLeft !== null ? t('dashboard.daysRemaining', { count: daysLeft }) : '—'}
                              </span>
                            </div>
                            <div className="h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
                              <div 
                                className="h-full rounded-full transition-all duration-500"
                                style={{ 
                                  width: `${Math.max(3, progress)}%`,
                                  backgroundColor: barColor
                                }}
                              />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </Card.Body>
              </Card>
            </WidgetWrapper>
          </div>
          )}

          {/* Recent Certificates */}
          {isVisible('certs') && (
          <div key="certs">
            <WidgetWrapper editMode={editMode}>
              <Card variant="elevated" className="h-full flex flex-col p-0">
                <Card.Header 
                  icon={Certificate}
                  iconColor="blue"
                  title={t('dashboard.recentCertificates')}
                  action={
                    <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/certificates')}>
                      {t('common.viewAll')} <CaretRight size={12} />
                    </Button>
                  }
                />
                <Card.Body className="flex-1 overflow-y-auto space-y-0.5 !pt-0">
                  {recentCerts.length === 0 ? (
                    <EmptyWidget icon={Certificate} text={t('dashboard.noCertificatesYet')} />
                  ) : (
                    recentCerts.slice(0, 4).map((cert, i) => (
                      <div 
                        key={cert.id || i}
                        onClick={() => navigate(`/certificates/${cert.id}`)}
                        className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-all group flex items-center gap-2.5"
                      >
                        <div className="w-7 h-7 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0 group-hover:bg-accent-primary/10 transition-colors">
                          <Certificate size={14} weight="duotone" className="text-text-tertiary group-hover:text-accent-primary transition-colors" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-medium text-text-primary truncate group-hover:text-accent-primary transition-colors">
                              {cert.common_name || cert.descr || cert.subject || t('common.certificate')}
                            </span>
                            <Badge variant={cert.revoked ? 'danger' : (cert.valid_to && new Date(cert.valid_to) < new Date()) ? 'warning' : 'success'} size="sm" dot>
                              {cert.revoked ? t('common.revoked') : (cert.valid_to && new Date(cert.valid_to) < new Date()) ? t('common.expired') : t('common.valid')}
                            </Badge>
                          </div>
                          <div className="text-[10px] text-text-tertiary mt-0.5">
                            {formatRelativeTime(cert.created_at, t)}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </Card.Body>
              </Card>
            </WidgetWrapper>
          </div>
          )}

          {/* Recent CAs */}
          {isVisible('cas') && (
          <div key="cas">
            <WidgetWrapper editMode={editMode}>
              <Card variant="elevated" className="h-full flex flex-col p-0">
                <Card.Header 
                  icon={ShieldCheck}
                  iconColor="emerald"
                  title={t('dashboard.recentCAs')}
                  action={
                    <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/cas')}>
                      {t('common.viewAll')} <CaretRight size={12} />
                    </Button>
                  }
                />
                <Card.Body className="flex-1 overflow-y-auto space-y-0.5 !pt-0">
                  {recentCAs.length === 0 ? (
                    <EmptyWidget icon={ShieldCheck} text={t('dashboard.noCAsYet')} />
                  ) : (
                    recentCAs.slice(0, 4).map((ca, i) => (
                      <div 
                        key={ca.id || i}
                        onClick={() => navigate(`/cas/${ca.id}`)}
                        className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors group flex items-center gap-2.5"
                      >
                        <div className="w-7 h-7 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0 group-hover:bg-accent-primary/10 transition-colors">
                          <ShieldCheck size={14} weight="duotone" className="text-text-tertiary group-hover:text-accent-primary transition-colors" />
                        </div>
                        <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-text-primary truncate group-hover:text-accent-primary transition-colors">
                            {ca.dn_commonname || ca.descr || ca.name}
                          </span>
                          <Badge variant={ca.is_root ? 'purple' : 'info'} size="sm">
                            {ca.is_root ? t('common.root') : t('dashboard.sub')}
                          </Badge>
                        </div>
                      </div>
                    ))
                  )}
                </Card.Body>
              </Card>
            </WidgetWrapper>
          </div>
          )}

          {/* Recent Activity */}
          {isVisible('activity') && (
          <div key="activity">
            <WidgetWrapper editMode={editMode}>
              <Card variant="elevated" className="h-full flex flex-col p-0">
                <Card.Header 
                  icon={ClockCounterClockwise}
                  iconColor="teal"
                  title={t('dashboard.recentActivity')}
                  subtitle={isConnected ? t('dashboard.liveUpdates') : undefined}
                  action={
                    <div className="flex items-center gap-2">
                      {isConnected && (
                        <Badge variant="success" size="sm" dot pulse>{t('common.live')}</Badge>
                      )}
                      <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/audit')}>
                        {t('common.viewAll')} <CaretRight size={12} />
                      </Button>
                    </div>
                  }
                />
                <Card.Body className="flex-1 overflow-y-auto !pt-0">
                  {activityLog.length === 0 ? (
                    <EmptyWidget icon={ClockCounterClockwise} text={t('dashboard.noRecentActivity')} />
                  ) : (
                    <div className="space-y-0.5">
                      {activityLog.map((activity, i) => {
                        const Icon = actionIcons[activity.action] || actionIcons.default
                        const isError = activity.action === 'login_failed' || activity.action === 'revoke'
                        const isSuccess = activity.action === 'login_success' || activity.action === 'create'
                        
                        return (
                          <div key={activity.id || i} className="p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors flex items-start gap-2.5">
                            <div className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 mt-0.5 ${
                              isError ? 'status-danger-bg' : isSuccess ? 'status-success-bg' : 'bg-bg-tertiary'
                            }`}>
                              <Icon size={12} weight="bold" className={
                                isError ? 'status-danger-text' : isSuccess ? 'status-success-text' : 'text-text-tertiary'
                              } />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-xs text-text-primary leading-tight truncate">
                                {activity.message || activity.action}
                              </p>
                              <div className="flex items-center gap-1.5 mt-0.5">
                                <span className="text-[10px] text-text-secondary font-medium">{activity.user || 'System'}</span>
                                <span className="text-text-tertiary text-[10px]">•</span>
                                <span className="text-[10px] text-text-tertiary">
                                  {formatRelativeTime(activity.timestamp, t)}
                                </span>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </Card.Body>
              </Card>
            </WidgetWrapper>
          </div>
          )}

          {/* System Health */}
          {isVisible('system') && (
          <div key="system">
            <WidgetWrapper editMode={editMode}>
              <Card variant="elevated" className="h-full flex flex-col p-0">
                <Card.Header 
                  icon={Heartbeat}
                  iconColor="blue"
                  title={t('dashboard.systemHealth')}
                  action={
                    <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/settings')}>
                      <Gear size={14} />
                    </Button>
                  }
                />
                <Card.Body className="flex-1 overflow-hidden !pt-0.5 !pb-0.5">
                  <div className="grid grid-cols-2 gap-1 mb-1.5">
                    <SystemStat 
                      icon={WifiHigh} 
                      label={t('dashboard.websocket')} 
                      value={isConnected ? t('common.connected') : t('common.disconnected')} 
                      status={isConnected ? 'online' : 'offline'} 
                    />
                    <SystemStat 
                      icon={Database} 
                      label={t('common.database')} 
                      value={t('dashboard.healthy')} 
                      status="online" 
                    />
                    <SystemStat 
                      icon={Clock} 
                      label={t('common.lastUpdate')} 
                      value={formatRelativeTime(lastUpdate, t)} 
                      status="online" 
                    />
                    <SystemStat 
                      icon={Lightning} 
                      label={t('dashboard.api')} 
                      value={t('common.online')} 
                      status="online" 
                    />
                  </div>
                  <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-wide mb-0.5">
                    {t('dashboard.services')}
                  </div>
                  <div className="grid grid-cols-4 gap-1">
                    <ServiceBadge name="ACME" status={systemStatus?.acme} />
                    <ServiceBadge name="SCEP" status={systemStatus?.scep} />
                    <ServiceBadge name="OCSP" status={systemStatus?.ocsp} />
                    <ServiceBadge name="CRL" status={systemStatus?.crl} />
                  </div>
                </Card.Body>
              </Card>
            </WidgetWrapper>
          </div>
          )}

          {/* ACME Accounts */}
          {isVisible('acme') && (
          <div key="acme">
            <WidgetWrapper editMode={editMode}>
              <Card variant="elevated" className="h-full flex flex-col p-0">
                <Card.Header 
                  icon={Globe}
                  iconColor="violet"
                  title={t('dashboard.acmeAccounts')}
                  action={
                    <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/acme')}>
                      {t('common.viewAll')} <CaretRight size={12} />
                    </Button>
                  }
                />
                <Card.Body className="flex-1 overflow-y-auto !pt-0">
                  {recentAcme.length === 0 ? (
                    <EmptyWidget icon={Globe} text={t('dashboard.noAcmeAccounts')} />
                  ) : (
                    <div className="space-y-0.5">
                      {recentAcme.slice(0, 4).map((account, i) => (
                        <div 
                          key={account.id || i} 
                          className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors group flex items-center gap-2.5"
                          onClick={() => navigate('/acme')}
                        >
                          <div className="w-7 h-7 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0 group-hover:bg-accent-primary/10 transition-colors">
                            <User size={14} weight="duotone" className="text-text-tertiary group-hover:text-accent-primary transition-colors" />
                          </div>
                          <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
                            <span className="text-xs font-medium text-text-primary truncate group-hover:text-accent-primary transition-colors">
                              {account.email || account.contact}
                            </span>
                            <Badge variant="secondary" size="sm">{account.orders_count || 0} {t('dashboard.orders')}</Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </Card.Body>
              </Card>
            </WidgetWrapper>
          </div>
          )}

          {/* Trust Store Expiring Widget */}
          {isVisible('trustExpiry') && (
          <div key="trustExpiry">
            <WidgetWrapper editMode={editMode}>
              <Card variant="elevated" className="h-full flex flex-col p-0">
                <Card.Header 
                  icon={ShieldCheck}
                  iconColor="orange"
                  title={t('dashboard.trustStoreExpiry')}
                  action={
                    <Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/truststore')}>
                      {t('common.viewAll')} <CaretRight size={12} />
                    </Button>
                  }
                />
                <Card.Body className="flex-1 overflow-y-auto !pt-0">
                  {trustStoreExpiring.expiring_count === 0 && trustStoreExpiring.expired_count === 0 ? (
                    <EmptyWidget icon={ShieldCheck} text={t('dashboard.noTrustStoreExpiring')} />
                  ) : (
                    <div className="space-y-0.5">
                      {trustStoreExpiring.expired.slice(0, 2).map((cert) => (
                        <div key={cert.id} className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors group flex items-center gap-2.5" onClick={() => navigate(`/truststore/${cert.id}`)}>
                          <div className="w-7 h-7 rounded-lg bg-status-danger/10 flex items-center justify-center shrink-0">
                            <Warning size={14} weight="duotone" className="text-status-danger" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-xs font-medium text-text-primary truncate block">{cert.name}</span>
                            <span className="text-[10px] text-status-danger">{t('common.expired')}</span>
                          </div>
                        </div>
                      ))}
                      {trustStoreExpiring.expiring.slice(0, 3).map((cert) => (
                        <div key={cert.id} className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors group flex items-center gap-2.5" onClick={() => navigate(`/truststore/${cert.id}`)}>
                          <div className="w-7 h-7 rounded-lg bg-accent-warning/10 flex items-center justify-center shrink-0">
                            <Clock size={14} weight="duotone" className="text-accent-warning" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-xs font-medium text-text-primary truncate block">{cert.name}</span>
                            <span className="text-[10px] text-accent-warning">{cert.days_remaining}d</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </Card.Body>
              </Card>
            </WidgetWrapper>
          </div>
          )}
        </Responsive>
        )}
        {/* Mobile: simple stacked layout — no RGL touch interference */}
        {gridMounted && !isDesktopGrid && (
          <div className="space-y-2 pb-4">
            {isVisible('stats') && (
            <div>
              <div className="grid grid-cols-4 gap-1.5 sm:gap-3">
                <StatCard icon={Certificate} label={t('common.certificates')} value={totalCerts} color="blue" live={isConnected} onClick={() => navigate('/certificates')} />
                <StatCard icon={ShieldCheck} label={t('common.cas')} value={totalCAs} color="purple" live={isConnected} onClick={() => navigate('/cas')} />
                <StatCard icon={ListChecks} label={t('common.csrs')} value={pendingCSRs} color={pendingCSRs > 0 ? 'yellow' : 'slate'} badge={pendingCSRs > 0 ? t('common.pending') : null} onClick={() => navigate('/csrs')} />
                <StatCard icon={Globe} label={t('common.acme')} value={acmeAccounts} color="emerald" onClick={() => navigate('/acme')} />
              </div>
            </div>
            )}

            {isVisible('chartTrend') && (
            <Card variant="elevated" className="p-0">
              <Card.Header icon={Lightning} iconColor="amber" title={t('dashboard.certificateActivity')} subtitle={t('dashboard.last7Days')} compact />
              <Card.Body className="!pt-0 !pb-0 !px-2">
                <div style={{ height: 200 }}>
                  <CertificateTrendChart data={certificateTrend} />
                </div>
              </Card.Body>
            </Card>
            )}

            {isVisible('chartPie') && (
            <Card variant="elevated" className="p-0">
              <Card.Header icon={Certificate} iconColor="violet" title={t('dashboard.statusDistribution')} compact />
              <Card.Body className="!pt-0 !pb-0 !px-2">
                <div style={{ height: 200 }}>
                  <StatusPieChart data={{ valid: Math.max(0, totalCerts - (stats?.expiring_soon || 0) - (stats?.revoked || 0)), expiring: stats?.expiring_soon || 0, expired: 0, revoked: stats?.revoked || 0 }} />
                </div>
              </Card.Body>
            </Card>
            )}

            {isVisible('nextExpiry') && (
            <Card variant="elevated" className="p-0">
              <Card.Header icon={Timer} iconColor="orange" title={t('dashboard.nextExpirations')} action={expiringCount > 0 ? <Badge variant="warning" size="sm" dot>{expiringCount}</Badge> : null} compact />
              <Card.Body className="!pt-0 !pb-2">
                {nextExpirations.length === 0 ? (
                  <EmptyWidget icon={Timer} text={t('dashboard.noExpirations')} />
                ) : (
                  <div className="space-y-1">
                    {nextExpirations.slice(0, 5).map((cert, i) => {
                      const daysLeft = cert.valid_to ? Math.max(0, Math.ceil((new Date(cert.valid_to) - new Date()) / (1000 * 60 * 60 * 24))) : null
                      const totalLifespan = (cert.valid_from && cert.valid_to) ? Math.max(1, Math.ceil((new Date(cert.valid_to) - new Date(cert.valid_from)) / (1000 * 60 * 60 * 24))) : 365
                      const progress = daysLeft !== null ? Math.min(100, (daysLeft / totalLifespan) * 100) : 0
                      const urgency = daysLeft === null ? 'gray' : daysLeft <= 7 ? 'danger' : daysLeft <= 15 ? 'warning' : daysLeft <= 30 ? 'yellow' : 'success'
                      const barColor = { danger: 'var(--accent-danger)', warning: 'var(--accent-warning)', yellow: '#EAB308', success: 'var(--accent-success)', gray: 'var(--text-tertiary)' }[urgency]
                      return (
                        <div key={cert.id || i} onClick={() => navigate(`/certificates/${cert.id}`)} className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors">
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="text-xs font-medium text-text-primary truncate flex-1">{cert.common_name || cert.descr || cert.subject || '—'}</span>
                            <span className={`text-[10px] font-semibold whitespace-nowrap ${urgency === 'danger' ? 'status-danger-text' : urgency === 'warning' ? 'status-warning-text' : 'text-text-secondary'}`}>
                              {daysLeft !== null ? t('dashboard.daysRemaining', { count: daysLeft }) : '—'}
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
                            <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(3, progress)}%`, backgroundColor: barColor }} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </Card.Body>
            </Card>
            )}

            {isVisible('certs') && (
            <Card variant="elevated" className="p-0">
              <Card.Header icon={Certificate} iconColor="blue" title={t('dashboard.recentCertificates')} action={<Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/certificates')}>{t('common.viewAll')} <CaretRight size={12} /></Button>} compact />
              <Card.Body className="space-y-0.5 !pt-0">
                {recentCerts.length === 0 ? (
                  <EmptyWidget icon={Certificate} text={t('dashboard.noCertificatesYet')} />
                ) : (
                  recentCerts.slice(0, 4).map((cert, i) => (
                    <div key={cert.id || i} onClick={() => navigate(`/certificates/${cert.id}`)} className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0">
                        <Certificate size={14} weight="duotone" className="text-text-tertiary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-text-primary truncate">{cert.common_name || cert.descr || cert.subject || t('common.certificate')}</span>
                          <Badge variant={cert.revoked ? 'danger' : (cert.valid_to && new Date(cert.valid_to) < new Date()) ? 'warning' : 'success'} size="sm" dot>
                            {cert.revoked ? t('common.revoked') : (cert.valid_to && new Date(cert.valid_to) < new Date()) ? t('common.expired') : t('common.valid')}
                          </Badge>
                        </div>
                        <div className="text-[10px] text-text-tertiary mt-0.5">{formatRelativeTime(cert.created_at, t)}</div>
                      </div>
                    </div>
                  ))
                )}
              </Card.Body>
            </Card>
            )}

            {isVisible('cas') && (
            <Card variant="elevated" className="p-0">
              <Card.Header icon={ShieldCheck} iconColor="emerald" title={t('dashboard.recentCAs')} action={<Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/cas')}>{t('common.viewAll')} <CaretRight size={12} /></Button>} compact />
              <Card.Body className="space-y-0.5 !pt-0">
                {recentCAs.length === 0 ? (
                  <EmptyWidget icon={ShieldCheck} text={t('dashboard.noCAsYet')} />
                ) : (
                  recentCAs.slice(0, 4).map((ca, i) => (
                    <div key={ca.id || i} onClick={() => navigate(`/cas/${ca.id}`)} className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0">
                        <ShieldCheck size={14} weight="duotone" className="text-text-tertiary" />
                      </div>
                      <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
                        <span className="text-xs font-medium text-text-primary truncate">{ca.dn_commonname || ca.descr || ca.name}</span>
                        <Badge variant={ca.is_root ? 'purple' : 'info'} size="sm">{ca.is_root ? t('common.root') : t('dashboard.sub')}</Badge>
                      </div>
                    </div>
                  ))
                )}
              </Card.Body>
            </Card>
            )}

            {isVisible('activity') && (
            <Card variant="elevated" className="p-0">
              <Card.Header icon={ClockCounterClockwise} iconColor="teal" title={t('dashboard.recentActivity')} action={<Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/audit')}>{t('common.viewAll')} <CaretRight size={12} /></Button>} compact />
              <Card.Body className="!pt-0">
                {activityLog.length === 0 ? (
                  <EmptyWidget icon={ClockCounterClockwise} text={t('dashboard.noRecentActivity')} />
                ) : (
                  <div className="space-y-0.5">
                    {activityLog.slice(0, 5).map((activity, i) => {
                      const Icon = actionIcons[activity.action] || actionIcons.default
                      const isError = activity.action === 'login_failed' || activity.action === 'revoke'
                      const isSuccess = activity.action === 'login_success' || activity.action === 'create'
                      return (
                        <div key={activity.id || i} className="p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors flex items-start gap-2.5">
                          <div className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 mt-0.5 ${isError ? 'status-danger-bg' : isSuccess ? 'status-success-bg' : 'bg-bg-tertiary'}`}>
                            <Icon size={12} weight="bold" className={isError ? 'status-danger-text' : isSuccess ? 'status-success-text' : 'text-text-tertiary'} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs text-text-primary leading-tight truncate">{activity.message || activity.action}</p>
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <span className="text-[10px] text-text-secondary font-medium">{activity.user || 'System'}</span>
                              <span className="text-text-tertiary text-[10px]">•</span>
                              <span className="text-[10px] text-text-tertiary">{formatRelativeTime(activity.timestamp, t)}</span>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </Card.Body>
            </Card>
            )}

            {isVisible('system') && (
            <Card variant="elevated" className="p-0">
              <Card.Header icon={Heartbeat} iconColor="blue" title={t('dashboard.systemHealth')} compact />
              <Card.Body className="!pt-0.5 !pb-1.5">
                <div className="grid grid-cols-2 gap-1 mb-1.5">
                  <SystemStat icon={WifiHigh} label={t('dashboard.websocket')} value={isConnected ? t('common.connected') : t('common.disconnected')} status={isConnected ? 'online' : 'offline'} />
                  <SystemStat icon={Database} label={t('common.database')} value={t('dashboard.healthy')} status="online" />
                  <SystemStat icon={Clock} label={t('common.lastUpdate')} value={formatRelativeTime(lastUpdate, t)} status="online" />
                  <SystemStat icon={Lightning} label={t('dashboard.api')} value={t('common.online')} status="online" />
                </div>
                <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-wide mb-0.5">{t('dashboard.services')}</div>
                <div className="grid grid-cols-4 gap-1">
                  <ServiceBadge name="ACME" status={systemStatus?.acme} />
                  <ServiceBadge name="SCEP" status={systemStatus?.scep} />
                  <ServiceBadge name="OCSP" status={systemStatus?.ocsp} />
                  <ServiceBadge name="CRL" status={systemStatus?.crl} />
                </div>
              </Card.Body>
            </Card>
            )}

            {isVisible('acme') && (
            <Card variant="elevated" className="p-0">
              <Card.Header icon={Globe} iconColor="violet" title={t('dashboard.acmeAccounts')} action={<Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/acme')}>{t('common.viewAll')} <CaretRight size={12} /></Button>} compact />
              <Card.Body className="!pt-0">
                {recentAcme.length === 0 ? (
                  <EmptyWidget icon={Globe} text={t('dashboard.noAcmeAccounts')} />
                ) : (
                  <div className="space-y-0.5">
                    {recentAcme.slice(0, 4).map((account, i) => (
                      <div key={account.id || i} className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors flex items-center gap-2.5" onClick={() => navigate('/acme')}>
                        <div className="w-7 h-7 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0">
                          <User size={14} weight="duotone" className="text-text-tertiary" />
                        </div>
                        <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-text-primary truncate">{account.email || account.contact}</span>
                          <Badge variant="secondary" size="sm">{account.orders_count || 0} {t('dashboard.orders')}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card.Body>
            </Card>
            )}

            {isVisible('trustExpiry') && (
            <Card variant="elevated" className="p-0">
              <Card.Header icon={ShieldCheck} iconColor="orange" title={t('dashboard.trustStoreExpiry')} action={<Button size="sm" variant="ghost" className="text-accent-primary" onClick={() => navigate('/truststore')}>{t('common.viewAll')} <CaretRight size={12} /></Button>} compact />
              <Card.Body className="!pt-0">
                {trustStoreExpiring.expiring_count === 0 && trustStoreExpiring.expired_count === 0 ? (
                  <EmptyWidget icon={ShieldCheck} text={t('dashboard.noTrustStoreExpiring')} />
                ) : (
                  <div className="space-y-0.5">
                    {trustStoreExpiring.expired.slice(0, 2).map((cert) => (
                      <div key={cert.id} className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors flex items-center gap-2.5" onClick={() => navigate(`/truststore/${cert.id}`)}>
                        <div className="w-7 h-7 rounded-lg bg-status-danger/10 flex items-center justify-center shrink-0">
                          <Warning size={14} weight="duotone" className="text-status-danger" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-xs font-medium text-text-primary truncate block">{cert.name}</span>
                          <span className="text-[10px] text-status-danger">{t('common.expired')}</span>
                        </div>
                      </div>
                    ))}
                    {trustStoreExpiring.expiring.slice(0, 3).map((cert) => (
                      <div key={cert.id} className="p-2 rounded-lg hover:bg-bg-tertiary/50 cursor-pointer transition-colors flex items-center gap-2.5" onClick={() => navigate(`/truststore/${cert.id}`)}>
                        <div className="w-7 h-7 rounded-lg bg-accent-warning/10 flex items-center justify-center shrink-0">
                          <Clock size={14} weight="duotone" className="text-accent-warning" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="text-xs font-medium text-text-primary truncate block">{cert.name}</span>
                          <span className="text-[10px] text-accent-warning">{cert.days_remaining}d</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card.Body>
            </Card>
            )}
          </div>
        )}
        </div>

      </div>
      
      {/* Widget Settings Modal */}
      <WidgetSettingsModal
        open={showWidgetSettings}
        onClose={() => setShowWidgetSettings(false)}
        widgets={widgets}
        onSave={(newWidgets) => {
          setWidgets(newWidgets)
          saveWidgetPrefs(newWidgets)
          setShowWidgetSettings(false)
        }}
      />
    </div>
  )
}

// Widget wrapper with drag handle for edit mode
function WidgetWrapper({ editMode, children }) {
  return (
    <div className="h-full relative">
      {editMode && (
        <div className="widget-drag-handle absolute top-0 left-0 right-0 h-8 z-10 flex items-center justify-center cursor-grab active:cursor-grabbing rounded-t-xl bg-accent-primary/5 border-b border-dashed border-accent-primary/20 opacity-0 hover:opacity-100 transition-opacity">
          <DotsSixVertical size={16} className="text-accent-primary" />
        </div>
      )}
      {children}
    </div>
  )
}

// Widget Settings Modal
function WidgetSettingsModal({ open, onClose, widgets, onSave }) {
  const { t } = useTranslation()
  const [localWidgets, setLocalWidgets] = useState(widgets)
  
  useEffect(() => {
    setLocalWidgets(widgets)
  }, [widgets, open])
  
  const toggleWidget = (id) => {
    setLocalWidgets(prev => prev.map(w => 
      w.id === id ? { ...w, visible: !w.visible } : w
    ))
  }
  
  const resetToDefaults = () => {
    setLocalWidgets(DEFAULT_WIDGETS)
  }

  return (
    <Modal open={open} onClose={onClose} size="sm">
      <div className="p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg icon-bg-blue flex items-center justify-center">
              <SlidersHorizontal size={18} className="text-accent-primary" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-text-primary">{t('dashboard.customizeDashboard')}</h2>
              <p className="text-xs text-text-secondary">{t('dashboard.showOrHideWidgets')}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-bg-tertiary text-text-secondary">
            <X size={18} />
          </button>
        </div>
        
        <div className="space-y-1 mb-4">
          {localWidgets.map(widget => (
            <button
              key={widget.id}
              onClick={() => toggleWidget(widget.id)}
              className="w-full flex items-center gap-3 p-2.5 rounded-lg hover:bg-bg-tertiary transition-colors"
            >
              <div className={`w-5 h-5 rounded flex items-center justify-center transition-colors ${
                widget.visible ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-tertiary'
              }`}>
                {widget.visible ? <Eye size={14} /> : <EyeSlash size={14} />}
              </div>
              <span className={`text-sm ${widget.visible ? 'text-text-primary' : 'text-text-tertiary'}`}>
                {t(widget.nameKey)}
              </span>
            </button>
          ))}
        </div>
        
        <div className="flex items-center justify-between pt-3 border-t border-border">
          <Button size="sm" variant="ghost" onClick={resetToDefaults}>
            {t('common.reset')}
          </Button>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button size="sm" onClick={() => onSave(localWidgets)}>
              {t('common.save')}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

// Enhanced Stat Card
function StatCard({ icon: Icon, label, value, color, onClick, live, badge }) {
  const accentMap = {
    blue: '--accent-primary',
    purple: '--accent-pro',
    yellow: '--accent-warning',
    emerald: '--accent-success',
    slate: '--text-tertiary',
  }
  
  const colorClasses = {
    blue: 'primary',
    purple: 'pro',
    yellow: 'warning',
    emerald: 'success',
    slate: '',
  }
  
  const iconStyles = {
    blue: 'icon-bg-blue',
    purple: 'icon-bg-violet',
    yellow: 'icon-bg-amber',
    emerald: 'icon-bg-emerald',
    slate: 'icon-bg-teal',
  }
  
  const variant = colorClasses[color] || ''
  const accentVar = accentMap[color] || accentMap.slate
  
  return (
    <button 
      onClick={onClick}
      className={`stat-card-enhanced ${variant} relative p-2 sm:p-3 text-left group transition-all duration-200`}
      style={{ '--card-accent': `var(${accentVar})` }}
    >
      {live && (
        <div className="absolute top-1.5 right-1.5 sm:top-2.5 sm:right-2.5 flex items-center gap-1.5 z-10">
          <span className="text-[10px] status-success-text font-medium opacity-0 group-hover:opacity-100 transition-opacity hidden sm:inline">Live</span>
          <div className="w-2 h-2 rounded-full status-success-bg-solid animate-pulse-soft" />
        </div>
      )}
      
      <div className="relative flex flex-col sm:flex-row items-center sm:items-center gap-1 sm:gap-3">
        <div className={`w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-105 ${iconStyles[color] || iconStyles.slate}`}>
          <Icon size={18} weight="duotone" />
        </div>
        <div className="min-w-0 text-center sm:text-left w-full">
          <div className="flex items-center justify-center sm:justify-start gap-2">
            <p className="text-lg sm:text-xl font-bold text-text-primary tracking-tight tabular-nums">{value}</p>
            {badge && (
              <Badge variant="warning" size="sm" dot pulse className="hidden sm:inline-flex">{badge}</Badge>
            )}
          </div>
          <p className="text-[9px] sm:text-[11px] text-text-secondary font-medium leading-tight line-clamp-2 sm:truncate sm:line-clamp-none">{label}</p>
        </div>
      </div>
      
      <CaretRight 
        size={14} 
        className="absolute right-2.5 bottom-2.5 text-text-tertiary opacity-0 group-hover:opacity-60 transition-all duration-200 group-hover:translate-x-0.5 hidden sm:block" 
      />
    </button>
  )
}

// System Stat mini card
function SystemStat({ icon: Icon, label, value, status }) {
  return (
    <div className={`px-2.5 py-1.5 rounded-lg border transition-all duration-200 group ${
      status === 'online' 
        ? 'stat-card-success' 
        : 'stat-card-danger'
    }`}>
      <div className="flex items-center gap-1.5">
        <div className={`w-4 h-4 rounded flex items-center justify-center transition-transform duration-200 group-hover:scale-110 ${
          status === 'online' ? 'status-success-bg' : 'status-danger-bg'
        }`}>
          <Icon size={10} className={status === 'online' ? 'status-success-text' : 'status-danger-text'} weight="bold" />
        </div>
        <span className="text-[10px] text-text-tertiary uppercase tracking-wide font-medium">{label}</span>
      </div>
      <p className={`text-[11px] font-semibold mt-0.5 ${
        status === 'online' ? 'status-success-text' : 'status-danger-text'
      }`}>{value}</p>
    </div>
  )
}

// Service Badge Component
function ServiceBadge({ name, status }) {
  const isOnline = status?.status === 'online' || status?.enabled
  return (
    <div className={`px-2.5 py-2 rounded-lg border text-center transition-all duration-200 group cursor-default ${
      isOnline 
        ? 'stat-card-success' 
        : 'bg-bg-tertiary border-border hover:border-text-tertiary/30'
    }`}>
      <div className="flex items-center justify-center gap-1.5">
        <div className={`w-2 h-2 rounded-full transition-transform duration-300 group-hover:scale-125 ${isOnline ? 'status-success-bg-solid animate-pulse' : 'bg-text-tertiary'}`} />
        <span className={`text-xs font-semibold ${isOnline ? 'text-text-primary' : 'text-text-secondary'}`}>{name}</span>
      </div>
    </div>
  )
}

// Empty Widget Component
function EmptyWidget({ icon: Icon, text }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary py-6">
      <div className="w-10 h-10 rounded-xl bg-bg-tertiary/50 flex items-center justify-center mb-2 border border-border/50">
        <Icon size={20} className="opacity-50" />
      </div>
      <p className="text-xs font-medium opacity-70">{text}</p>
    </div>
  )
}
