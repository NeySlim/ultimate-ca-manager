/**
 * DiscoveryPage — Certificate Discovery with scan profiles, results & history
 * Pattern: CSRsPage (stats + sidebar tabs + table) 
 */
import { useState, useEffect, useCallback, useMemo, Fragment } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Globe, MagnifyingGlass, ShieldCheck, Warning, WarningCircle, Clock,
  ArrowsClockwise, Trash, Play, Plus, CheckCircle, XCircle,
  ClockCounterClockwise, FolderOpen, Pencil, CalendarBlank,
  WifiHigh, WifiSlash, Certificate, ArrowSquareOut, Network,
  Export, Gauge, Lightning, MapPin, Crosshair, Plugs,
  GearSix, Timer, Bell, CaretDown, Envelope, Funnel, ArrowCounterClockwise,
  IdentificationBadge, Stamp
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable,
  Badge, Button, Input, Modal, Textarea, Select,
  LoadingSpinner, EmptyState, HelpCard,
  CompactSection, CompactGrid, CompactField, CompactHeader, CompactStats
} from '../components'
import TagsInput from '../components/ui/TagsInput'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'
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

  // Selection (detail panel)
  const [selectedItem, setSelectedItem] = useState(null)

  // Modals
  const [showProfileForm, setShowProfileForm] = useState(false)
  const [editingProfile, setEditingProfile] = useState(null)
  const [showQuickScan, setShowQuickScan] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(null)

  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

  // Filters
  const [statusFilter, setStatusFilter] = useState(null)   // null = all, 'managed', 'unmanaged', 'error'
  const [profileFilter, setProfileFilter] = useState(null)  // null = all, profile id

  // ── Data loaders ──────────────────────────────────────
  const loadStats = useCallback(async () => {
    try {
      const params = {}
      if (profileFilter) params.profile_id = profileFilter
      const res = await discoveryService.getStats(profileFilter)
      setStats(res.data ?? res)
    } catch { /* silent */ }
  }, [profileFilter])

  const loadProfiles = useCallback(async () => {
    try {
      const res = await discoveryService.getProfiles()
      setProfiles(res.data ?? res ?? [])
    } catch { /* silent */ }
  }, [])

  const loadDiscovered = useCallback(async () => {
    try {
      const params = { limit: perPage, offset: (page - 1) * perPage }
      if (statusFilter) params.status = statusFilter
      if (profileFilter) params.profile_id = profileFilter
      const res = await discoveryService.getAll(params)
      const data = res.data ?? res
      if (Array.isArray(data)) {
        setDiscovered(data)
        setDiscoveredTotal(data.length)
      } else {
        setDiscovered(data.items ?? [])
        setDiscoveredTotal(data.total ?? data.items?.length ?? 0)
      }
    } catch { /* silent */ }
  }, [page, perPage, statusFilter, profileFilter])

  const loadRuns = useCallback(async () => {
    try {
      const params = { limit: 50 }
      if (profileFilter) params.profile_id = profileFilter
      const res = await discoveryService.getRuns(params)
      const data = res.data ?? res
      if (Array.isArray(data)) {
        setRuns(data)
        setRunsTotal(data.length)
      } else {
        setRuns(data.items ?? [])
        setRunsTotal(data.total ?? data.items?.length ?? 0)
      }
    } catch { /* silent */ }
  }, [profileFilter])

  const loadAll = useCallback(async () => {
    setLoading(true)
    await Promise.all([loadStats(), loadProfiles(), loadDiscovered(), loadRuns()])
    setLoading(false)
  }, [loadStats, loadProfiles, loadDiscovered, loadRuns])

  useEffect(() => { loadAll() }, [loadAll])
  useEffect(() => { loadDiscovered() }, [page, perPage, statusFilter, profileFilter])
  useEffect(() => { loadStats(); loadRuns() }, [profileFilter])

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
    setSelectedItem(null)
    setPage(1)
    if (tabId !== 'discovered') {
      setStatusFilter(null)
    }
    setSearchParams({ tab: tabId, ...(profileFilter ? { profile: profileFilter } : {}) })
  }

  // Filter helpers
  const handleStatusFilter = (status) => {
    setStatusFilter(prev => prev === status ? null : status)
    setPage(1)
  }

  const handleProfileFilter = (id) => {
    setProfileFilter(prev => prev === id ? null : id)
    setPage(1)
    setStatusFilter(null)
  }

  const handleRetryScan = async (target, port) => {
    try {
      setScanning(true)
      await discoveryService.scan({ targets: [`${target}:${port}`], ports: [port], timeout: 10 })
    } catch (error) {
      showError(error.message || t('discovery.scanFailed'))
      setScanning(false)
    }
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
      await discoveryService.scan(formData)
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

  const handleExport = async (format = 'csv') => {
    try {
      const blob = await discoveryService.export(format)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `discovered_certificates.${format}`
      a.click()
      window.URL.revokeObjectURL(url)
      showSuccess(t('discovery.exportSuccess'))
    } catch (error) {
      showError(error.message || t('discovery.exportFailed'))
    }
  }

  const handleBulkResolveDns = async () => {
    try {
      const res = await discoveryService.bulkResolveDns()
      const data = res.data ?? res
      showSuccess(t('discovery.bulkDnsSuccess', { updated: data.updated, total: data.total }))
      loadDiscovered()
    } catch (error) {
      showError(error.message)
    }
  }

  // ── Stats bar (clickable → filter) ─────────────────────
  const statsBar = useMemo(() => [
    { icon: Globe, label: t('common.total'), value: stats.total, variant: 'primary',
      filterValue: null },
    { icon: ShieldCheck, label: t('discovery.managed'), value: stats.managed, variant: 'success',
      filterValue: 'managed' },
    { icon: Warning, label: t('discovery.unmanaged'), value: stats.unmanaged, variant: 'warning',
      filterValue: 'unmanaged' },
    { icon: XCircle, label: t('common.expired'), value: stats.expired, variant: 'danger' },
    ...(stats.expiring_soon > 0 ? [{ icon: Clock, label: t('discovery.expiringSoon'), value: stats.expiring_soon, variant: 'warning' }] : []),
    ...(stats.errors > 0 ? [{ icon: WarningCircle, label: t('common.error'), value: stats.errors, variant: 'danger',
      filterValue: 'error' }] : []),
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
        const isError = row.status === 'error'
        return (
          <div className="flex items-center gap-2">
            <div className={cn(
              "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
              isError ? 'icon-bg-red' : row.status === 'managed' ? 'icon-bg-emerald' : 'icon-bg-orange'
            )}>
              {isError ? <XCircle size={14} weight="duotone" /> : <Certificate size={14} weight="duotone" />}
            </div>
            <div className="truncate">
              <span className={cn("font-medium truncate", isError && "text-status-danger")}>{isError ? `${row.target}:${row.port}` : name}</span>
              {isError && row.scan_error && (
                <div className="text-2xs text-text-tertiary truncate" title={row.scan_error}>{row.scan_error}</div>
              )}
            </div>
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
        <div className="text-sm">
          <span className="text-text-secondary">{val || '—'}:{row.port || 443}</span>
          {row.sni_hostname && (
            <div className="text-2xs text-accent-primary truncate" title={`SNI: ${row.sni_hostname}`}>SNI: {row.sni_hostname}</div>
          )}
          {row.dns_hostname && (
            <div className="text-2xs text-text-tertiary truncate">{row.dns_hostname}</div>
          )}
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
      width: 80,
      render: (_, row) => (
        <div className="flex items-center gap-1">
          {row.status === 'error' && canWrite('certificates') && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); handleRetryScan(row.target, row.port) }}
              className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-tertiary hover:text-accent-primary transition-colors"
              title={t('discovery.retry')}
            >
              <ArrowCounterClockwise size={14} />
            </button>
          )}
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
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <span className="text-sm text-text-secondary">{val ?? 0}</span>
          {row.errors_count > 0 && (
            <Badge variant="danger" size="sm">{row.errors_count} err</Badge>
          )}
        </div>
      )
    },
    {
      key: 'targets_scanned',
      header: t('discovery.targetsScanned'),
      sortable: true,
      priority: 4,
      hideOnMobile: true,
      render: (val) => (
        <span className="text-sm text-text-secondary">{val ?? '—'}</span>
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

  // ── Filter Bar Component ─────────────────────────────
  const FilterBar = () => {
    const activeProfile = profiles.find(p => p.id === profileFilter)
    const statusFilters = [
      { id: null, label: t('common.all'), icon: Globe },
      { id: 'managed', label: t('discovery.managed'), icon: ShieldCheck, variant: 'success' },
      { id: 'unmanaged', label: t('discovery.unmanaged'), icon: Warning, variant: 'warning' },
      { id: 'error', label: t('common.error'), icon: WarningCircle, variant: 'danger' },
    ]
    return (
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-border bg-bg-secondary/50">
        {/* Status pills */}
        <div className="flex items-center gap-1">
          <Funnel size={13} className="text-text-tertiary mr-0.5" />
          {statusFilters.map(f => (
            <button
              key={f.id ?? 'all'}
              type="button"
              onClick={() => { setStatusFilter(f.id); setPage(1) }}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all',
                statusFilter === f.id
                  ? 'bg-accent-primary text-white shadow-sm'
                  : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
              )}
            >
              <f.icon size={12} />
              {f.label}
            </button>
          ))}
        </div>

        {/* Profile filter */}
        {profiles.length > 0 && (
          <>
            <div className="w-px h-5 bg-border mx-1" />
            <select
              value={profileFilter ?? ''}
              onChange={(e) => { handleProfileFilter(e.target.value ? parseInt(e.target.value) : null) }}
              className="text-xs bg-bg-secondary border border-border rounded-lg px-2 py-1 text-text-secondary focus:border-accent-primary focus:outline-none"
            >
              <option value="">{t('discovery.allProfiles')}</option>
              {profiles.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </>
        )}

        {/* Active filter indicator */}
        {(statusFilter || profileFilter) && (
          <>
            <div className="w-px h-5 bg-border mx-1" />
            <button
              type="button"
              onClick={() => { setStatusFilter(null); setProfileFilter(null); setPage(1) }}
              className="flex items-center gap-1 px-2 py-1 rounded-full text-xs text-accent-primary hover:bg-accent-op10 transition-colors"
            >
              <XCircle size={12} />
              {t('discovery.clearFilters')}
            </button>
            {activeProfile && (
              <span className="text-xs text-text-tertiary">
                {t('discovery.filterByProfile')}: <span className="font-medium text-text-secondary">{activeProfile.name}</span>
              </span>
            )}
          </>
        )}
      </div>
    )
  }

  // ── Tab content ───────────────────────────────────────
  const renderContent = () => {
    switch (activeTab) {
      case 'discovered':
        return (
          <div className="flex flex-col h-full">
            <FilterBar />
            <div className="flex-1 min-h-0">
              <ResponsiveDataTable
            data={discovered}
            columns={discoveredColumns}
            loading={loading}
            selectedId={selectedItem?.id}
            onRowClick={(item) => item ? setSelectedItem(item) : setSelectedItem(null)}
            searchable
            searchPlaceholder={t('discovery.searchDiscovered')}
            searchKeys={['subject', 'target', 'issuer', 'serial_number']}
            columnStorageKey="ucm-discovery-columns"
            sortable
            defaultSort={{ key: 'cn', direction: 'asc' }}
            pagination={{
              page,
              total: discoveredTotal,
              perPage,
              onChange: setPage,
              onPerPageChange: (v) => { setPerPage(v); setPage(1) }
            }}
            toolbarActions={canWrite('certificates') && (
              isMobile ? (
                <Button type="button" size="lg" onClick={() => setShowQuickScan(true)} disabled={scanning} className="w-11 h-11 p-0">
                  <MagnifyingGlass size={22} weight="bold" />
                </Button>
              ) : (
                <div className="flex items-center gap-2">
                  {scanning && scanProgress && scanProgress.total > 0 && (
                    <div className="flex items-center gap-2 text-xs text-text-secondary mr-1">
                      <div className="w-24 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
                        <div
                          className="h-full bg-accent-primary rounded-full transition-all"
                          style={{ width: `${Math.round(scanProgress.scanned / scanProgress.total * 100)}%` }}
                        />
                      </div>
                      <span className="tabular-nums whitespace-nowrap">{scanProgress.scanned}/{scanProgress.total}</span>
                    </div>
                  )}
                  {discovered.length > 0 && (
                    <>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={handleBulkResolveDns}
                        title={t('discovery.bulkResolveDns')}
                      >
                        <MapPin size={14} />
                        {t('discovery.bulkResolveDns')}
                      </Button>
                      {stats.errors > 0 && (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={async () => {
                            const errorEntries = discovered.filter(d => d.status === 'error')
                            if (!errorEntries.length) return
                            const targets = errorEntries.map(e => `${e.target}:${e.port}`)
                            try {
                              setScanning(true)
                              await discoveryService.scan({ targets, timeout: 10 })
                            } catch (err) {
                              showError(err.message || t('discovery.scanFailed'))
                              setScanning(false)
                            }
                          }}
                          className="text-status-danger hover:text-status-danger"
                          title={t('discovery.retryAllErrors')}
                        >
                          <ArrowCounterClockwise size={14} />
                          {t('discovery.retryAllErrors')}
                        </Button>
                      )}
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => handleExport('csv')}
                      >
                        <Export size={14} />
                        {t('common.export')}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setDeleteConfirm({ type: 'all' })}
                        className="text-status-danger hover:text-status-danger"
                      >
                        <Trash size={14} />
                        {t('discovery.deleteAll')}
                      </Button>
                    </>
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
            </div>
          </div>
        )

      case 'profiles':
        return (
          <ResponsiveDataTable
            data={profiles}
            columns={profileColumns}
            loading={loading}
            selectedId={selectedItem?.id}
            onRowClick={(item) => item ? setSelectedItem(item) : setSelectedItem(null)}
            searchable
            searchPlaceholder={t('discovery.searchProfiles')}
            searchKeys={['name', 'description', 'targets']}
            columnStorageKey="ucm-discovery-profiles-columns"
            sortable
            defaultSort={{ key: 'name', direction: 'asc' }}
            pagination={{
              page,
              total: profiles.length,
              perPage,
              onChange: setPage,
              onPerPageChange: (v) => { setPerPage(v); setPage(1) }
            }}
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
            selectedId={selectedItem?.id}
            onRowClick={(item) => item ? setSelectedItem(item) : setSelectedItem(null)}
            searchable
            searchPlaceholder={t('discovery.searchHistory')}
            searchKeys={['profile_name', 'status']}
            columnStorageKey="ucm-discovery-history-columns"
            sortable
            defaultSort={{ key: 'started_at', direction: 'desc' }}
            pagination={{
              page,
              total: runsTotal,
              perPage,
              onChange: setPage,
              onPerPageChange: (v) => { setPerPage(v); setPage(1) }
            }}
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

  // ── Detail panel content ────────────────────────────────
  const getSlideOverTitle = () => {
    if (!selectedItem) return ''
    if (activeTab === 'discovered') return t('discovery.certDetails')
    if (activeTab === 'profiles') return t('discovery.profileDetails')
    return t('discovery.runDetails')
  }

  const getSlideOverContent = () => {
    if (!selectedItem) return null
    if (activeTab === 'discovered') return <DiscoveredDetailPanel item={selectedItem} t={t} />
    if (activeTab === 'profiles') return <ProfileDetailPanel item={selectedItem} t={t} />
    return <RunDetailPanel item={selectedItem} t={t} />
  }

  return (
    <>
      <ResponsiveLayout
        title={t('discovery.title')}
        subtitle={subtitle}
        icon={Globe}
        stats={statsBar}
        activeStatFilter={statusFilter}
        onStatClick={(filterValue) => handleStatusFilter(filterValue)}
        tabs={tabsWithCounts}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        tabLayout="sidebar"
        helpPageKey="discovery"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Globe size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('discovery.selectItem')}</p>
          </div>
        }
        slideOverOpen={!!selectedItem}
        onSlideOverClose={() => setSelectedItem(null)}
        slideOverTitle={getSlideOverTitle()}
        slideOverContent={getSlideOverContent()}
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
  const [targets, setTargets] = useState([])
  const [ports, setPorts] = useState(['443'])
  const [timeout, setTimeout_] = useState(5)
  const [maxWorkers, setMaxWorkers] = useState(20)
  const [resolveDns, setResolveDns] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)

  useEffect(() => {
    if (open) {
      setTargets([]); setPorts(['443']); setTimeout_(5)
      setMaxWorkers(20); setResolveDns(false); setShowAdvanced(false)
    }
  }, [open])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!targets.length) return
    const portList = ports.map(s => parseInt(s)).filter(n => n > 0 && n <= 65535)
    onScan({
      targets,
      ports: portList.length ? portList : [443],
      timeout,
      max_workers: maxWorkers,
      resolve_dns: resolveDns,
    })
  }

  const portPresets = [
    { label: 'HTTPS', ports: ['443'] },
    { label: 'HTTPS + Alt', ports: ['443', '8443'] },
    { label: t('discovery.allCommon'), ports: ['443', '8443', '8080', '636', '993', '995', '465', '587'] },
  ]

  const portsMatch = (a, b) => a.length === b.length && a.every((v, i) => v === b[i])

  return (
    <Modal open={open} onClose={onClose} title={t('discovery.quickScan')}>
      <form onSubmit={handleSubmit} className="p-5 space-y-5">
        {/* ── Targets Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <Crosshair size={14} weight="bold" />
            {t('discovery.targets')}
          </div>
          <TagsInput
            value={targets}
            onChange={setTargets}
            placeholder={t('discovery.targetsPlaceholder')}
            helperText={t('discovery.targetsTagHelp')}
          />
        </div>

        {/* ── Ports Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <Plugs size={14} weight="bold" />
            {t('discovery.ports')}
          </div>
          <div className="flex flex-wrap gap-2">
            {portPresets.map((preset) => (
              <button
                key={preset.label}
                type="button"
                className={cn(
                  'flex flex-col items-center px-3.5 py-2 rounded-lg border text-xs transition-all',
                  portsMatch(ports, preset.ports)
                    ? 'bg-accent-op10 border-accent-primary text-accent-primary ring-1 ring-accent-primary'
                    : 'border-border bg-bg-secondary text-text-secondary hover:border-text-tertiary hover:bg-bg-tertiary'
                )}
                onClick={() => setPorts(preset.ports)}
              >
                <span className="font-medium">{preset.label}</span>
                <span className="text-2xs opacity-60 mt-0.5">{preset.ports.join(', ')}</span>
              </button>
            ))}
          </div>
          <TagsInput
            value={ports}
            onChange={setPorts}
            placeholder="443, 8443, 636"
            helperText={t('discovery.portsHelpDetailed')}
            validate={(v) => { const n = parseInt(v); return n > 0 && n <= 65535 }}
          />
        </div>

        {/* ── Advanced Options ── */}
        <div className="rounded-lg border border-border overflow-hidden">
          <button
            type="button"
            className="flex items-center justify-between w-full px-4 py-2.5 text-sm text-text-secondary hover:bg-bg-secondary transition-colors"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            <span className="flex items-center gap-2">
              <GearSix size={15} weight="bold" />
              {t('discovery.advancedOptions')}
            </span>
            <CaretDown size={14} className={cn("transition-transform duration-200", showAdvanced && "rotate-180")} />
          </button>

          {showAdvanced && (
            <div className="px-4 pb-4 pt-1 space-y-4 border-t border-border bg-secondary-op50">
              <ToggleSwitch
                checked={resolveDns}
                onChange={setResolveDns}
                label={t('discovery.reverseDns')}
                description="PTR records"
                size="sm"
              />
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label={t('discovery.timeout')}
                  type="number"
                  value={timeout}
                  onChange={(e) => setTimeout_(Math.min(Math.max(parseInt(e.target.value) || 1, 1), 30))}
                  min={1} max={30}
                  helperText="1–30s"
                />
                <Input
                  label={t('discovery.concurrency')}
                  type="number"
                  value={maxWorkers}
                  onChange={(e) => setMaxWorkers(Math.min(Math.max(parseInt(e.target.value) || 1, 1), 50))}
                  min={1} max={50}
                  helperText="1–50"
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={scanning || !targets.length}>
            {scanning ? <ArrowsClockwise size={14} className="animate-spin" /> : <Play size={14} weight="fill" />}
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
  const [targets, setTargets] = useState([])
  const [ports, setPorts] = useState(['443'])
  const [schedule, setSchedule] = useState('0')
  const [notifyEmail, setNotifyEmail] = useState('')
  const [timeout, setTimeout_] = useState(5)
  const [maxWorkers, setMaxWorkers] = useState(20)
  const [resolveDns, setResolveDns] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)

  useEffect(() => {
    if (open) {
      if (profile) {
        setName(profile.name || '')
        setDescription(profile.description || '')
        const tList = Array.isArray(profile.targets) ? profile.targets
          : (typeof profile.targets === 'string' ? (() => { try { return JSON.parse(profile.targets) } catch { return profile.targets.split(',') } })() : [])
        setTargets(tList.map(s => s.trim()).filter(Boolean))
        const pList = Array.isArray(profile.ports) ? profile.ports
          : (typeof profile.ports === 'string' ? (() => { try { return JSON.parse(profile.ports) } catch { return profile.ports.split(',') } })() : [443])
        setPorts(pList.map(String))
        setSchedule(String(profile.schedule_interval_minutes || 0))
        setNotifyEmail(profile.notify_email || '')
        setTimeout_(profile.timeout || 5)
        setMaxWorkers(profile.max_workers || 20)
        setResolveDns(profile.resolve_dns || false)
        setShowAdvanced(!!(profile.resolve_dns || profile.timeout !== 5 || profile.max_workers !== 20))
      } else {
        setName(''); setDescription(''); setTargets([]); setPorts(['443'])
        setSchedule('0'); setNotifyEmail('')
        setTimeout_(5); setMaxWorkers(20); setResolveDns(false); setShowAdvanced(false)
      }
    }
  }, [open, profile])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!name.trim() || !targets.length) return
    const portList = ports.map(s => parseInt(s)).filter(n => n > 0 && n <= 65535)
    onSave({
      name: name.trim(),
      description: description.trim(),
      targets,
      ports: portList.length ? portList : [443],
      schedule_interval_minutes: parseInt(schedule) || 0,
      schedule_enabled: parseInt(schedule) > 0,
      timeout,
      max_workers: maxWorkers,
      resolve_dns: resolveDns,
      notify_email: notifyEmail.trim() || null,
    })
  }

  const scheduleOptions = [
    { value: '0', label: t('discovery.manual'), icon: '—' },
    { value: '60', label: t('discovery.every1h'), icon: '1h' },
    { value: '360', label: t('discovery.every6h'), icon: '6h' },
    { value: '720', label: t('discovery.every12h'), icon: '12h' },
    { value: '1440', label: t('discovery.every24h'), icon: '24h' },
    { value: '10080', label: t('discovery.every7d'), icon: '7d' },
  ]

  const portPresets = [
    { label: 'HTTPS', ports: ['443'] },
    { label: 'HTTPS + Alt', ports: ['443', '8443'] },
    { label: t('discovery.allCommon'), ports: ['443', '8443', '8080', '636', '993', '995', '465', '587'] },
  ]

  const portsMatch = (a, b) => a.length === b.length && a.every((v, i) => v === b[i])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={profile ? t('discovery.editProfile') : t('discovery.createProfile')}
    >
      <form onSubmit={handleSubmit} className="p-5 space-y-5 max-h-[75vh] overflow-y-auto">
        {/* ── Identity Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <FolderOpen size={14} weight="bold" />
            {t('discovery.profile')}
          </div>
          <div className="grid grid-cols-1 gap-3">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder={t('discovery.profileNamePlaceholder')}
              label={t('common.name')}
            />
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('discovery.profileDescPlaceholder')}
              label={t('common.description')}
            />
          </div>
        </div>

        {/* ── Targets Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <Crosshair size={14} weight="bold" />
            {t('discovery.targets')}
          </div>
          <TagsInput
            value={targets}
            onChange={setTargets}
            placeholder={t('discovery.targetsPlaceholder')}
            helperText={t('discovery.targetsTagHelp')}
          />
        </div>

        {/* ── Ports Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <Plugs size={14} weight="bold" />
            {t('discovery.ports')}
          </div>
          <div className="flex flex-wrap gap-2">
            {portPresets.map((preset) => (
              <button
                key={preset.label}
                type="button"
                className={cn(
                  'flex flex-col items-center px-3.5 py-2 rounded-lg border text-xs transition-all',
                  portsMatch(ports, preset.ports)
                    ? 'bg-accent-op10 border-accent-primary text-accent-primary ring-1 ring-accent-primary'
                    : 'border-border bg-bg-secondary text-text-secondary hover:border-text-tertiary hover:bg-bg-tertiary'
                )}
                onClick={() => setPorts(preset.ports)}
              >
                <span className="font-medium">{preset.label}</span>
                <span className="text-2xs opacity-60 mt-0.5">{preset.ports.join(', ')}</span>
              </button>
            ))}
          </div>
          <TagsInput
            value={ports}
            onChange={setPorts}
            placeholder="443, 8443, 636"
            helperText={t('discovery.portsHelpDetailed')}
            validate={(v) => { const n = parseInt(v); return n > 0 && n <= 65535 }}
          />
        </div>

        {/* ── Schedule Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <CalendarBlank size={14} weight="bold" />
            {t('discovery.schedule')}
          </div>
          <div className="flex flex-wrap gap-2">
            {scheduleOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={cn(
                  'px-3 py-1.5 rounded-lg border text-xs font-medium transition-all',
                  schedule === opt.value
                    ? 'bg-accent-op10 border-accent-primary text-accent-primary ring-1 ring-accent-primary'
                    : 'border-border bg-bg-secondary text-text-secondary hover:border-text-tertiary hover:bg-bg-tertiary'
                )}
                onClick={() => setSchedule(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {schedule !== '0' && (
            <Input
              label={t('discovery.notifyEmail')}
              value={notifyEmail}
              onChange={(e) => setNotifyEmail(e.target.value)}
              placeholder="admin@example.com"
              type="email"
              helperText={t('discovery.notifyOnNew')}
            />
          )}
        </div>

        {/* ── Advanced Options ── */}
        <div className="rounded-lg border border-border overflow-hidden">
          <button
            type="button"
            className="flex items-center justify-between w-full px-4 py-2.5 text-sm text-text-secondary hover:bg-bg-secondary transition-colors"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            <span className="flex items-center gap-2">
              <GearSix size={15} weight="bold" />
              {t('discovery.advancedOptions')}
            </span>
            <CaretDown size={14} className={cn("transition-transform duration-200", showAdvanced && "rotate-180")} />
          </button>

          {showAdvanced && (
            <div className="px-4 pb-4 pt-1 space-y-4 border-t border-border bg-secondary-op50">
              <ToggleSwitch
                checked={resolveDns}
                onChange={setResolveDns}
                label={t('discovery.reverseDns')}
                description="PTR records"
                size="sm"
              />
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label={t('discovery.timeout')}
                  type="number"
                  value={timeout}
                  onChange={(e) => setTimeout_(Math.min(Math.max(parseInt(e.target.value) || 1, 1), 30))}
                  min={1} max={30}
                  helperText="1–30s"
                />
                <Input
                  label={t('discovery.concurrency')}
                  type="number"
                  value={maxWorkers}
                  onChange={(e) => setMaxWorkers(Math.min(Math.max(parseInt(e.target.value) || 1, 1), 50))}
                  min={1} max={50}
                  helperText="1–50"
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={!name.trim() || !targets.length}>
            {profile ? t('common.save') : t('common.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}


// ════════════════════════════════════════════════════════
// Detail Panels
// ════════════════════════════════════════════════════════

// OID-to-label mapping for DN fields
const DN_LABELS = {
  'CN': 'Common Name',
  'O': 'Organization',
  'OU': 'Org. Unit',
  'L': 'Locality',
  'ST': 'State',
  'C': 'Country',
  'SN': 'Surname',
  'GN': 'Given Name',
  'DC': 'Domain Component',
  '1.2.840.113549.1.9.1': 'Email',
  'emailAddress': 'Email',
  'E': 'Email',
  'STREET': 'Street',
  'SERIALNUMBER': 'Serial',
}

function FormattedDN({ dn }) {
  if (!dn) return <span className="text-xs text-text-tertiary">—</span>
  // Parse DN: handles both KEY=value and OID=value formats
  const parts = []
  const regex = /([\w.]+)=([^,]*(?:,(?!\s*[A-Z0-9.]+=).*)*)/g
  let match
  while ((match = regex.exec(dn)) !== null) {
    parts.push({ key: match[1].trim(), value: match[2].trim() })
  }
  if (!parts.length) return <span className="text-xs font-mono text-text-primary break-all">{dn}</span>

  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
      {parts.map((p, i) => (
        <Fragment key={i}>
          <span className="text-2xs text-text-tertiary whitespace-nowrap py-0.5 text-right">
            {DN_LABELS[p.key] || p.key}
          </span>
          <span className="text-xs font-medium text-text-primary break-all py-0.5">
            {p.value}
          </span>
        </Fragment>
      ))}
    </div>
  )
}

function DiscoveredDetailPanel({ item, t }) {
  const extractCN = (s) => { const m = s?.match(/CN=([^,]+)/); return m ? m[1] : null }
  const isError = item.status === 'error'
  const name = isError ? `${item.target}:${item.port || 443}` : (extractCN(item.subject) || item.target || t('common.unknown'))
  const days = item.days_until_expiry
  const isExpired = item.is_expired
  const isExpiring = !isExpired && days != null && days <= 30

  const expiryValue = (() => {
    const dateStr = item.not_after ? formatDate(item.not_after) : '—'
    const suffix = isExpired ? ` (${t('common.expired')})` : isExpiring ? ` (${days}d)` : ''
    return dateStr + suffix
  })()

  // Error troubleshooting hints
  const getErrorHint = (error) => {
    if (!error) return null
    const e = error.toLowerCase()
    if (e.includes('unrecognized_name') || e.includes('sni'))
      return { icon: '🔒', hint: t('discovery.errorHintSni') }
    if (e.includes('connection refused') || e.includes('errno 111'))
      return { icon: '🚫', hint: t('discovery.errorHintRefused') }
    if (e.includes('timed out') || e.includes('errno 110'))
      return { icon: '⏱️', hint: t('discovery.errorHintTimeout') }
    if (e.includes('no route') || e.includes('errno 113') || e.includes('network unreachable'))
      return { icon: '🌐', hint: t('discovery.errorHintNoRoute') }
    if (e.includes('dns') || e.includes('name resolution') || e.includes('getaddrinfo'))
      return { icon: '📡', hint: t('discovery.errorHintDns') }
    if (e.includes('reset') || e.includes('errno 104'))
      return { icon: '⛔', hint: t('discovery.errorHintReset') }
    return null
  }

  if (isError) {
    const errorHint = getErrorHint(item.scan_error)
    return (
      <div className="p-4 space-y-4">
        <CompactSection title={t('common.error')}>
          <div className="space-y-3">
            <CompactGrid>
              <CompactField label={t('discovery.host')} value={`${item.target}:${item.port || 443}`} mono />
              {item.dns_hostname && (
                <CompactField label={t('discovery.dnsHostname')} value={item.dns_hostname} />
              )}
              <CompactField
                label={t('common.status')}
                value={<Badge variant="danger" size="sm" icon={WarningCircle} dot>{t('common.error')}</Badge>}
              />
            </CompactGrid>
            <div className="rounded-lg border border-status-danger/20 bg-status-danger/5 p-3">
              <div className="text-xs font-mono text-status-danger break-all">{item.scan_error}</div>
            </div>
            {errorHint && (
              <div className="rounded-lg border border-border bg-bg-tertiary p-3 flex items-start gap-2">
                <span className="text-base shrink-0">{errorHint.icon}</span>
                <p className="text-xs text-text-secondary leading-relaxed">{errorHint.hint}</p>
              </div>
            )}
          </div>
        </CompactSection>
        <CompactSection title={t('discovery.scanInfo')}>
          <CompactGrid>
            <CompactField label={t('discovery.firstSeen')} value={item.first_seen ? formatDate(item.first_seen) : '—'} />
            <CompactField label={t('discovery.lastSeen')} value={item.last_seen ? formatDate(item.last_seen) : '—'} />
          </CompactGrid>
        </CompactSection>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4">
      <CompactSection title={t('discovery.certInfo')}>
        <CompactGrid>
          <CompactField label={t('common.commonName')} value={name} />
          <CompactField label={t('discovery.host')} value={`${item.target}:${item.port || 443}`} />
          {item.sni_hostname && (
            <CompactField label="SNI" value={item.sni_hostname} mono />
          )}
          {item.dns_hostname && (
            <CompactField label={t('discovery.dnsHostname')} value={item.dns_hostname} />
          )}
          <CompactField
            label={t('common.status')}
            value={
              <Badge
                variant={item.status === 'managed' ? 'success' : 'warning'}
                size="sm"
                icon={item.status === 'managed' ? ShieldCheck : Warning}
                dot
              >
                {item.status === 'managed' ? t('discovery.managed') : t('discovery.unmanaged')}
              </Badge>
            }
          />
          <CompactField label={t('common.serialNumber')} value={item.serial_number || '—'} mono />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.subject')} icon={IdentificationBadge} iconClass="icon-bg-blue">
        <FormattedDN dn={item.subject} />
      </CompactSection>

      <CompactSection title={t('common.issuer')} icon={Stamp} iconClass="icon-bg-violet">
        <FormattedDN dn={item.issuer} />
      </CompactSection>

      {(item.san_dns_names?.length > 0 || item.san_ip_addresses?.length > 0) && (
        <CompactSection title={t('discovery.subjectAltNames')}>
          <div className="space-y-2">
            {item.san_dns_names?.length > 0 && (
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">DNS</div>
                <div className="flex flex-wrap gap-1">
                  {item.san_dns_names.map((san, i) => (
                    <Badge key={i} variant="secondary" size="sm">{san}</Badge>
                  ))}
                </div>
              </div>
            )}
            {item.san_ip_addresses?.length > 0 && (
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">IP</div>
                <div className="flex flex-wrap gap-1">
                  {item.san_ip_addresses.map((san, i) => (
                    <Badge key={i} variant="secondary" size="sm">{san}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </CompactSection>
      )}

      <CompactSection title={t('common.validity')}>
        <CompactGrid>
          <CompactField label={t('common.notBefore')} value={item.not_before ? formatDate(item.not_before) : '—'} />
          <CompactField
            label={t('common.notAfter')}
            value={expiryValue}
            className={isExpired ? 'text-status-danger' : isExpiring ? 'text-status-warning' : ''}
          />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.fingerprint')}>
        <div>
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">SHA-256</div>
          <div className="text-xs font-mono text-text-primary break-all">{item.fingerprint_sha256 || '—'}</div>
        </div>
      </CompactSection>

      <CompactSection title={t('discovery.scanInfo')}>
        <CompactGrid>
          <CompactField label={t('discovery.firstSeen')} value={item.first_seen ? formatDate(item.first_seen) : '—'} />
          <CompactField label={t('discovery.lastSeen')} value={item.last_seen ? formatDate(item.last_seen) : '—'} />
          {item.last_changed_at && (
            <CompactField label={t('discovery.lastChanged')} value={formatDate(item.last_changed_at)} />
          )}
          {item.scan_error && (
            <CompactField label={t('common.error')} value={item.scan_error} />
          )}
        </CompactGrid>
      </CompactSection>
    </div>
  )
}

function ProfileDetailPanel({ item, t }) {
  const targets = item.targets_list || (typeof item.targets === 'string' ? (() => { try { return JSON.parse(item.targets) } catch { return item.targets.split(',') } })() : item.targets) || []
  const ports = item.ports_list || (typeof item.ports === 'string' ? (() => { try { return JSON.parse(item.ports) } catch { return item.ports.split(',') } })() : item.ports) || [443]

  const scheduleLabel = (val) => {
    if (!val) return t('discovery.manual')
    const h = Math.round(val / 3600)
    if (h < 24) return `${h}h`
    return `${Math.round(h / 24)}d`
  }

  return (
    <div className="p-4 space-y-4">
      <CompactSection title={t('common.info')}>
        <CompactGrid>
          <CompactField label={t('common.name')} value={item.name} />
          {item.description && <CompactField label={t('common.description')} value={item.description} />}
          <CompactField
            label={t('common.status')}
            value={
              <Badge variant={item.enabled ? 'success' : 'secondary'} size="sm" dot>
                {item.enabled ? t('common.enabled') : t('common.disabled')}
              </Badge>
            }
          />
          <CompactField label={t('discovery.schedule')} value={scheduleLabel(item.schedule_interval)} />
          {item.notify_email && <CompactField label={t('discovery.notifyEmail')} value={item.notify_email} />}
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('discovery.targets')}>
        <div className="space-y-1">
          {targets.map((target, i) => (
            <div key={i} className="text-sm font-mono text-text-secondary px-2 py-1 bg-bg-tertiary rounded">
              {target}
            </div>
          ))}
        </div>
      </CompactSection>

      <CompactSection title={t('discovery.ports')}>
        <div className="flex flex-wrap gap-1.5">
          {ports.map((port, i) => (
            <Badge key={i} variant="secondary" size="sm">{port}</Badge>
          ))}
        </div>
      </CompactSection>

      {item.last_scan_at && (
        <CompactSection title={t('discovery.lastScan')}>
          <CompactGrid>
            <CompactField label={t('common.date')} value={formatDate(item.last_scan_at)} />
          </CompactGrid>
        </CompactSection>
      )}
    </div>
  )
}

function RunDetailPanel({ item, t }) {
  const duration = item.duration_seconds
  const durationStr = duration == null ? '—' : duration < 60 ? `${Math.round(duration)}s` : `${Math.round(duration / 60)}m ${Math.round(duration % 60)}s`

  return (
    <div className="p-4 space-y-4">
      <CompactSection title={t('common.info')}>
        <CompactGrid>
          <CompactField label={t('discovery.profile')} value={item.profile_name || t('discovery.adHocScan')} />
          <CompactField
            label={t('common.status')}
            value={
              <Badge
                variant={item.status === 'completed' ? 'success' : item.status === 'running' ? 'info' : 'danger'}
                size="sm"
                icon={item.status === 'completed' ? CheckCircle : item.status === 'running' ? ArrowsClockwise : XCircle}
                dot={item.status === 'running'}
              >
                {item.status === 'completed' ? t('common.completed') : item.status === 'running' ? t('discovery.scanning') : t('common.failed')}
              </Badge>
            }
          />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('discovery.scanResults')}>
        <CompactGrid>
          <CompactField label={t('discovery.certsFound')} value={item.certs_found ?? 0} />
          <CompactField label={t('discovery.targetsScanned')} value={item.targets_scanned ?? 0} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.timeline')}>
        <CompactGrid>
          <CompactField label={t('common.started')} value={item.started_at ? formatDate(item.started_at) : '—'} />
          <CompactField label={t('common.completed')} value={item.completed_at ? formatDate(item.completed_at) : '—'} />
          <CompactField label={t('discovery.duration')} value={durationStr} />
        </CompactGrid>
      </CompactSection>

      {item.error_message && (
        <CompactSection title={t('common.error')}>
          <div className="text-sm text-status-danger bg-bg-tertiary rounded p-2 font-mono">
            {item.error_message}
          </div>
        </CompactSection>
      )}
    </div>
  )
}
