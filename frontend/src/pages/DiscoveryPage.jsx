/**
 * DiscoveryPage — Certificate Discovery with scan profiles, results & history
 * Pattern: CSRsPage (stats + sidebar tabs + table) 
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Globe, MagnifyingGlass, ShieldCheck, Warning, WarningCircle, Clock,
  ArrowsClockwise, Trash, Play, Plus, CheckCircle, XCircle,
  ClockCounterClockwise, FolderOpen, Pencil,
  Certificate, Export, MapPin, ArrowCounterClockwise,
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable,
  Badge, Button, HelpCard,
} from '../components'
import { ConfirmModal } from '../components/FormModal'
import { discoveryService } from '../services'
import { useNotification } from '../contexts'
import { useMobile } from '../contexts/MobileContext'
import { usePermission, useWebSocket } from '../hooks'
import { formatDate, cn, extractCN, downloadBlob } from '../lib/utils'
import QuickScanModal from './discovery/QuickScanModal'
import ProfileFormModal from './discovery/ProfileFormModal'
import DiscoveryFilterBar from './discovery/DiscoveryFilterBar'
import DiscoveredDetailPanel from './discovery/DiscoveredDetailPanel'
import ProfileDetailPanel from './discovery/ProfileDetailPanel'
import RunDetailPanel from './discovery/RunDetailPanel'

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
  const [statusFilter, setStatusFilter] = useState([])   // [] = all, ['managed', 'unmanaged', 'error']
  const [profileFilter, setProfileFilter] = useState(null)  // null = all, profile id

  // ── Data loaders ──────────────────────────────────────
  const loadStats = useCallback(async () => {
    try {
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
      if (statusFilter.length > 0) params.status = statusFilter
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
  }, [page, perPage, JSON.stringify(statusFilter), profileFilter])

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
      setStatusFilter([])
    }
    setSearchParams({ tab: tabId, ...(profileFilter ? { profile: profileFilter } : {}) })
  }

  // Filter helpers
  const handleStatusFilter = (status) => {
    setStatusFilter(prev => {
      if (prev.includes(status)) return prev.filter(v => v !== status)
      return [...prev, status]
    })
    setPage(1)
  }

  const handleProfileFilter = (id) => {
    setProfileFilter(prev => prev === id ? null : id)
    setPage(1)
    setStatusFilter([])
  }

  const handleRetryScan = async (target, port) => {
    try {
      setScanning(true)
      await discoveryService.scan({ targets: [`${target}:${port}`], ports: [port], timeout: 10 })
    } catch (error) {
      showError(error.message || t('discovery.scanFailed'))
    } finally {
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
      downloadBlob(blob, `discovered_certificates.${format}`)
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
          {canWrite('certificates') && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setEditingProfile(row); setShowProfileForm(true) }}
              className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary transition-colors"
              title={t('common.edit')}
            >
              <Pencil size={14} />
            </button>
          )}
          {canWrite('certificates') && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setDeleteConfirm({ type: 'profile', id: row.id }) }}
              className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-tertiary hover:text-status-danger transition-colors"
              title={t('common.delete')}
            >
              <Trash size={14} />
            </button>
          )}
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
  // ── Tab content ───────────────────────────────────────
  const renderContent = () => {
    switch (activeTab) {
      case 'discovered':
        return (
          <div className="flex flex-col h-full">
            <DiscoveryFilterBar statusFilter={statusFilter} setStatusFilter={setStatusFilter} profileFilter={profileFilter} profiles={profiles} handleProfileFilter={handleProfileFilter} setPage={setPage} t={t} />
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
            densityStorageKey="ucm-discovery-density"
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
      <HelpCard title={t('discovery.helpScanProfilesTitle')} variant="info">
        {t('discovery.helpScanProfiles')}
      </HelpCard>
      <HelpCard title={t('discovery.helpFiltersTitle')} variant="tip">
        {t('discovery.helpFilters')}
      </HelpCard>
      <HelpCard title={t('discovery.helpErrorsTitle')} variant="warning">
        {t('discovery.helpErrors')}
      </HelpCard>
      <HelpCard title={t('discovery.helpExportTitle')} variant="info">
        {t('discovery.helpExport')}
      </HelpCard>
      <HelpCard title={t('discovery.helpSecurityTitle')} variant="info">
        {t('discovery.helpSecurity')}
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
