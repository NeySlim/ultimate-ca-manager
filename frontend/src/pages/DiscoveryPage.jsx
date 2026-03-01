/**
 * DiscoveryPage — Certificate Discovery with scan profiles, results & history
 * Pattern: CSRsPage (stats + sidebar tabs + table) 
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Globe, MagnifyingGlass, ShieldCheck, Warning, Clock,
  ArrowsClockwise, Trash, Play, Plus, CheckCircle, XCircle,
  ClockCounterClockwise, FolderOpen, Pencil, CalendarBlank,
  WifiHigh, WifiSlash, Certificate, ArrowSquareOut, Network
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable,
  Badge, Button, Input, Modal, Textarea, Select,
  LoadingSpinner, EmptyState, HelpCard,
  CompactSection, CompactGrid, CompactField, CompactHeader, CompactStats
} from '../components'
import { ConfirmModal } from '../components/FormModal'
import { discoveryService } from '../services'
import { useNotification } from '../contexts'
import { useMobile } from '../contexts/MobileContext'
import { usePermission, useWebSocket } from '../hooks'
import { formatDate, cn } from '../lib/utils'

export default function DiscoveryPage() {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const { showSuccess, showError } = useNotification()
  const { isAdmin, canWrite } = usePermission()
  const { subscribe } = useWebSocket({ showToasts: false })
  const [searchParams, setSearchParams] = useSearchParams()

  // Tab state
  const TABS = [
    { id: 'discovered', label: t('discovery.tabDiscovered'), icon: Globe },
    { id: 'profiles', label: t('discovery.tabProfiles'), icon: FolderOpen },
    { id: 'history', label: t('discovery.tabHistory'), icon: ClockCounterClockwise },
  ]
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'discovered')

  // Data
  const [loading, setLoading] = useState(true)
  const [discovered, setDiscovered] = useState([])
  const [discoveredTotal, setDiscoveredTotal] = useState(0)
  const [profiles, setProfiles] = useState([])
  const [runs, setRuns] = useState([])
  const [runsTotal, setRunsTotal] = useState(0)
  const [stats, setStats] = useState({ total: 0, managed: 0, unmanaged: 0, expired: 0, expiring_soon: 0, errors: 0 })

  // Scan state
  const [scanning, setScanning] = useState(false)
  const [scanProgress, setScanProgress] = useState(null)

  // Modals
  const [showProfileForm, setShowProfileForm] = useState(false)
  const [editingProfile, setEditingProfile] = useState(null)
  const [showQuickScan, setShowQuickScan] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(null)

  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

  // ── Data loaders ──────────────────────────────────────
  const loadStats = useCallback(async () => {
    try {
      const res = await discoveryService.getStats()
      setStats(res.data ?? res)
    } catch { /* silent */ }
  }, [])

  const loadProfiles = useCallback(async () => {
    try {
      const res = await discoveryService.getProfiles()
      setProfiles(res.data ?? res ?? [])
    } catch { /* silent */ }
  }, [])

  const loadDiscovered = useCallback(async () => {
    try {
      const res = await discoveryService.getAll({ page, per_page: perPage })
      const data = res.data ?? res
      if (Array.isArray(data)) {
        setDiscovered(data)
        setDiscoveredTotal(data.length)
      } else {
        setDiscovered(data.items ?? [])
        setDiscoveredTotal(data.total ?? data.items?.length ?? 0)
      }
    } catch { /* silent */ }
  }, [page, perPage])

  const loadRuns = useCallback(async () => {
    try {
      const res = await discoveryService.getRuns({ limit: 50 })
      const data = res.data ?? res
      if (Array.isArray(data)) {
        setRuns(data)
        setRunsTotal(data.length)
      } else {
        setRuns(data.items ?? [])
        setRunsTotal(data.total ?? data.items?.length ?? 0)
      }
    } catch { /* silent */ }
  }, [])

  const loadAll = useCallback(async () => {
    setLoading(true)
    await Promise.all([loadStats(), loadProfiles(), loadDiscovered(), loadRuns()])
    setLoading(false)
  }, [loadStats, loadProfiles, loadDiscovered, loadRuns])

  useEffect(() => { loadAll() }, [loadAll])
  useEffect(() => { loadDiscovered() }, [page, perPage])

  // ── WebSocket ─────────────────────────────────────────
  useEffect(() => {
    const unsub1 = subscribe('discovery.scan_started', () => {
      setScanning(true)
      setScanProgress({ scanned: 0, total: 0, found: 0 })
    })
    const unsub2 = subscribe('discovery.scan_progress', (data) => {
      setScanProgress(prev => ({
        scanned: data.scanned ?? prev?.scanned ?? 0,
        total: data.total ?? prev?.total ?? 0,
        found: data.found ?? prev?.found ?? 0,
      }))
    })
    const unsub3 = subscribe('discovery.scan_complete', () => {
      setScanning(false)
      setScanProgress(null)
      loadAll()
    })
    return () => { unsub1(); unsub2(); unsub3() }
  }, [subscribe, loadAll])

  // ── Handlers ──────────────────────────────────────────
  const handleTabChange = (tabId) => {
    setActiveTab(tabId)
    setPage(1)
    setSearchParams({ tab: tabId })
  }

  const handleSaveProfile = async (formData) => {
    try {
      if (editingProfile) {
        await discoveryService.updateProfile(editingProfile.id, formData)
        showSuccess(t('discovery.profileUpdated'))
      } else {
        await discoveryService.createProfile(formData)
        showSuccess(t('discovery.profileCreated'))
      }
      setShowProfileForm(false)
      setEditingProfile(null)
      loadProfiles()
    } catch (error) {
      showError(error.message || t('messages.errors.saveFailed'))
    }
  }

  const handleDeleteProfile = async (id) => {
    try {
      await discoveryService.deleteProfile(id)
      showSuccess(t('discovery.profileDeleted'))
      loadProfiles()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed'))
    }
    setDeleteConfirm(null)
  }

  const handleScanProfile = async (profileId) => {
    try {
      setScanning(true)
      await discoveryService.scanProfile(profileId)
    } catch (error) {
      showError(error.message || t('discovery.scanFailed'))
      setScanning(false)
    }
  }

  const handleQuickScan = async (formData) => {
    try {
      setScanning(true)
      setShowQuickScan(false)
      await discoveryService.scan(formData.targets, formData.ports)
    } catch (error) {
      showError(error.message || t('discovery.scanFailed'))
      setScanning(false)
    }
  }

  const handleDeleteDiscovered = async (id) => {
    try {
      await discoveryService.delete(id)
      showSuccess(t('messages.success.delete'))
      loadDiscovered()
      loadStats()
    } catch (error) {
      showError(error.message)
    }
    setDeleteConfirm(null)
  }

  const handleDeleteAll = async () => {
    try {
      await discoveryService.deleteAll()
      showSuccess(t('discovery.deleteAll'))
      loadDiscovered()
      loadStats()
    } catch (error) {
      showError(error.message)
    }
    setDeleteConfirm(null)
  }

  // ── Stats bar ─────────────────────────────────────────
  const statsBar = useMemo(() => [
    { icon: Globe, label: t('common.total'), value: stats.total, variant: 'primary' },
    { icon: ShieldCheck, label: t('discovery.managed'), value: stats.managed, variant: 'success' },
    { icon: Warning, label: t('discovery.unmanaged'), value: stats.unmanaged, variant: 'warning' },
    { icon: XCircle, label: t('common.expired'), value: stats.expired, variant: 'danger' },
  ], [stats, t])

  // ── Discovered columns ────────────────────────────────
  const discoveredColumns = useMemo(() => [
    {
      key: 'subject',
      header: t('common.commonName'),
      sortable: true,
      priority: 1,
      render: (val, row) => {
        const extractCN = (s) => { const m = s?.match(/CN=([^,]+)/); return m ? m[1] : null }
        const name = extractCN(row.subject) || row.target || t('common.unknown')
        return (
          <div className="flex items-center gap-2">
            <div className={cn(
              "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
              row.status === 'managed' ? 'icon-bg-emerald' : 'icon-bg-orange'
            )}>
              <Certificate size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{name}</span>
          </div>
        )
      }
    },
    {
      key: 'target',
      header: t('discovery.host'),
      sortable: true,
      priority: 2,
      hideOnMobile: true,
      render: (val, row) => (
        <span className="text-text-secondary text-sm">{val || '—'}:{row.port || 443}</span>
      )
    },
    {
      key: 'status',
      header: t('common.status'),
      sortable: true,
      priority: 2,
      render: (val) => {
        const cfg = {
          managed: { variant: 'success', icon: ShieldCheck, label: t('discovery.managed') },
          unmanaged: { variant: 'warning', icon: Warning, label: t('discovery.unmanaged') },
          error: { variant: 'danger', icon: XCircle, label: t('common.error') },
        }
        const { variant, icon, label } = cfg[val] || cfg.error
        return <Badge variant={variant} size="sm" icon={icon} dot>{label}</Badge>
      }
    },
    {
      key: 'not_after',
      header: t('common.expires'),
      sortable: true,
      priority: 3,
      hideOnMobile: true,
      render: (val) => {
        if (!val) return <span className="text-text-tertiary">—</span>
        const d = new Date(val)
        const now = new Date()
        const days = Math.floor((d - now) / 86400000)
        const isExpired = days < 0
        const isExpiring = days >= 0 && days <= 30
        return (
          <span className={cn(
            "text-xs whitespace-nowrap",
            isExpired ? "text-status-danger" : isExpiring ? "text-status-warning" : "text-text-secondary"
          )}>
            {formatDate(val)}
            {isExpired && <span className="ml-1">({t('common.expired')})</span>}
            {isExpiring && <span className="ml-1">({days}d)</span>}
          </span>
        )
      }
    },
    {
      key: 'issuer',
      header: t('common.issuer'),
      sortable: true,
      priority: 4,
      hideOnMobile: true,
      render: (val) => <span className="text-text-secondary truncate text-sm">{val || '—'}</span>
    },
    {
      key: 'actions',
      header: '',
      priority: 1,
      width: 60,
      render: (_, row) => (
        <div className="flex items-center gap-1">
          {canWrite('certificates') && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setDeleteConfirm({ type: 'discovered', id: row.id }) }}
              className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-tertiary hover:text-status-danger transition-colors"
              title={t('common.delete')}
            >
              <Trash size={14} />
            </button>
          )}
        </div>
      )
    }
  ], [t, canWrite])

  // ── Profile columns ───────────────────────────────────
  const profileColumns = useMemo(() => [
    {
      key: 'name',
      header: t('common.name'),
      sortable: true,
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0 icon-bg-violet">
            <FolderOpen size={14} weight="duotone" />
          </div>
          <div className="min-w-0">
            <span className="font-medium truncate block">{val}</span>
            {row.description && (
              <span className="text-xs text-text-tertiary truncate block">{row.description}</span>
            )}
          </div>
        </div>
      )
    },
    {
      key: 'targets',
      header: t('discovery.targets'),
      priority: 2,
      hideOnMobile: true,
      render: (val, row) => {
        const targets = row.targets_list || (typeof val === 'string' ? val.split(',') : val) || []
        return (
          <span className="text-text-secondary text-sm truncate">
            {targets.slice(0, 3).join(', ')}
            {targets.length > 3 && ` +${targets.length - 3}`}
          </span>
        )
      }
    },
    {
      key: 'schedule_interval',
      header: t('discovery.schedule'),
      priority: 3,
      hideOnMobile: true,
      render: (val) => {
        if (!val) return <Badge variant="secondary" size="sm">{t('discovery.manual')}</Badge>
        const hours = Math.round(val / 3600)
        return <Badge variant="info" size="sm" icon={Clock}>{hours}h</Badge>
      }
    },
    {
      key: 'enabled',
      header: t('common.status'),
      priority: 2,
      render: (val) => (
        <Badge variant={val ? 'success' : 'secondary'} size="sm" dot>
          {val ? t('common.enabled') : t('common.disabled')}
        </Badge>
      )
    },
    {
      key: 'actions',
      header: '',
      priority: 1,
      width: 100,
      render: (_, row) => (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); handleScanProfile(row.id) }}
            disabled={scanning}
            className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-tertiary hover:text-accent-primary transition-colors disabled:opacity-40"
            title={t('discovery.runScan')}
          >
            <Play size={14} />
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setEditingProfile(row); setShowProfileForm(true) }}
            className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary transition-colors"
            title={t('common.edit')}
          >
            <Pencil size={14} />
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setDeleteConfirm({ type: 'profile', id: row.id }) }}
            className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-tertiary hover:text-status-danger transition-colors"
            title={t('common.delete')}
          >
            <Trash size={14} />
          </button>
        </div>
      )
    }
  ], [t, scanning, handleScanProfile])

  // ── History columns ───────────────────────────────────
  const historyColumns = useMemo(() => [
    {
      key: 'profile_name',
      header: t('discovery.profile'),
      sortable: true,
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
            row.status === 'completed' ? 'icon-bg-emerald' : row.status === 'running' ? 'icon-bg-blue' : 'icon-bg-rose'
          )}>
            <ClockCounterClockwise size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{val || t('discovery.adHocScan')}</span>
        </div>
      )
    },
    {
      key: 'status',
      header: t('common.status'),
      sortable: true,
      priority: 2,
      render: (val) => {
        const cfg = {
          completed: { variant: 'success', icon: CheckCircle, label: t('common.completed') },
          running: { variant: 'info', icon: ArrowsClockwise, label: t('discovery.scanning') },
          failed: { variant: 'danger', icon: XCircle, label: t('common.failed') },
        }
        const { variant, icon, label } = cfg[val] || { variant: 'secondary', icon: Clock, label: val }
        return <Badge variant={variant} size="sm" icon={icon} dot={val === 'running'}>{label}</Badge>
      }
    },
    {
      key: 'certs_found',
      header: t('discovery.certsFound'),
      sortable: true,
      priority: 3,
      render: (val) => (
        <span className="text-sm text-text-secondary">{val ?? 0}</span>
      )
    },
    {
      key: 'started_at',
      header: t('common.date'),
      sortable: true,
      priority: 2,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">{formatDate(val)}</span>
      )
    },
    {
      key: 'duration_seconds',
      header: t('discovery.duration'),
      priority: 4,
      hideOnMobile: true,
      render: (val) => {
        if (!val && val !== 0) return <span className="text-text-tertiary">—</span>
        const secs = Math.round(val)
        return <span className="text-xs text-text-secondary">{secs < 60 ? `${secs}s` : `${Math.round(secs / 60)}m`}</span>
      }
    }
  ], [t])

  // ── Tab content ───────────────────────────────────────
  const renderContent = () => {
    switch (activeTab) {
      case 'discovered':
        return (
          <ResponsiveDataTable
            data={discovered}
            columns={discoveredColumns}
            loading={loading}
            searchable
            searchPlaceholder={t('discovery.searchDiscovered')}
            searchKeys={['subject', 'target', 'issuer', 'serial_number']}
            columnStorageKey="ucm-discovery-columns"
            sortable
            defaultSort={{ key: 'cn', direction: 'asc' }}
            toolbarActions={canWrite('certificates') && (
              isMobile ? (
                <Button type="button" size="lg" onClick={() => setShowQuickScan(true)} disabled={scanning} className="w-11 h-11 p-0">
                  <MagnifyingGlass size={22} weight="bold" />
                </Button>
              ) : (
                <div className="flex gap-2">
                  {discovered.length > 0 && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleteConfirm({ type: 'all' })}
                    >
                      <Trash size={14} />
                      {t('discovery.deleteAll')}
                    </Button>
                  )}
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => setShowQuickScan(true)}
                    disabled={scanning}
                  >
                    {scanning ? <ArrowsClockwise size={14} className="animate-spin" /> : <MagnifyingGlass size={14} />}
                    {scanning ? t('discovery.scanning') : t('discovery.quickScan')}
                  </Button>
                </div>
              )
            )}
            emptyIcon={Globe}
            emptyTitle={t('discovery.noResults')}
            emptyDescription={t('discovery.noResultsDesc')}
            emptyAction={canWrite('certificates') && (
              <Button type="button" onClick={() => setShowQuickScan(true)}>
                <MagnifyingGlass size={16} />
                {t('discovery.quickScan')}
              </Button>
            )}
          />
        )

      case 'profiles':
        return (
          <ResponsiveDataTable
            data={profiles}
            columns={profileColumns}
            loading={loading}
            searchable
            searchPlaceholder={t('discovery.searchProfiles')}
            searchKeys={['name', 'description', 'targets']}
            columnStorageKey="ucm-discovery-profiles-columns"
            sortable
            defaultSort={{ key: 'name', direction: 'asc' }}
            toolbarActions={canWrite('certificates') && (
              isMobile ? (
                <Button type="button" size="lg" onClick={() => { setEditingProfile(null); setShowProfileForm(true) }} className="w-11 h-11 p-0">
                  <Plus size={22} weight="bold" />
                </Button>
              ) : (
                <Button type="button" size="sm" onClick={() => { setEditingProfile(null); setShowProfileForm(true) }}>
                  <Plus size={14} weight="bold" />
                  {t('discovery.createProfile')}
                </Button>
              )
            )}
            emptyIcon={FolderOpen}
            emptyTitle={t('discovery.noProfiles')}
            emptyDescription={t('discovery.noProfilesDesc')}
            emptyAction={canWrite('certificates') && (
              <Button type="button" onClick={() => { setEditingProfile(null); setShowProfileForm(true) }}>
                <Plus size={16} />
                {t('discovery.createProfile')}
              </Button>
            )}
          />
        )

      case 'history':
        return (
          <ResponsiveDataTable
            data={runs}
            columns={historyColumns}
            loading={loading}
            searchable
            searchPlaceholder={t('discovery.searchHistory')}
            searchKeys={['profile_name', 'status']}
            columnStorageKey="ucm-discovery-history-columns"
            sortable
            defaultSort={{ key: 'started_at', direction: 'desc' }}
            emptyIcon={ClockCounterClockwise}
            emptyTitle={t('discovery.noHistory')}
            emptyDescription={t('discovery.noHistoryDesc')}
          />
        )

      default:
        return null
    }
  }

  // ── Help content ──────────────────────────────────────
  const helpContent = (
    <div className="space-y-4">
      <div className="visual-section">
        <div className="visual-section-header">
          <Globe size={16} className="status-primary-text" />
          {t('discovery.title')}
        </div>
        <div className="visual-section-body">
          <div className="quick-info-grid">
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-primary">{stats.total}</div>
              <div className="help-stat-label">{t('common.total')}</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-success">{stats.managed}</div>
              <div className="help-stat-label">{t('discovery.managed')}</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-warning">{stats.unmanaged}</div>
              <div className="help-stat-label">{t('discovery.unmanaged')}</div>
            </div>
          </div>
        </div>
      </div>
      <HelpCard title={t('discovery.aboutDiscovery')} variant="info">
        {t('discovery.aboutDiscoveryDesc')}
      </HelpCard>
      <HelpCard title={t('discovery.quickScan')} variant="tip">
        {t('discovery.quickScanHelp')}
      </HelpCard>
    </div>
  )

  // Tabs with counts
  const tabsWithCounts = TABS.map(tab => ({
    ...tab,
    count: tab.id === 'discovered' ? discoveredTotal
      : tab.id === 'profiles' ? profiles.length
      : tab.id === 'history' ? runsTotal
      : undefined
  }))

  // Scanning progress subtitle
  const subtitle = scanning && scanProgress
    ? `${t('discovery.scanning')}… ${scanProgress.scanned}/${scanProgress.total}`
    : t('discovery.subtitle')

  return (
    <>
      <ResponsiveLayout
        title={t('discovery.title')}
        subtitle={subtitle}
        icon={Globe}
        stats={statsBar}
        tabs={tabsWithCounts}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        tabLayout="sidebar"
        helpPageKey="discovery"
      >
        {renderContent()}
      </ResponsiveLayout>

      {/* Quick Scan Modal */}
      <QuickScanModal
        open={showQuickScan}
        onClose={() => setShowQuickScan(false)}
        onScan={handleQuickScan}
        scanning={scanning}
        t={t}
      />

      {/* Profile Form Modal */}
      <ProfileFormModal
        open={showProfileForm}
        onClose={() => { setShowProfileForm(false); setEditingProfile(null) }}
        onSave={handleSaveProfile}
        profile={editingProfile}
        t={t}
      />

      {/* Confirm Dialogs */}
      <ConfirmModal
        open={deleteConfirm?.type === 'profile'}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={() => handleDeleteProfile(deleteConfirm?.id)}
        title={t('discovery.deleteProfile')}
        message={t('discovery.deleteProfileConfirm')}
        confirmLabel={t('common.delete')}
        variant="danger"
      />
      <ConfirmModal
        open={deleteConfirm?.type === 'discovered'}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={() => handleDeleteDiscovered(deleteConfirm?.id)}
        title={t('common.delete')}
        message={t('discovery.deleteDiscoveredConfirm')}
        confirmLabel={t('common.delete')}
        variant="danger"
      />
      <ConfirmModal
        open={deleteConfirm?.type === 'all'}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDeleteAll}
        title={t('discovery.deleteAll')}
        message={t('discovery.deleteAllConfirm')}
        confirmLabel={t('discovery.deleteAll')}
        variant="danger"
      />
    </>
  )
}


