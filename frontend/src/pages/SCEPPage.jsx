/**
 * SCEP Management Page - Migrated to ResponsiveLayout
 * Simple Certificate Enrollment Protocol configuration and request management
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  Robot, Gear, CheckCircle, XCircle, Clock, Copy, ArrowsClockwise, 
  Eye, ShieldCheck, Plugs, Key, Warning, Info, FileText, Globe, Database, 
  ListBullets
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  ResponsiveDataTable,
  Button, Input, Select, Card,
  Badge, LoadingSpinner, Modal, Textarea, EmptyState, HelpCard,
  CompactHeader, CompactSection, CompactGrid, CompactField, CompactStats
} from '../components'
import { scepService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, cn } from '../lib/utils'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'

export default function SCEPPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showInfo } = useNotification()
  const { hasPermission, canWrite } = usePermission()
  
  const [loading, setLoading] = useState(true)
  const [config, setConfig] = useState({})
  const [requests, setRequests] = useState([])
  const [cas, setCas] = useState([])
  const [stats, setStats] = useState({ pending: 0, approved: 0, rejected: 0, total: 0 })
  const [selectedRequest, setSelectedRequest] = useState(null)
  const [activeTab, setActiveTab] = useState('requests')
  const [saving, setSaving] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  
  // Modal states
  const [showRejectModal, setShowRejectModal] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [showHelp, setShowHelp] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [configRes, requestsRes, casRes, statsRes] = await Promise.all([
        scepService.getConfig(),
        scepService.getRequests(),
        casService.getAll(),
        scepService.getStats()
      ])
      setConfig(configRes.data || {})
      setRequests(requestsRes.data || [])
      setStats(statsRes.data || { pending: 0, approved: 0, rejected: 0, total: 0 })
      
      // Load challenge passwords for each CA
      const casData = casRes.data || []
      const casWithChallenges = await Promise.all(
        casData.map(async (ca) => {
          try {
            const challengeRes = await scepService.getChallenge(ca.id)
            return { ...ca, scep_challenge: challengeRes.data?.challenge }
          } catch {
            return { ...ca, scep_challenge: null }
          }
        })
      )
      setCas(casWithChallenges)
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.scep'))
    } finally {
      setLoading(false)
    }
  }

  const handleSaveConfig = async () => {
    if (!canWrite('scep')) return
    setSaving(true)
    try {
      await scepService.updateConfig(config)
      showSuccess(t('messages.success.update.settings'))
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const handleApprove = async (req) => {
    try {
      await scepService.approveRequest(req.id)
      showSuccess(t('scep.requestApproved'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }

  const handleReject = async () => {
    if (!selectedRequest) return
    try {
      await scepService.rejectRequest(selectedRequest.id, rejectReason)
      showSuccess(t('scep.requestRejected'))
      setShowRejectModal(false)
      setRejectReason('')
      setSelectedRequest(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }

  const handleRegenerateChallenge = async (caId) => {
    try {
      await scepService.regenerateChallenge(caId)
      showSuccess(t('scep.challengeRegenerated'))
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.generic'))
    }
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    showInfo(t('common.copiedToClipboard'))
  }

  const getStatusBadge = (status) => {
    const config = {
      pending: { variant: 'orange', dot: true, pulse: true },
      approved: { variant: 'success', dot: true, pulse: false },
      rejected: { variant: 'danger', dot: true, pulse: false },
      issued: { variant: 'primary', dot: true, pulse: false }
    }
    const { variant, dot, pulse } = config[status] || { variant: 'secondary', dot: false, pulse: false }
    return <Badge variant={variant} size="sm" dot={dot} pulse={pulse}>{status}</Badge>
  }

  // Parse DN to extract CN and other fields
  const parseDN = (dn) => {
    if (!dn) return { cn: null, parts: {} }
    const parts = {}
    // Parse DN like "CN=scep-test-device,OU=MDM,O=UCM Test,C=FR"
    const regex = /([A-Z]+)=([^,]+)/g
    let match
    while ((match = regex.exec(dn)) !== null) {
      parts[match[1]] = match[2]
    }
    return { cn: parts.CN || null, parts }
  }

  // Tabs config
  const tabs = useMemo(() => [
    { id: 'requests', label: t('scep.requests'), icon: ListBullets, badge: stats.pending > 0 ? stats.pending : null },
    { id: 'config', label: t('common.config'), icon: Gear },
    { id: 'challenge', label: t('common.challenges'), icon: Key },
    { id: 'info', label: t('scep.info'), icon: Info }
  ], [stats.pending, t])

  // Get SCEP CA name from config
  const scepCaName = useMemo(() => {
    if (!config.ca_id) return null
    const ca = cas.find(c => c.id === config.ca_id)
    return ca?.cn || ca?.common_name || ca?.name || null
  }, [config.ca_id, cas])

  // Stats for header
  const headerStats = useMemo(() => [
    { icon: Clock, label: t('common.pending'), value: stats.pending, variant: stats.pending > 0 ? 'warning' : 'default' },
    { icon: CheckCircle, label: t('common.approved'), value: stats.approved, variant: 'success' },
    { icon: XCircle, label: t('common.rejected'), value: stats.rejected, variant: 'danger' },
    { icon: ListBullets, label: t('common.total'), value: stats.total }
  ], [stats, t])

  // Request table columns
  const requestColumns = useMemo(() => [
    { key: 'id', header: t('scep.id'), width: '60px', hideOnMobile: true },
    { 
      key: 'subject', 
      header: t('common.subject'), 
      priority: 1,
      // Desktop: Icon + CN as main text + O/OU as secondary
      render: (v, row) => {
        const { cn: commonName, parts } = parseDN(v)
        return (
          <div className="flex items-center gap-2">
            <div className={cn(
              "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
              row.status === 'pending' ? 'icon-bg-orange' : row.status === 'approved' ? 'icon-bg-emerald' : 'icon-bg-red'
            )}>
              <Robot size={14} weight="duotone" />
            </div>
            <div className="space-y-0.5 min-w-0">
              <div className="font-medium text-text-primary truncate">
                {commonName || `Request #${row.id}`}
              </div>
              {(parts.O || parts.OU) && (
                <div className="text-xs text-text-secondary truncate">
                  {[parts.O, parts.OU].filter(Boolean).join(' • ')}
                </div>
              )}
            </div>
          </div>
        )
      },
      // Mobile: CN left + status badge right (same pattern as Certificates)
      mobileRender: (v, row) => {
        const { cn: commonName } = parseDN(v)
        return (
          <div className="flex items-center justify-between gap-2 w-full">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className={cn(
                "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
                row.status === 'pending' ? 'icon-bg-orange' : row.status === 'approved' ? 'icon-bg-emerald' : 'icon-bg-red'
              )}>
                <Robot size={14} weight="duotone" />
              </div>
              <span className="font-medium truncate">
                {commonName || `Request #${row.id}`}
              </span>
            </div>
            <div className="shrink-0">
              {getStatusBadge(row.status)}
            </div>
          </div>
        )
      }
    },
    { 
      key: 'status', 
      header: t('common.status'), 
      priority: 2,
      hideOnMobile: true, // Status shown in subject mobileRender
      render: (v) => getStatusBadge(v)
    },
    {
      key: 'ca',
      header: t('common.ca'),
      priority: 3,
      hideOnMobile: true,
      render: () => (
        <span className="text-text-secondary truncate">
          {scepCaName || <span className="text-text-tertiary italic">{t('common.notConfigured')}</span>}
        </span>
      )
    },
    { 
      key: 'transaction_id', 
      header: t('scep.transactionId'), 
      priority: 4,
      hideOnMobile: true,
      render: (v) => (
        <code className="text-xs bg-bg-tertiary px-1.5 py-0.5 rounded">{v?.slice(0, 16)}...</code>
      )
    },
    { 
      key: 'created_at', 
      header: t('scep.requested'), 
      priority: 5,
      render: (v) => formatDate(v),
      // Mobile: CA + organization info + date
      mobileRender: (v, row) => {
        const { parts } = parseDN(row.subject)
        return (
          <div className="flex items-center gap-2 flex-wrap text-xs">
            {scepCaName && (
              <span><span className="text-text-tertiary">{t('common.ca')}:</span> <span className="text-text-secondary">{scepCaName}</span></span>
            )}
            {parts.O && (
              <span><span className="text-text-tertiary">Org:</span> <span className="text-text-secondary">{parts.O}</span></span>
            )}
            <span><span className="text-text-tertiary">{t('scep.requested')}:</span> <span className="text-text-secondary">{formatDate(v)}</span></span>
          </div>
        )
      }
    }
  ], [scepCaName, t])

  // Help content
  const helpContent = (
    <div className="p-4 space-y-4">
      {/* SCEP Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary-op5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          {t('scep.scepStats')}
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-warning-text">{stats.pending}</p>
            <p className="text-xs text-text-secondary">{t('common.pending')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-success-text">{stats.approved}</p>
            <p className="text-xs text-text-secondary">{t('common.approved')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-danger">{stats.rejected}</p>
            <p className="text-xs text-text-secondary">{t('common.rejected')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{stats.total}</p>
            <p className="text-xs text-text-secondary">{t('common.total')}</p>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title={t('scep.aboutScep')}>
          {t('scep.aboutScepDesc')}
        </HelpCard>
        
        <HelpCard variant="tip" title={t('scep.mdmIntegration')}>
          {t('scep.mdmIntegrationDesc')}
        </HelpCard>

        <HelpCard variant="warning" title={t('scep.challengeSecurity')}>
          {t('scep.challengeSecurityDesc')}
        </HelpCard>
      </div>
    </div>
  )

  // Request details slide-over content
  const requestDetailContent = selectedRequest && !showRejectModal && (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={Robot}
        iconClass={selectedRequest.status === 'approved' ? "bg-status-success-op20" : selectedRequest.status === 'rejected' ? "bg-status-danger-op20" : "bg-status-warning-op20"}
        title={`Request #${selectedRequest.id}`}
        subtitle={selectedRequest.subject || 'SCEP Enrollment Request'}
        badge={getStatusBadge(selectedRequest.status)}
      />

      <CompactStats stats={[
        { icon: Clock, value: formatDate(selectedRequest.created_at) }
      ]} />

      {selectedRequest.status === 'pending' && hasPermission('write:scep') && (
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="primary" className="flex-1" onClick={() => handleApprove(selectedRequest)}>
            <CheckCircle size={14} /> {t('scep.approve')}
          </Button>
          <Button type="button" size="sm" variant="danger" onClick={() => setShowRejectModal(true)}>
            <XCircle size={14} /> {t('scep.reject')}
          </Button>
        </div>
      )}

      <CompactSection title={t('common.requestDetails')}>
        <CompactGrid>
          <CompactField autoIcon="transactionId" label={t('scep.transactionId')} value={selectedRequest.transaction_id} mono copyable />
          <CompactField autoIcon="subject" label={t('common.subject')} value={selectedRequest.subject} />
          <CompactField autoIcon="status" label={t('common.status')} value={selectedRequest.status} />
          <CompactField autoIcon="created" label={t('common.created')} value={formatDate(selectedRequest.created_at)} />
        </CompactGrid>
      </CompactSection>

      {selectedRequest.csr_pem && (
        <CompactSection title={t('common.csrContent')} collapsible defaultOpen={false}>
          <pre className="text-2xs font-mono text-text-secondary bg-tertiary-op50 p-2 rounded overflow-x-auto max-h-32 overflow-y-auto">
            {selectedRequest.csr_pem}
          </pre>
        </CompactSection>
      )}
    </div>
  )

  // Header actions
  const headerActions = (
    <>
      <Button type="button" variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
        <ArrowsClockwise size={14} />
      </Button>
      <Button type="button" variant="secondary" size="lg" onClick={loadData} className="md:hidden h-11 w-11 p-0">
        <ArrowsClockwise size={22} />
      </Button>
    </>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <>
      <ResponsiveLayout
        title={t('scep.title')}
        icon={Robot}
        subtitle={config.enabled ? t('common.enabled') : t('common.disabled')}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        tabLayout="sidebar"
        sidebarContentClass=""
        tabGroups={[
          { labelKey: 'scep.groups.management', tabs: ['requests', 'challenge'], color: 'icon-bg-blue' },
          { labelKey: 'scep.groups.settings', tabs: ['config', 'info'], color: 'icon-bg-emerald' },
        ]}
        stats={activeTab === 'requests' ? headerStats : undefined}
        helpPageKey="scep"
        splitView={activeTab === 'requests'}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Robot size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('scep.selectRequest')}</p>
          </div>
        }
        slideOverOpen={!!selectedRequest && !showRejectModal}
        onSlideOverClose={() => setSelectedRequest(null)}
        slideOverTitle={t('common.requestDetails')}
        slideOverContent={requestDetailContent}
        slideOverWidth="md"
      >
        {/* Requests Tab */}
        {activeTab === 'requests' && (
          <ResponsiveDataTable
            data={requests}
            columns={requestColumns}
            keyField="id"
            searchable
            externalSearch={searchQuery}
            onSearchChange={setSearchQuery}
            searchPlaceholder={t('scep.searchRequests')}
            toolbarActions={
              <>
                <Button type="button" variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
                  <ArrowsClockwise size={14} />
                </Button>
                <Button type="button" variant="secondary" size="lg" onClick={loadData} className="md:hidden h-11 w-11 p-0">
                  <ArrowsClockwise size={22} />
                </Button>
              </>
            }
            selectedId={selectedRequest?.id}
            onRowClick={setSelectedRequest}
            pagination={{
              page,
              total: requests.length,
              perPage,
              onChange: setPage,
              onPerPageChange: (v) => { setPerPage(v); setPage(1) }
            }}
            emptyState={{
              icon: Robot,
              title: t('scep.noRequests'),
              description: t('scep.noRequestsDesc')
            }}
          />
        )}

        {/* Configuration Tab */}
        {activeTab === 'config' && (
          <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-6">
            <Card className="p-4">
              <div className="flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                  config.enabled ? 'status-success-bg' : 'bg-bg-tertiary'
                }`}>
                  <Plugs size={24} className={config.enabled ? 'status-success-text' : 'text-text-tertiary'} weight="duotone" />
                </div>
                <div className="flex-1">
                  <ToggleSwitch
                    checked={config.enabled || false}
                    onChange={(val) => setConfig({ ...config, enabled: val })}
                    label={t('scep.enableScep')}
                    description={t('scep.enableScepDesc')}
                  />
                </div>
              </div>
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Gear size={16} />
                {t('scep.serverSettings')}
              </h3>
              
              <Input
                label={t('scep.scepEndpointUrl')}
                value={`${window.location.origin}/scep/pkiclient.exe`}
                readOnly
                helperText={t('scep.useThisUrl')}
                className="bg-bg-tertiary"
              />

              <Select
                label={t('common.issuingCA')}
                placeholder={t('common.acmeSelectCA')}
                options={cas.map(ca => ({ value: ca.id.toString(), label: ca.name || ca.subject }))}
                value={config.ca_id?.toString() || ''}
                onChange={(val) => setConfig({ ...config, ca_id: parseInt(val) })}
                disabled={!config.enabled}
              />

              <Input
                label={t('scep.caIdentifier')}
                value={config.ca_ident || 'ucm-ca'}
                onChange={(e) => setConfig({ ...config, ca_ident: e.target.value })}
                helperText={t('scep.caIdentifierHelp')}
                disabled={!config.enabled}
              />
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <ShieldCheck size={16} />
                {t('common.securitySettings')}
              </h3>
              
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <ToggleSwitch
                  checked={config.auto_approve || false}
                  onChange={(val) => setConfig({ ...config, auto_approve: val })}
                  disabled={!config.enabled}
                  label={t('scep.autoApprove')}
                  description={t('scep.autoApproveDesc')}
                />
                {config.auto_approve && (
                  <div className="mt-2 flex items-start gap-2 status-warning-text text-xs">
                    <Warning size={14} className="flex-shrink-0 mt-0.5" />
                    <span>{t('scep.autoApproveWarning')}</span>
                  </div>
                )}
              </div>

              <Input
                label={t('scep.challengeValidity')}
                type="number"
                value={config.challenge_validity || 24}
                onChange={(e) => setConfig({ ...config, challenge_validity: parseInt(e.target.value) })}
                min="1"
                max="168"
                disabled={!config.enabled}
                helperText={t('scep.challengeValidityHelp')}
                suffix={t('scep.hours')}
              />
            </Card>

            {hasPermission('write:scep') && (
              <div className="flex justify-end">
                <Button type="button" onClick={handleSaveConfig} disabled={saving}>
                  {saving ? <LoadingSpinner size="sm" /> : <Gear size={14} />}
                  {saving ? t('common.saving') : t('common.saveConfiguration')}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Challenge Passwords Tab */}
        {activeTab === 'challenge' && (
          <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-4">
            {!config.enabled && (
              <Card className="p-4 status-warning-border status-warning-bg border">
                <div className="flex items-start gap-3">
                  <Warning size={20} className="status-warning-text flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium status-warning-text">{t('scep.scepDisabled')}</p>
                    <p className="text-xs text-text-secondary">{t('scep.scepDisabledDesc')}</p>
                  </div>
                </div>
              </Card>
            )}

            {cas.length === 0 ? (
              <EmptyState 
                icon={ShieldCheck}
                title={t('scep.noCasAvailable')}
                description={t('scep.noCasAvailableDesc')}
              />
            ) : (
              cas.map(ca => (
                <Card key={ca.id} className="p-4">
                  <div className="flex items-start justify-between gap-4 mb-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <ShieldCheck size={16} className="text-accent-primary" weight="duotone" />
                        <h3 className="text-sm font-semibold text-text-primary truncate">{ca.name || ca.subject}</h3>
                      </div>
                      <p className="text-xs text-text-tertiary truncate">{ca.subject}</p>
                    </div>
                    {hasPermission('write:scep') && (
                      <Button 
                        size="sm" 
                        variant="secondary" 
                        onClick={() => handleRegenerateChallenge(ca.id)}
                      >
                        <ArrowsClockwise size={14} />
                        <span className="hidden md:inline">{t('scep.regenerate')}</span>
                      </Button>
                    )}
                  </div>
                  <div className="p-3 bg-bg-tertiary rounded-lg">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-text-secondary mb-1">{t('scep.challenge')}</p>
                        <code className="text-sm font-mono text-text-primary break-all">
                          {ca.scep_challenge || t('scep.noChallengeSet')}
                        </code>
                      </div>
                      {ca.scep_challenge && (
                        <Button type="button" size="sm" variant="ghost" onClick={() => copyToClipboard(ca.scep_challenge)}>
                          <Copy size={14} />
                        </Button>
                      )}
                    </div>
                  </div>
                </Card>
              ))
            )}
          </div>
        )}

        {/* Information Tab */}
        {activeTab === 'info' && (
          <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-4">
            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Globe size={16} />
                {t('scep.connectionDetails')}
              </h3>
              
              <div className="space-y-3">
                <div className="p-3 bg-bg-tertiary rounded-lg">
                  <p className="text-xs text-text-secondary mb-1">{t('scep.scepURL')}</p>
                  <div className="flex items-center gap-2">
                    <code className="text-sm font-mono text-text-primary flex-1 break-all">
                      {window.location.origin}/scep/pkiclient.exe
                    </code>
                    <Button type="button" size="sm" variant="ghost" onClick={() => copyToClipboard(`${window.location.origin}/scep/pkiclient.exe`)}>
                      <Copy size={14} />
                    </Button>
                  </div>
                </div>
                
                <div className="p-3 bg-bg-tertiary rounded-lg">
                  <p className="text-xs text-text-secondary mb-1">{t('scep.caIdentifier')}</p>
                  <div className="flex items-center gap-2">
                    <code className="text-sm font-mono text-text-primary flex-1">
                      {config.ca_ident || 'ucm-ca'}
                    </code>
                    <Button type="button" size="sm" variant="ghost" onClick={() => copyToClipboard(config.ca_ident || 'ucm-ca')}>
                      <Copy size={14} />
                    </Button>
                  </div>
                </div>
              </div>
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <CheckCircle size={16} />
                {t('scep.supportedOperations')}
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {['GetCACaps', 'GetCACert', 'GetCACertChain', 'PKIOperation'].map(op => (
                  <div key={op} className="flex items-center gap-2 p-2 bg-bg-tertiary rounded">
                    <CheckCircle size={14} className="status-success-text" />
                    <span className="text-sm text-text-primary">{op}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <FileText size={16} />
                {t('scep.ciscoExample')}
              </h3>
              <pre className="p-3 bg-bg-tertiary rounded-lg text-xs text-text-primary font-mono overflow-x-auto border border-border">
{`crypto ca trustpoint UCM-CA
 enrollment url ${window.location.origin}/scep/pkiclient.exe
 subject-name CN=device.example.com
 revocation-check none
 auto-enroll 70
!
crypto ca authenticate UCM-CA
crypto ca enroll UCM-CA`}
              </pre>
            </Card>
          </div>
        )}
      </ResponsiveLayout>

      {/* Reject Modal */}
      <Modal
        open={showRejectModal}
        onClose={() => { setShowRejectModal(false); setRejectReason(''); setSelectedRequest(null); }}
        title={t('scep.rejectRequest')}
        size="md"
      >
        <div className="space-y-4">
          <div className="p-3 status-danger-bg status-danger-border border rounded-lg">
            <p className="text-sm text-text-primary">
              {t('scep.rejectEnrollment')}
            </p>
            <p className="text-sm font-mono status-danger-text mt-1">
              {selectedRequest?.subject || selectedRequest?.transaction_id}
            </p>
          </div>
          <Textarea
            label={t('scep.rejectionReason')}
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder={t('scep.rejectionPlaceholder')}
            rows={3}
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => { setShowRejectModal(false); setRejectReason(''); }}>
              {t('common.cancel')}
            </Button>
            <Button type="button" variant="danger" onClick={handleReject}>
              <XCircle size={14} />
              {t('scep.rejectRequest')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
