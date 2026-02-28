/**
 * Discovery Page
 * Certificate discovery and network scanning
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Globe, Gear, Copy, Info, ShieldCheck, Plugs, Warning, CheckCircle,
  ChartBar, Lock, ArrowsClockwise, MagnifyingGlass, Network, Cpu
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  Button, Input, Select, Card,
  LoadingSpinner, EmptyState, HelpCard,
  CompactStats, Badge, Tabs
} from '../components'
import { discoveryService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'
import { ResponsiveDataTable } from '../components/ui/responsive/ResponsiveDataTable'

export default function DiscoveryPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showInfo } = useNotification()
  const { hasPermission, canWrite } = usePermission()

  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [importing, setImporting] = useState(false)
  const [activeTab, setActiveTab] = useState('scan')
  const [scanResults, setScanResults] = useState([])
  const [history, setHistory] = useState([])
  const [unknownCerts, setUnknownCerts] = useState([])
  const [expiredCerts, setExpiredCerts] = useState([])
  const [stats, setStats] = useState({
    totalScanned: 0,
    found: 0,
    imported: 0,
    unknown: 0,
    expired: 0
  })

  const [scanConfig, setScanConfig] = useState({
    targets: 'example.com\ngoogle.com',
    ports: [443, 8443],
    scanType: 'targets'
  })

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [historyRes, unknownRes, expiredRes] = await Promise.all([
        discoveryService.getHistory(100),
        discoveryService.getUnknown(),
        discoveryService.getExpired()
      ])
      
      setHistory(historyRes.data.history || [])
      setUnknownCerts(unknownRes.data.unknown || [])
      setExpiredCerts(expiredRes.data.expired || [])
      
      updateStats()
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.discovery'))
    } finally {
      setLoading(false)
    }
  }

  const updateStats = () => {
    setStats({
      totalScanned: history.length,
      found: history.length,
      imported: history.filter(c => c.status === 'known').length,
      unknown: unknownCerts.length,
      expired: expiredCerts.length
    })
  }

  // Column definitions for ResponsiveDataTable
  const resultColumns = useMemo(() => [
    { key: 'target', label: t('common.target'), sortable: true },
    { key: 'subject', label: t('common.subject'), sortable: true },
    { key: 'issuer', label: t('common.issuer'), sortable: true },
    { key: 'serial', label: t('common.serial'), sortable: true },
    { key: 'notAfter', label: t('common.expiry'), sortable: true, render: (row) => row.notAfter ? new Date(row.notAfter).toLocaleDateString() : '-' },
    { key: 'status', label: t('common.status'), render: (row) => (
      <Badge variant={row.status === 'known' ? 'success' : 'warning'}>
        {t(`common.${row.status}`)}
      </Badge>
    )}
  ], [t])

  const historyColumns = useMemo(() => [
    { key: 'target', label: t('common.target'), sortable: true },
    { key: 'subject', label: t('common.subject'), sortable: true },
    { key: 'issuer', label: t('common.issuer'), sortable: true },
    { key: 'serial', label: t('common.serial'), sortable: true },
    { key: 'lastSeen', label: t('common.lastSeen'), sortable: true, render: (row) => row.lastSeen ? new Date(row.lastSeen).toLocaleString() : '-' },
    { key: 'status', label: t('common.status'), sortable: true, render: (row) => (
      <Badge variant={row.status === 'known' ? 'success' : 'warning'}>
        {t(`common.${row.status}`)}
      </Badge>
    )}
  ], [t])

  const unknownColumns = useMemo(() => [
    { key: 'target', label: t('common.target'), sortable: true },
    { key: 'subject', label: t('common.subject'), sortable: true },
    { key: 'issuer', label: t('common.issuer'), sortable: true },
    { key: 'serial', label: t('common.serial'), sortable: true },
    { key: 'notAfter', label: t('common.expiry'), sortable: true, render: (row) => row.notAfter ? new Date(row.notAfter).toLocaleDateString() : '-' }
  ], [t])

  const expiredColumns = useMemo(() => [
    { key: 'target', label: t('common.target'), sortable: true },
    { key: 'subject', label: t('common.subject'), sortable: true },
    { key: 'issuer', label: t('common.issuer'), sortable: true },
    { key: 'serial', label: t('common.serial'), sortable: true },
    { key: 'notAfter', label: t('common.expiry'), sortable: true, render: (row) => row.notAfter ? new Date(row.notAfter).toLocaleDateString() : '-' }
  ], [t])

  const handleScan = async () => {
    if (!canWrite('system')) {
      showError(t('messages.errors.permissionRequired'))
      return
    }

    if (scanConfig.scanType === 'targets' && !scanConfig.targets.trim()) {
      showError(t('discovery.errors.noTargets'))
      return
    }
    
    if (scanConfig.scanType === 'subnet' && !scanConfig.subnet) {
      showError(t('discovery.errors.noSubnet'))
      return
    }

    setScanning(true)
    try {
      let response
      
      if (scanConfig.scanType === 'targets') {
        const targets = scanConfig.targets.split('\n').filter(t => t.trim())
        response = await discoveryService.scan(targets, scanConfig.ports)
      } else {
        response = await discoveryService.scanSubnet(scanConfig.subnet, scanConfig.ports)
      }
      
      const results = response.data.results || []
      setScanResults(results)
      setActiveTab('results')
      
      showSuccess(
        t('discovery.success.scanComplete', { count: results.length })
      )
    } catch (error) {
      showError(error.message || t('discovery.errors.scanFailed'))
    } finally {
      setScanning(false)
    }
  }

  const handleImport = async (certificates) => {
    if (!canWrite('certificates')) {
      showError(t('messages.errors.permissionRequired'))
      return
    }

    setImporting(true)
    try {
      const response = await discoveryService.import(certificates)
      
      showSuccess(
        t('discovery.success.imported', {
          imported: response.data.imported,
          known: response.data.already_known
        })
      )
      
      await loadData()
      setScanResults([])
    } catch (error) {
      showError(error.message || t('discovery.errors.importFailed'))
    } finally {
      setImporting(false)
    }
  }

  const handleImportSelected = async () => {
    await handleImport(scanResults)
  }

  const handleImportAllUnknown = async () => {
    await handleImport(unknownCerts)
  }

  const handleRefresh = async () => {
    await loadData()
    showInfo(t('discovery.info.dataRefreshed'))
  }

  const renderScanTab = () => {
    return (
      <div className="space-y-6">
        <Card>
          <div className="flex items-center gap-4 mb-4">
            <Network size={32} className="text-accent-primary" />
            <h2 className="text-xl font-semibold">{t('discovery.scanConfiguration')}</h2>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">{t('discovery.scanType')}</label>
              <Select
                value={scanConfig.scanType}
                onChange={(value) => setScanConfig({...scanConfig, scanType: value})}
                options={[
                  { value: 'targets', label: t('discovery.scanTypeTargets') },
                  { value: 'subnet', label: t('discovery.scanTypeSubnet') }
                ]}
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">{t('discovery.ports')}</label>
              <Select
                value={scanConfig.ports}
                onChange={(value) => setScanConfig({...scanConfig, ports: value})}
                options={[
                  { value: [443], label: '443 (HTTPS)' },
                  { value: [8443], label: '8443 (Alternative)' },
                  { value: [443, 8443], label: '443, 8443 (Both)' }
                ]}
                isMulti
              />
            </div>
          </div>
          
          {scanConfig.scanType === 'targets' && (
            <div className="mt-4">
              <label className="block text-sm font-medium mb-2">{t('discovery.targets')}</label>
              <Input
                type="textarea"
                rows={6}
                value={scanConfig.targets}
                onChange={(e) => setScanConfig({...scanConfig, targets: e.target.value})}
                placeholder="example.com\n192.168.1.1\n10.0.0.5\ngoogle.com"
              />
              <p className="text-xs text-text-tertiary mt-1">
                {t('discovery.targetsHelp')}
              </p>
            </div>
          )}
          
          {scanConfig.scanType === 'subnet' && (
            <div className="mt-4">
              <label className="block text-sm font-medium mb-2">{t('discovery.subnet')}</label>
              <Input
                value={scanConfig.subnet}
                onChange={(e) => setScanConfig({...scanConfig, subnet: e.target.value})}
                placeholder="192.168.1.0/24"
              />
              <p className="text-xs text-text-tertiary mt-1">
                {t('discovery.subnetHelp')}
              </p>
            </div>
          )}
          
          <div className="flex gap-2 mt-6">
            <Button
              onClick={handleScan}
              disabled={scanning}
              icon={scanning ? <LoadingSpinner size="sm" /> : <MagnifyingGlass />}
            >
              {scanning ? t('discovery.scanning') : t('discovery.scan')}
            </Button>
            <Button
              variant="secondary"
              onClick={() => setScanConfig({
                targets: 'example.com\ngoogle.com',
                ports: [443, 8443],
                scanType: 'targets'
              })}
              icon={<ArrowsClockwise />}
            >
              {t('common.reset')}
            </Button>
          </div>
        </Card>
        
        <HelpCard
          title={t('discovery.helpTitle')}
          icon={<Info />}
        >
          <p className="text-sm mb-2">{t('discovery.helpDescription')}</p>
          <ul className="text-sm space-y-1 text-text-secondary">
            <li>• {t('discovery.helpItem1')}</li>
            <li>• {t('discovery.helpItem2')}</li>
            <li>• {t('discovery.helpItem3')}</li>
            <li>• {t('discovery.helpItem4')}</li>
          </ul>
        </HelpCard>
      </div>
    )
  }

  const renderResultsTab = () => {
    if (scanResults.length === 0) {
      return (
        <EmptyState
          icon={<MagnifyingGlass size={48} />}
          title={t('discovery.noResults')}
          description={t('discovery.noResultsDescription')}
        />
      )
    }

    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-semibold">
            {t('discovery.scanResults', { count: scanResults.length })}
          </h2>
          {canWrite('certificates') && (
            <Button
              onClick={handleImportSelected}
              disabled={importing}
              icon={importing ? <LoadingSpinner size="sm" /> : <Plugs />}
            >
              {importing ? t('discovery.importing') : t('discovery.importAll')}
            </Button>
          )}
        </div>
        
        <ResponsiveDataTable
          data={scanResults}
          columns={resultColumns}
          loading={loading}
          onRowClick={handleSelectCert}
          searchable
          searchPlaceholder={t('common.search') + ' ' + t('common.certificates').toLowerCase() + '...'}
          searchKeys={['target', 'subject', 'issuer', 'serial']}
          columnStorageKey="ucm-discovery-results-columns"
        />
      </div>
    )
  }

  const renderHistoryTab = () => {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-semibold">{t('discovery.discoveryHistory')}</h2>
          <Button
            variant="secondary"
            onClick={handleRefresh}
            icon={<ArrowsClockwise />}
          >
            {t('common.refresh')}
          </Button>
        </div>
        
        {history.length === 0 ? (
          <EmptyState
            icon={<ChartBar size={48} />}
            title={t('discovery.noHistory')}
            description={t('discovery.noHistoryDescription')}
          />
        ) : (
          <ResponsiveDataTable
            data={history}
            columns={historyColumns}
            loading={loading}
            searchable
            searchPlaceholder={t('common.search') + ' ' + t('common.history').toLowerCase() + '...'}
            searchKeys={['target', 'subject', 'issuer', 'serial', 'status']}
            columnStorageKey="ucm-discovery-history-columns"
          />
        )}
      </div>
    )
  }

  const renderUnknownTab = () => {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-semibold">
            {t('discovery.unknownCertificates', { count: unknownCerts.length })}
          </h2>
          {canWrite('certificates') && unknownCerts.length > 0 && (
            <Button
              onClick={handleImportAllUnknown}
              disabled={importing}
              icon={importing ? <LoadingSpinner size="sm" /> : <Plugs />}
            >
              {importing ? t('discovery.importing') : t('discovery.importAll')}
            </Button>
          )}
        </div>
        
        {unknownCerts.length === 0 ? (
          <EmptyState
            icon={<ShieldCheck size={48} />}
            title={t('discovery.noUnknown')}
            description={t('discovery.noUnknownDescription')}
          />
        ) : (
          <ResponsiveDataTable
            data={unknownCerts}
            columns={unknownColumns}
            loading={loading}
            searchable
            searchPlaceholder={t('common.search') + ' ' + t('common.certificates').toLowerCase() + '...'}
            searchKeys={['target', 'subject', 'issuer', 'serial']}
            columnStorageKey="ucm-discovery-unknown-columns"
          />
        )}
      </div>
    )
  }

  const renderExpiredTab = () => {
    return (
      <div className="space-y-6">
        <h2 className="text-xl font-semibold">
          {t('discovery.expiredCertificates', { count: expiredCerts.length })}
        </h2>
        
        {expiredCerts.length === 0 ? (
          <EmptyState
            icon={<CheckCircle size={48} />}
            title={t('discovery.noExpired')}
            description={t('discovery.noExpiredDescription')}
          />
        ) : (
          <ResponsiveDataTable
            data={expiredCerts}
            columns={expiredColumns}
            loading={loading}
            searchable
            searchPlaceholder={t('common.search') + ' ' + t('common.certificates').toLowerCase() + '...'}
            searchKeys={['target', 'subject', 'issuer', 'serial']}
            columnStorageKey="ucm-discovery-expired-columns"
          />
        )}
      </div>
    )
  }

  const renderStats = () => {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <CompactStats
          title={t('discovery.stats.totalScanned')}
          value={stats.totalScanned}
          icon={<Globe />}
          color="blue"
        />
        <CompactStats
          title={t('discovery.stats.found')}
          value={stats.found}
          icon={<MagnifyingGlass />}
          color="green"
        />
        <CompactStats
          title={t('discovery.stats.imported')}
          value={stats.imported}
          icon={<CheckCircle />}
          color="purple"
        />
        <CompactStats
          title={t('discovery.stats.unknown')}
          value={stats.unknown}
          icon={<Warning />}
          color="yellow"
        />
        <CompactStats
          title={t('discovery.stats.expired')}
          value={stats.expired}
          icon={<Lock />}
          color="red"
        />
      </div>
    )
  }

  if (loading && !history.length) {
    return (
      <ResponsiveLayout>
        <div className="flex justify-center items-center h-64">
          <LoadingSpinner size="lg" />
        </div>
      </ResponsiveLayout>
    )
  }

  return (
    <ResponsiveLayout>
      <div className="p-4">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold">{t('discovery.title')}</h1>
            <p className="text-text-secondary mt-1">
              {t('discovery.subtitle')}
            </p>
          </div>
          {renderStats()}
        </div>

        <TabsComponent
          tabs={[
            { id: 'scan', icon: <MagnifyingGlass />, label: t('discovery.tabScan'), content: renderScanTab() },
            { id: 'results', icon: <ChartBar />, label: t('discovery.tabResults'), content: renderResultsTab() },
            { id: 'history', icon: <ArrowsClockwise />, label: t('discovery.tabHistory'), content: renderHistoryTab() },
            { id: 'unknown', icon: <Warning />, label: t('discovery.tabUnknown'), content: renderUnknownTab() },
            { id: 'expired', icon: <Lock />, label: t('discovery.tabExpired'), content: renderExpiredTab() }
          ]}
          defaultTab={activeTab}
          className="mb-6"
        />
      </div>
    </ResponsiveLayout>
  )
}
