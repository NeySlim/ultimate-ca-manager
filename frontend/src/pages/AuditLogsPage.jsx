/**
 * Audit Logs Page - Migrated to ResponsiveLayout
 * View and filter audit logs with real-time updates
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  ClockCounterClockwise, 
  User, 
  ShieldCheck, 
  Warning, 
  MagnifyingGlass,
  FunnelSimple,
  ArrowsClockwise,
  DownloadSimple,
  Trash,
  CheckCircle,
  XCircle,
  Key,
  Certificate,
  Users,
  Gear,
  Database,
  SignIn,
  SignOut,
  ListBullets,
  Export,
  Calendar
} from '@phosphor-icons/react';
import { 
  ResponsiveLayout,
  ResponsiveDataTable,
  MobileCard,
  Card, 
  Button, 
  Badge, 
  Input,
  Modal,
  LoadingSpinner,
  HelpCard,
  CompactHeader,
  CompactSection,
  CompactGrid,
  CompactField,
  CompactStats
} from '../components';
import { useNotification } from '../contexts';
import auditService from '../services/audit.service';
import { ERRORS } from '../lib/messages';

// Action icons mapping
const actionIcons = {
  login_success: SignIn,
  login_failure: SignIn,
  logout: SignOut,
  create: CheckCircle,
  update: ArrowsClockwise,
  delete: Trash,
  issue: Certificate,
  revoke: XCircle,
  renew: ArrowsClockwise,
  sign: Certificate,
  import: DownloadSimple,
  export: DownloadSimple,
  audit_cleanup: Trash,
  default: ClockCounterClockwise
};

// Category colors
const categoryColors = {
  auth: 'blue',
  certificates: 'emerald',
  cas: 'purple',
  csrs: 'orange',
  users: 'cyan',
  settings: 'gray',
  system: 'red',
  audit: 'yellow',
  default: 'gray'
};

// Action category mapping
const getActionCategory = (action) => {
  if (action.includes('login') || action.includes('logout')) return 'auth';
  if (action.includes('cert') || action.includes('issue') || action.includes('revoke')) return 'certificates';
  if (action.includes('ca_')) return 'cas';
  if (action.includes('csr')) return 'csrs';
  if (action.includes('user')) return 'users';
  if (action.includes('setting')) return 'settings';
  if (action.includes('audit')) return 'audit';
  return 'system';
};

export default function AuditLogsPage() {
  const { t } = useTranslation();
  const { showError, showSuccess } = useNotification();
  
  // State
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [actions, setActions] = useState({ actions: [], categories: {} });
  const [loading, setLoading] = useState(true);
  const [selectedLog, setSelectedLog] = useState(null);
  
  // Pagination
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(50);
  const [total, setTotal] = useState(0);
  
  // Search & Filters
  const [search, setSearch] = useState('');
  const [filterUsername, setFilterUsername] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterSuccess, setFilterSuccess] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  
  // Modals
  const [showCleanupModal, setShowCleanupModal] = useState(false);
  const [cleanupDays, setCleanupDays] = useState(90);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  
  // Slide-over states
  const [showHelp, setShowHelp] = useState(false);
  const [showDateFilters, setShowDateFilters] = useState(false);

  // Load initial data
  useEffect(() => {
    loadData();
  }, []);

  // Reload logs when filters or page change
  useEffect(() => {
    loadLogs();
  }, [page, perPage, filterUsername, filterAction, filterSuccess, filterDateFrom, filterDateTo, search]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [logsRes, statsRes, actionsRes] = await Promise.all([
        auditService.getLogs({ page: 1, per_page: perPage }),
        auditService.getStats(30),
        auditService.getActions()
      ]);
      
      setLogs(logsRes.data || []);
      setTotal(logsRes.meta?.total || 0);
      setStats(statsRes.data || null);
      setActions(actionsRes.data || { actions: [], categories: {} });
    } catch (err) {
      console.error('Failed to load audit data:', err);
      showError(err.message || ERRORS.LOAD_FAILED.AUDIT_LOGS);
    } finally {
      setLoading(false);
    }
  };

  const loadLogs = async () => {
    try {
      const params = {
        page,
        per_page: perPage,
        search: search || undefined,
        username: filterUsername || undefined,
        action: filterAction || undefined,
        success: filterSuccess !== '' ? filterSuccess : undefined,
        date_from: filterDateFrom || undefined,
        date_to: filterDateTo || undefined
      };
      
      const res = await auditService.getLogs(params);
      setLogs(res.data || []);
      setTotal(res.meta?.total || 0);
    } catch (err) {
      console.error('Failed to load logs:', err);
    }
  };

  const handleExport = async (format) => {
    try {
      const res = await auditService.exportLogs({
        format,
        date_from: filterDateFrom || undefined,
        date_to: filterDateTo || undefined,
        limit: 10000
      });
      
      // Create download
      const blob = new Blob([typeof res === 'string' ? res : JSON.stringify(res, null, 2)], {
        type: format === 'csv' ? 'text/csv' : 'application/json'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      
      showSuccess(t('common.exportedFormat', { format: format.toUpperCase() }));
    } catch (err) {
      showError(t('audit.exportLogs') + ' ' + t('common.failed').toLowerCase());
    }
  };

  const handleCleanup = async () => {
    try {
      setCleanupLoading(true);
      const res = await auditService.cleanupLogs(cleanupDays);
      showSuccess(res.message || `Cleaned up ${res.data?.deleted || 0} old logs`);
      setShowCleanupModal(false);
      loadData();
    } catch (err) {
      showError(t('audit.cleanupLogs') + ' ' + t('common.failed').toLowerCase());
    } finally {
      setCleanupLoading(false);
    }
  };

  const clearFilters = useCallback(() => {
    setSearch('');
    setFilterUsername('');
    setFilterAction('');
    setFilterSuccess('');
    setFilterDateFrom('');
    setFilterDateTo('');
    setPage(1);
  }, []);

  // Format timestamp
  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = (now - date) / 1000;
    
    if (diff < 60) return t('common.justNow');
    if (diff < 3600) return t('common.minutesAgo', { count: Math.floor(diff / 60) });
    if (diff < 86400) return t('common.hoursAgo', { count: Math.floor(diff / 3600) });
    
    return date.toLocaleDateString(undefined, { 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Get unique usernames for filter
  const uniqueUsernames = useMemo(() => {
    const names = new Set(logs.map(l => l.username).filter(Boolean));
    return Array.from(names).sort();
  }, [logs]);

  // Table columns - standardized with header, priority, mobileRender
  const columns = useMemo(() => [
    {
      key: 'action',
      header: t('audit.action'),
      priority: 1,
      render: (value, row) => {
        const category = getActionCategory(value);
        const color = categoryColors[category] || 'gray';
        const Icon = actionIcons[value] || actionIcons.default;
        return (
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg icon-bg-violet flex items-center justify-center shrink-0">
              <Icon size={14} weight="duotone" />
            </div>
            <Badge variant={color} size="sm">
              {value.replace(/_/g, ' ')}
            </Badge>
          </div>
        );
      },
      // Mobile: Action + status badge
      mobileRender: (value, row) => {
        const Icon = actionIcons[value] || actionIcons.default;
        return (
          <div className="flex items-center justify-between gap-2 w-full">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className="w-7 h-7 rounded-lg icon-bg-violet flex items-center justify-center shrink-0">
                <Icon size={14} weight="duotone" />
              </div>
              <span className="font-medium truncate">{value?.replace(/_/g, ' ')}</span>
            </div>
            <div className="shrink-0">
              {row.success ? (
                <Badge variant="emerald" size="sm"><CheckCircle size={12} weight="fill" /> OK</Badge>
              ) : (
                <Badge variant="red" size="sm"><XCircle size={12} weight="fill" /> Fail</Badge>
              )}
            </div>
          </div>
        );
      }
    },
    {
      key: 'success',
      header: t('common.status'),
      priority: 2,
      width: '80px',
      hideOnMobile: true, // Status shown in action mobileRender
      render: (value) => (
        value ? (
          <Badge variant="emerald" size="sm">
            <CheckCircle size={12} weight="fill" />
            OK
          </Badge>
        ) : (
          <Badge variant="red" size="sm">
            <XCircle size={12} weight="fill" />
            Fail
          </Badge>
        )
      )
    },
    {
      key: 'username',
      header: t('audit.user'),
      priority: 3,
      width: '120px',
      hideOnMobile: true,
      render: (value) => (
        <div className="flex items-center gap-1">
          <User size={12} className="text-text-secondary" />
          <span className="text-sm font-medium">{value || 'system'}</span>
        </div>
      )
    },
    {
      key: 'resource_type',
      header: t('audit.target'),
      priority: 4,
      hideOnMobile: true,
      render: (value, row) => (
        <span className="text-sm text-text-secondary truncate">
          {value}{row.resource_name ? `: ${row.resource_name}` : (row.resource_id ? ` #${row.resource_id}` : '')}
        </span>
      )
    },
    {
      key: 'timestamp',
      header: t('audit.timestamp'),
      priority: 5,
      sortable: true,
      width: '100px',
      render: (value) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatTime(value)}
        </span>
      ),
      // Mobile: User + resource + time
      mobileRender: (value, row) => (
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span><span className="text-text-tertiary">User:</span> <span className="text-text-secondary">{row.username || 'system'}</span></span>
          {row.resource_type && (
            <span><span className="text-text-tertiary">Resource:</span> <span className="text-text-secondary">{row.resource_type}</span></span>
          )}
          <span><span className="text-text-tertiary">Time:</span> <span className="text-text-secondary">{formatTime(value)}</span></span>
        </div>
      )
    },
    {
      key: 'ip_address',
      header: t('audit.ipAddress'),
      priority: 6,
      width: '120px',
      hideOnMobile: true,
      render: (value) => (
        <span className="text-xs text-text-secondary font-mono">{value || '-'}</span>
      )
    }
  ], [t]);

  // Stats for header
  const headerStats = useMemo(() => {
    if (!stats) return [];
    return [
      { icon: Database, label: t('common.total'), value: stats.total_logs || 0, variant: 'default' },
      { icon: CheckCircle, label: t('common.success'), value: stats.success_count || 0, variant: 'success' },
      { icon: XCircle, label: t('common.failed'), value: stats.failure_count || 0, variant: 'danger' },
      { icon: Users, label: t('common.users'), value: stats.unique_users || 0, variant: 'info' }
    ];
  }, [stats]);

  // Filters config for ResponsiveLayout
  const filters = useMemo(() => [
    {
      key: 'action',
      label: 'Action',
      type: 'select',
      value: filterAction,
      onChange: (v) => { setFilterAction(v); setPage(1); },
      placeholder: LABELS.FILTERS.ALL_ACTIONS,
      options: (actions.actions || []).map(a => ({ value: a, label: a.replace(/_/g, ' ') }))
    },
    {
      key: 'status',
      label: 'Status',
      type: 'select',
      value: filterSuccess,
      onChange: (v) => { setFilterSuccess(v); setPage(1); },
      placeholder: LABELS.FILTERS.ALL_STATUS,
      options: [
        { value: 'true', label: t('common.success') },
        { value: 'false', label: t('common.failed') }
      ]
    },
    {
      key: 'username',
      label: 'User',
      type: 'select',
      value: filterUsername,
      onChange: (v) => { setFilterUsername(v); setPage(1); },
      placeholder: LABELS.FILTERS.ALL_USERS,
      options: uniqueUsernames.map(u => ({ value: u, label: u }))
    }
  ], [filterAction, filterSuccess, filterUsername, actions.actions, uniqueUsernames]);

  // Count active filters
  const activeFilters = useMemo(() => {
    let count = 0;
    if (filterAction) count++;
    if (filterSuccess) count++;
    if (filterUsername) count++;
    if (filterDateFrom) count++;
    if (filterDateTo) count++;
    return count;
  }, [filterAction, filterSuccess, filterUsername, filterDateFrom, filterDateTo]);

  // Help content
  const helpContent = (
    <div className="p-4 space-y-4">
      {/* Statistics */}
      {stats && (
        <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Database size={16} className="text-accent-primary" />
            {t('common.last30DaysStats')}
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="text-center p-3 bg-bg-tertiary rounded-lg">
              <p className="text-2xl font-bold text-text-primary">{stats.total_logs || 0}</p>
              <p className="text-xs text-text-secondary">{t('common.totalEvents')}</p>
            </div>
            <div className="text-center p-3 bg-bg-tertiary rounded-lg">
              <p className="text-2xl font-bold status-success-text">{stats.success_count || 0}</p>
              <p className="text-xs text-text-secondary">{t('common.successful')}</p>
            </div>
            <div className="text-center p-3 bg-bg-tertiary rounded-lg">
              <p className="text-2xl font-bold status-danger-text">{stats.failure_count || 0}</p>
              <p className="text-xs text-text-secondary">{t('common.failed')}</p>
            </div>
            <div className="text-center p-3 bg-bg-tertiary rounded-lg">
              <p className="text-2xl font-bold text-text-primary">{stats.unique_users || 0}</p>
              <p className="text-xs text-text-secondary">{t('common.activeUsers')}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title={t('audit.aboutAuditLogs')}>
          All user actions are logged for security and compliance purposes.
          Logs include timestamps, users, actions, resources, and IP addresses.
        </HelpCard>
        
        <HelpCard variant="tip" title={t('audit.filteringSearch')}>
          Use filters to narrow down logs by date range, user, action type, or status.
          The search box supports full-text search across all log fields.
        </HelpCard>

        <HelpCard variant="warning" title={t('audit.dataRetention')}>
          Old logs can be cleaned up to save storage space.
          The minimum retention period is 30 days for compliance requirements.
        </HelpCard>

        <HelpCard variant="info" title={t('audit.exportOptions')}>
          Export logs in JSON or CSV format for external analysis,
          compliance reporting, or integration with SIEM systems.
        </HelpCard>
      </div>
    </div>
  );

  // Date range filter slide-over content
  const dateFilterContent = (
    <div className="p-4 space-y-4">
      <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
        <Calendar size={16} />
        {t('audit.dateRange')}
      </h3>
      
      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1">{t('common.fromDate')}</label>
          <Input
            type="date"
            value={filterDateFrom}
            onChange={(e) => { setFilterDateFrom(e.target.value); setPage(1); }}
            className="w-full"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1">{t('common.toDate')}</label>
          <Input
            type="date"
            value={filterDateTo}
            onChange={(e) => { setFilterDateTo(e.target.value); setPage(1); }}
            className="w-full"
          />
        </div>
      </div>

      {/* Quick Filters */}
      <div className="space-y-2 pt-4 border-t border-border">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
          {t('common.quickFilters')}
        </h4>
        <div className="space-y-2">
          <Button 
            variant={filterAction === 'login_failure' ? 'primary' : 'ghost'} 
            size="sm" 
            className="w-full justify-start"
            onClick={() => { setFilterAction('login_failure'); setShowDateFilters(false); setPage(1); }}
          >
            <XCircle size={14} />
            {t('common.failedLogins')}
          </Button>
          <Button 
            variant={filterSuccess === 'false' && !filterAction ? 'primary' : 'ghost'} 
            size="sm" 
            className="w-full justify-start"
            onClick={() => { setFilterSuccess('false'); setFilterAction(''); setShowDateFilters(false); setPage(1); }}
          >
            <Warning size={14} />
            {t('common.allFailures')}
          </Button>
        </div>
      </div>

      {/* Clear Filters */}
      {activeFilters > 0 && (
        <Button 
          variant="secondary" 
          size="sm" 
          className="w-full" 
          onClick={() => { clearFilters(); setShowDateFilters(false); }}
        >
          <ArrowsClockwise size={14} />
          {t('common.clearAllFilters')}
        </Button>
      )}

      {/* Export Section */}
      <div className="space-y-2 pt-4 border-t border-border">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
          {t('audit.exportLogs')}
        </h4>
        <div className="flex gap-2">
          <Button 
            variant="secondary" 
            size="sm" 
            onClick={() => handleExport('json')}
            className="flex-1"
          >
            <Export size={14} />
            JSON
          </Button>
          <Button 
            variant="secondary" 
            size="sm" 
            onClick={() => handleExport('csv')}
            className="flex-1"
          >
            <Export size={14} />
            CSV
          </Button>
        </div>
      </div>
    </div>
  );

  // Log detail slide-over content
  const logDetailContent = selectedLog && (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={actionIcons[selectedLog.action] || actionIcons.default}
        iconClass={selectedLog.success ? "bg-status-success/20" : "bg-status-danger/20"}
        title={selectedLog.action?.replace(/_/g, ' ') || t('audit.event')}
        subtitle={`${selectedLog.resource_type || t('common.system')}${selectedLog.resource_name ? `: ${selectedLog.resource_name}` : (selectedLog.resource_id ? ` #${selectedLog.resource_id}` : '')}`}
        badge={
          <Badge variant={selectedLog.success ? 'emerald' : 'red'} size="sm">
            {selectedLog.success ? (
              <><CheckCircle size={12} weight="fill" /> {t('common.success')}</>
            ) : (
              <><XCircle size={12} weight="fill" /> {t('common.failed')}</>
            )}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: User, value: selectedLog.username || t('common.system') },
        { icon: ClockCounterClockwise, value: formatTime(selectedLog.timestamp) }
      ]} />

      <CompactSection title={t('audit.details')}>
        <CompactGrid>
          <CompactField 
            label={t('audit.timestamp')} 
            value={new Date(selectedLog.timestamp).toLocaleString()} 
          />
          <CompactField 
            label={t('audit.user')} 
            value={selectedLog.username || t('common.system')} 
          />
          <CompactField 
            label={t('audit.action')} 
            value={selectedLog.action?.replace(/_/g, ' ')} 
          />
          <CompactField 
            label={t('audit.target')} 
            value={`${selectedLog.resource_type || '-'}${selectedLog.resource_name ? `: ${selectedLog.resource_name}` : (selectedLog.resource_id ? ` #${selectedLog.resource_id}` : '')}`} 
          />
          <CompactField 
            label={t('audit.ipAddress')} 
            value={selectedLog.ip_address} 
            mono 
            copyable 
          />
          <CompactField 
            label={t('common.status')} 
            value={selectedLog.success ? t('common.success') : t('common.failed')} 
          />
        </CompactGrid>
      </CompactSection>

      {selectedLog.details && (
        <CompactSection title={t('audit.details')} collapsible>
          <pre className="text-2xs font-mono text-text-secondary bg-bg-tertiary/50 p-2 rounded overflow-x-auto max-h-32 overflow-y-auto whitespace-pre-wrap">
            {selectedLog.details}
          </pre>
        </CompactSection>
      )}

      {selectedLog.user_agent && (
        <CompactSection title={t('common.clientInfo')} collapsible defaultOpen={false}>
          <pre className="text-2xs font-mono text-text-secondary bg-bg-tertiary/50 p-2 rounded overflow-x-auto whitespace-pre-wrap">
            {selectedLog.user_agent}
          </pre>
        </CompactSection>
      )}
    </div>
  );

  // Header actions
  const headerActions = (
    <>
      {/* Desktop: Date filter button */}
      <Button 
        variant="secondary" 
        size="sm" 
        onClick={() => setShowDateFilters(true)}
        className="hidden md:inline-flex"
      >
        <Calendar size={14} />
        {t('common.date')}
        {(filterDateFrom || filterDateTo) && (
          <Badge variant="primary" size="sm" className="ml-1">1</Badge>
        )}
      </Button>
      <Button variant="secondary" size="sm" onClick={loadLogs} className="hidden md:inline-flex">
        <ArrowsClockwise size={14} />
      </Button>
      <Button variant="secondary" size="sm" onClick={() => setShowCleanupModal(true)}>
        <Trash size={14} className="text-status-danger" />
        <span className="hidden md:inline">{t('audit.cleanupLogs')}</span>
      </Button>
      {/* Mobile: More filters */}
      <Button 
        variant="secondary" 
        size="lg" 
        onClick={() => setShowDateFilters(true)}
        className="md:hidden h-11 w-11 p-0"
      >
        <FunnelSimple size={22} />
      </Button>
    </>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <>
      <ResponsiveLayout
        title={t('audit.title')}
        icon={ClockCounterClockwise}
        subtitle={t('common.countEntries', { count: total })}
        stats={headerStats}
        helpPageKey="auditLogs"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <ClockCounterClockwise size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('common.selectToView')}</p>
          </div>
        }
        slideOverOpen={!!selectedLog || showDateFilters}
        onSlideOverClose={() => { setSelectedLog(null); setShowDateFilters(false); }}
        slideOverTitle={selectedLog ? t('common.details') : t('common.filtersExport')}
        slideOverContent={selectedLog ? logDetailContent : dateFilterContent}
        slideOverWidth={selectedLog ? 'md' : 'sm'}
      >
        <ResponsiveDataTable
          data={logs}
          columns={columns}
          keyField="id"
          searchable
          externalSearch={search}
          onSearchChange={setSearch}
          searchPlaceholder={t('common.searchLogs')}
          toolbarFilters={[
            {
              key: 'action',
              value: filterAction,
              onChange: (v) => { setFilterAction(v); setPage(1); },
              placeholder: t('common.allActions'),
              options: (actions.actions || []).map(a => ({ value: a, label: a.replace(/_/g, ' ') }))
            },
            {
              key: 'status',
              value: filterSuccess,
              onChange: (v) => { setFilterSuccess(v); setPage(1); },
              placeholder: t('common.allStatus'),
              options: [
                { value: 'true', label: t('common.success') },
                { value: 'false', label: t('common.failed') }
              ]
            },
            {
              key: 'username',
              value: filterUsername,
              onChange: (v) => { setFilterUsername(v); setPage(1); },
              placeholder: t('common.allUsers'),
              options: uniqueUsernames.map(u => ({ value: u, label: u }))
            }
          ]}
          toolbarActions={headerActions}
          selectedId={selectedLog?.id}
          onRowClick={setSelectedLog}
          pagination={{
            page,
            perPage,
            total,
            onPageChange: setPage,
            onPerPageChange: (newPerPage) => { setPerPage(newPerPage); setPage(1); }
          }}
          emptyState={{
            icon: ClockCounterClockwise,
            title: t('audit.noLogs'),
            description: search || activeFilters > 0 ? t('common.tryAdjustFilters') : t('common.activityWillAppear')
          }}
        />
      </ResponsiveLayout>

      {/* Cleanup Modal */}
      <Modal
        open={showCleanupModal}
        onOpenChange={setShowCleanupModal}
        title={t('audit.cleanupLogs')}
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            {t('common.deleteOlderThanDays')}
          </p>
          
          <div>
            <label className="block text-xs font-medium mb-1">{t('common.retentionDays')}</label>
            <Input
              type="number"
              min={30}
              max={365}
              value={cleanupDays}
              onChange={(e) => setCleanupDays(Math.max(30, parseInt(e.target.value) || 90))}
            />
            <p className="text-xs text-text-secondary mt-1">
              {t('common.minimum')}: 30 {t('common.days')}
            </p>
          </div>
          
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="secondary" onClick={() => setShowCleanupModal(false)}>
              {t('common.cancel')}
            </Button>
            <Button 
              variant="danger" 
              onClick={handleCleanup}
              loading={cleanupLoading}
            >
              <Trash size={14} />
              {t('common.deleteOldLogs')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