// ════════════════════════════════════════════════════════
// Quick Scan Modal
// ════════════════════════════════════════════════════════
function QuickScanModal({ open, onClose, onScan, scanning, t }) {
  const [targets, setTargets] = useState('')
  const [ports, setPorts] = useState('443')

  const handleSubmit = (e) => {
    e.preventDefault()
    const targetList = targets.split(/[\n,]+/).map(s => s.trim()).filter(Boolean)
    const portList = ports.split(/[,\s]+/).map(s => parseInt(s.trim())).filter(n => n > 0 && n <= 65535)
    if (!targetList.length) return
    onScan({ targets: targetList, ports: portList.length ? portList : [443] })
  }

  // Common port presets
  const portPresets = [
    { label: 'HTTPS (443)', value: '443' },
    { label: 'HTTPS + Alt', value: '443, 8443' },
    { label: t('discovery.allCommon'), value: '443, 8443, 8080, 636, 993, 995, 465, 587' },
  ]

  return (
    <Modal open={open} onClose={onClose} title={t('discovery.quickScan')}>
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        <Textarea
          label={t('discovery.targets')}
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          placeholder={`example.com\n192.168.1.0/24\n10.0.0.1:8443`}
          rows={5}
          required
          helperText={t('discovery.targetsHelpDetailed')}
        />
        <div>
          <Input
            label={t('discovery.ports')}
            value={ports}
            onChange={(e) => setPorts(e.target.value)}
            placeholder="443, 8443, 636"
            helperText={t('discovery.portsHelpDetailed')}
          />
          <div className="flex flex-wrap gap-1.5 mt-2">
            {portPresets.map((preset) => (
              <button
                key={preset.value}
                type="button"
                className={cn(
                  'text-xs px-2 py-0.5 rounded-full border transition-colors',
                  ports === preset.value
                    ? 'bg-accent-primary text-white border-accent-primary'
                    : 'border-border text-text-secondary hover:border-accent-primary hover:text-accent-primary'
                )}
                onClick={() => setPorts(preset.value)}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={scanning || !targets.trim()}>
            {scanning ? <ArrowsClockwise size={14} className="animate-spin" /> : <MagnifyingGlass size={14} />}
            {t('discovery.startScan')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}


// ════════════════════════════════════════════════════════
// Profile Form Modal
// ════════════════════════════════════════════════════════
function ProfileFormModal({ open, onClose, onSave, profile, t }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [targets, setTargets] = useState('')
  const [ports, setPorts] = useState('443')
  const [schedule, setSchedule] = useState('0')
  const [enabled, setEnabled] = useState(true)
  const [notifyEmail, setNotifyEmail] = useState('')

  useEffect(() => {
    if (open) {
      if (profile) {
        setName(profile.name || '')
        setDescription(profile.description || '')
        const t = profile.targets_list || (typeof profile.targets === 'string' ? JSON.parse(profile.targets) : profile.targets) || []
        setTargets(t.join('\n'))
        const p = profile.ports_list || (typeof profile.ports === 'string' ? JSON.parse(profile.ports) : profile.ports) || [443]
        setPorts(p.join(', '))
        setSchedule(String(profile.schedule_interval || 0))
        setEnabled(profile.enabled !== false)
        setNotifyEmail(profile.notify_email || '')
      } else {
        setName(''); setDescription(''); setTargets(''); setPorts('443')
        setSchedule('0'); setEnabled(true); setNotifyEmail('')
      }
    }
  }, [open, profile])

  const handleSubmit = (e) => {
    e.preventDefault()
    const targetList = targets.split(/[\n,]+/).map(s => s.trim()).filter(Boolean)
    const portList = ports.split(/[,\s]+/).map(s => parseInt(s.trim())).filter(n => n > 0 && n <= 65535)
    if (!name.trim() || !targetList.length) return
    onSave({
      name: name.trim(),
      description: description.trim(),
      targets: targetList,
      ports: portList.length ? portList : [443],
      schedule_interval: parseInt(schedule) || 0,
      enabled,
      notify_email: notifyEmail.trim() || null,
    })
  }

  const scheduleOptions = [
    { value: '0', label: t('discovery.manual') },
    { value: '3600', label: t('discovery.every1h') },
    { value: '21600', label: t('discovery.every6h') },
    { value: '43200', label: t('discovery.every12h') },
    { value: '86400', label: t('discovery.every24h') },
    { value: '604800', label: t('discovery.every7d') },
  ]

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={profile ? t('discovery.editProfile') : t('discovery.createProfile')}
    >
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        <Input
          label={t('common.name')}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder={t('discovery.profileNamePlaceholder')}
        />
        <Input
          label={t('common.description')}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t('discovery.profileDescPlaceholder')}
        />
        <Textarea
          label={t('discovery.targets')}
          value={targets}
          onChange={(e) => setTargets(e.target.value)}
          placeholder={`example.com\n192.168.1.0/24\n10.0.0.1:8443`}
          rows={4}
          required
          helperText={t('discovery.targetsHelpDetailed')}
        />
        <Input
          label={t('discovery.ports')}
          value={ports}
          onChange={(e) => setPorts(e.target.value)}
          placeholder="443, 8443, 636"
          helperText={t('discovery.portsHelpDetailed')}
        />
        <Select
          label={t('discovery.schedule')}
          value={schedule}
          onChange={(val) => setSchedule(val)}
          options={scheduleOptions}
        />
        <Input
          label={t('discovery.notifyEmail')}
          value={notifyEmail}
          onChange={(e) => setNotifyEmail(e.target.value)}
          placeholder="admin@example.com"
          type="email"
        />
        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={!name.trim() || !targets.trim()}>
            {profile ? t('common.save') : t('common.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
