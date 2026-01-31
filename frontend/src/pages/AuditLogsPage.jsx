/**
 * Audit Logs Page
 * View and filter audit logs with real-time updates
 */
import { useState, useEffect, useMemo } from 'react';
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
  Export
} from '@phosphor-icons/react';
import { 
  PageLayout,
  FocusItem,
  Card, 
  Button, 
  Badge, 
  Table, 
  SearchBar,
  Select, 
  Input,
  Modal,
  LoadingSpinner,
  EmptyState,
  Pagination,
  HelpCard,
  DetailHeader,
  DetailSection,
  DetailGrid,
  DetailField,
  DetailContent
} from '../components';
import { useNotification } from '../contexts';
import auditService from '../services/audit.service';

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
  const [totalPages, setTotalPages] = useState(0);
  
  // Filters
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
      setTotalPages(logsRes.meta?.total_pages || 0);
      setStats(statsRes.data || null);
      setActions(actionsRes.data || { actions: [], categories: {} });
    } catch (err) {
      console.error('Failed to load audit data:', err);
      showError('Failed to load audit logs');
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
      setTotalPages(res.meta?.total_pages || 0);
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
      
      showSuccess(`Exported audit logs as ${format.toUpperCase()}`);
    } catch (err) {
      showError('Failed to export logs');
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
      showError('Failed to cleanup logs');
    } finally {
      setCleanupLoading(false);
    }
  };

  const clearFilters = () => {
    setSearch('');
    setFilterUsername('');
    setFilterAction('');
    setFilterSuccess('');
    setFilterDateFrom('');
    setFilterDateTo('');
    setPage(1);
  };

  // Format timestamp
  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = (now - date) / 1000;
    
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    
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

  // Table columns
  const columns = [
    {
      key: 'timestamp',
      label: 'Time',
      sortable: true,
      render: (value) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatTime(value)}
        </span>
      )
    },
    {
      key: 'username',
      label: 'User',
      render: (value) => (
        <div className="flex items-center gap-1">
          <User size={12} className="text-text-secondary" />
          <span className="text-sm font-medium">{value || 'system'}</span>
        </div>
      )
    },
    {
      key: 'action',
      label: 'Action',
      render: (value) => {
        const category = getActionCategory(value);
        const color = categoryColors[category] || 'gray';
        const Icon = actionIcons[value] || actionIcons.default;
        return (
          <div className="flex items-center gap-1.5">
            <Icon size={14} className="text-text-secondary" />
            <Badge variant={color} size="sm">
              {value.replace(/_/g, ' ')}
            </Badge>
          </div>
        );
      }
    },
    {
      key: 'resource_type',
      label: 'Resource',
      render: (value, row) => (
        <span className="text-sm text-text-secondary">
          {value}{row.resource_id ? ` #${row.resource_id}` : ''}
        </span>
      )
    },
    {
      key: 'success',
      label: 'Status',
      render: (value) => (
        value ? (
          <Badge variant="emerald" size="sm">
            <CheckCircle size={12} weight="fill" />
            OK
          </Badge>
        ) : (
          <Badge variant="red" size="sm">
            <XCircle size={12} weight="fill" />
            Failed
          </Badge>
        )
      )
    },
    {
      key: 'ip_address',
      label: 'IP',
      render: (value) => (
        <span className="text-xs text-text-secondary font-mono">{value || '-'}</span>
      )
    }
  ];

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* Statistics */}
      {stats && (
        <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Database size={16} className="text-accent-primary" />
            Last 30 Days Statistics
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="text-center p-3 bg-bg-tertiary rounded-lg">
              <p className="text-2xl font-bold text-text-primary">{stats.total_logs || 0}</p>
              <p className="text-xs text-text-secondary">Total Events</p>
            </div>
            <div className="text-center p-3 bg-bg-tertiary rounded-lg">
              <p className="text-2xl font-bold text-emerald-500">{stats.success_count || 0}</p>
              <p className="text-xs text-text-secondary">Successful</p>
            </div>
            <div className="text-center p-3 bg-bg-tertiary rounded-lg">
              <p className="text-2xl font-bold text-red-500">{stats.failure_count || 0}</p>
              <p className="text-xs text-text-secondary">Failed</p>
            </div>
            <div className="text-center p-3 bg-bg-tertiary rounded-lg">
              <p className="text-2xl font-bold text-text-primary">{stats.unique_users || 0}</p>
              <p className="text-xs text-text-secondary">Active Users</p>
            </div>
          </div>
        </Card>
      )}

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="About Audit Logs">
          All user actions are logged for security and compliance purposes.
          Logs include timestamps, users, actions, resources, and IP addresses.
        </HelpCard>
        
        <HelpCard variant="tip" title="Filtering & Search">
          Use filters to narrow down logs by date range, user, action type, or status.
          The search box supports full-text search across all log fields.
        </HelpCard>

        <HelpCard variant="warning" title="Data Retention">
          Old logs can be cleaned up to save storage space.
          The minimum retention period is 30 days for compliance requirements.
        </HelpCard>

        <HelpCard variant="info" title="Export Options">
          Export logs in JSON or CSV format for external analysis,
          compliance reporting, or integration with SIEM systems.
        </HelpCard>
      </div>
    </div>
  );

  // Focus panel content - Filters
  const focusContent = (
    <div className="p-3 space-y-4">
      {/* Date Range Filter */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
          Date Range
        </h4>
        <div className="space-y-2">
          <Input
            type="date"
            value={filterDateFrom}
            onChange={(e) => { setFilterDateFrom(e.target.value); setPage(1); }}
            placeholder="From"
            className="w-full"
          />
          <Input
            type="date"
            value={filterDateTo}
            onChange={(e) => { setFilterDateTo(e.target.value); setPage(1); }}
            placeholder="To"
            className="w-full"
          />
        </div>
      </div>

      {/* Action Type Filter */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
          Action Type
        </h4>
        <Select
          value={filterAction}
          onChange={(v) => { setFilterAction(v); setPage(1); }}
          placeholder="All Actions"
          className="w-full"
        >
          <option value="">All Actions</option>
          {(actions.actions || []).map(action => (
            <option key={action} value={action}>{action.replace(/_/g, ' ')}</option>
          ))}
        </Select>
      </div>

      {/* User Filter */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
          User
        </h4>
        <Select
          value={filterUsername}
          onChange={(v) => { setFilterUsername(v); setPage(1); }}
          placeholder="All Users"
          className="w-full"
        >
          <option value="">All Users</option>
          {uniqueUsernames.map(name => (
            <option key={name} value={name}>{name}</option>
          ))}
        </Select>
      </div>

      {/* Status Filter */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
          Status
        </h4>
        <Select
          value={filterSuccess}
          onChange={(v) => { setFilterSuccess(v); setPage(1); }}
          placeholder="All Status"
          className="w-full"
        >
          <option value="">All Status</option>
          <option value="true">Success</option>
          <option value="false">Failed</option>
        </Select>
      </div>

      {/* Quick Filters */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
          Quick Filters
        </h4>
        <div className="space-y-1">
          <FocusItem 
            icon={XCircle}
            title="Failed Logins"
            subtitle="Security events"
            selected={filterAction === 'login_failure'}
            onClick={() => { setFilterAction('login_failure'); setPage(1); }}
          />
          <FocusItem 
            icon={Warning}
            title="All Failures"
            subtitle="Error events"
            selected={filterSuccess === 'false' && !filterAction}
            onClick={() => { setFilterSuccess('false'); setFilterAction(''); setPage(1); }}
          />
        </div>
      </div>

      {/* Clear Filters */}
      {(search || filterUsername || filterAction || filterSuccess || filterDateFrom || filterDateTo) && (
        <Button variant="ghost" size="sm" className="w-full" onClick={clearFilters}>
          <ArrowsClockwise size={14} />
          Clear All Filters
        </Button>
      )}
    </div>
  );

  // Focus panel actions - Export buttons
  const focusActions = (
    <>
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
    <PageLayout
      title="Audit Logs"
      focusTitle="Filters"
      focusContent={focusContent}
      focusActions={focusActions}
      focusFooter={`${total} log entries`}
      helpContent={helpContent}
      
    >
      {/* Main Content */}
      <div className="flex flex-col h-full">
        {/* Header - Search Bar and Refresh */}
        <div className="p-4 border-b border-border space-y-3">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <SearchBar
                value={search}
                onChange={setSearch}
                placeholder="Search logs..."
              />
            </div>
            <Button variant="secondary" size="sm" onClick={loadLogs}>
              <ArrowsClockwise size={14} />
              Refresh
            </Button>
            <Button variant="danger" size="sm" onClick={() => setShowCleanupModal(true)}>
              <Trash size={14} />
              Cleanup
            </Button>
          </div>

          {/* Results info */}
          <div className="text-xs text-text-secondary">
            Showing {logs.length} of {total} entries
            {(search || filterUsername || filterAction || filterSuccess || filterDateFrom || filterDateTo) && (
              <span className="ml-1">(filtered)</span>
            )}
          </div>
        </div>

        {/* Logs Table - Scrollable */}
        <div className="flex-1 overflow-auto">
          {logs.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={ClockCounterClockwise}
                title="No audit logs found"
                description={search || filterAction ? "Try adjusting your filters" : "Activity will appear here"}
              />
            </div>
          ) : (
            <Table
              data={logs}
              columns={columns}
              onRowClick={setSelectedLog}
            />
          )}
        </div>
        
        {/* Pagination - Fixed at bottom */}
        {total > perPage && (
          <div className="border-t border-border bg-bg-secondary">
            <Pagination
              page={page}
              total={total}
              perPage={perPage}
              onChange={setPage}
              onPerPageChange={(newPerPage) => { setPerPage(newPerPage); setPage(1); }}
            />
          </div>
        )}
      </div>

      {/* Log Detail Modal */}
      <Modal
        open={!!selectedLog}
        onOpenChange={() => setSelectedLog(null)}
        title="Log Details"
        size="md"
      >
        {selectedLog && (
          <DetailContent className="p-0">
            {/* Header with action type, icon, and status badge */}
            <DetailHeader
              icon={actionIcons[selectedLog.action] || actionIcons.default}
              title={selectedLog.action?.replace(/_/g, ' ') || 'Event'}
              subtitle={`${selectedLog.resource_type || 'System'}${selectedLog.resource_id ? ` #${selectedLog.resource_id}` : ''}`}
              badge={
                <Badge variant={selectedLog.success ? 'emerald' : 'red'} size="sm">
                  {selectedLog.success ? (
                    <><CheckCircle size={12} weight="fill" /> Success</>
                  ) : (
                    <><XCircle size={12} weight="fill" /> Failed</>
                  )}
                </Badge>
              }
              stats={[
                { icon: User, label: 'User:', value: selectedLog.username || 'system' },
                { icon: ClockCounterClockwise, label: 'Time:', value: formatTime(selectedLog.timestamp) }
              ]}
            />

            {/* Event Details Section */}
            <DetailSection title="Event Details">
              <DetailGrid>
                <DetailField 
                  label="Timestamp" 
                  value={new Date(selectedLog.timestamp).toLocaleString()} 
                />
                <DetailField 
                  label="User" 
                  value={selectedLog.username || 'system'} 
                />
                <DetailField 
                  label="Action" 
                  value={selectedLog.action?.replace(/_/g, ' ')} 
                />
                <DetailField 
                  label="Resource" 
                  value={`${selectedLog.resource_type || '-'}${selectedLog.resource_id ? ` #${selectedLog.resource_id}` : ''}`} 
                />
                <DetailField 
                  label="IP Address" 
                  value={selectedLog.ip_address} 
                  mono 
                  copyable 
                />
                <DetailField 
                  label="Status" 
                  value={selectedLog.success ? 'Success' : 'Failed'} 
                />
              </DetailGrid>
            </DetailSection>

            {/* Details Section - if present */}
            {selectedLog.details && (
              <DetailSection title="Details">
                <DetailField 
                  label="Event Details" 
                  value={selectedLog.details} 
                  mono 
                  fullWidth 
                  copyable
                />
              </DetailSection>
            )}

            {/* User Agent Section - if present */}
            {selectedLog.user_agent && (
              <DetailSection title="Client Information">
                <DetailField 
                  label="User Agent" 
                  value={selectedLog.user_agent} 
                  mono 
                  fullWidth 
                  copyable
                />
              </DetailSection>
            )}
          </DetailContent>
        )}
      </Modal>

      {/* Cleanup Modal */}
      <Modal
        open={showCleanupModal}
        onOpenChange={setShowCleanupModal}
        title="Cleanup Old Logs"
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Delete audit logs older than the specified number of days.
            This action cannot be undone.
          </p>
          
          <div>
            <label className="block text-xs font-medium mb-1">Retention Days</label>
            <Input
              type="number"
              min={30}
              max={365}
              value={cleanupDays}
              onChange={(e) => setCleanupDays(Math.max(30, parseInt(e.target.value) || 90))}
            />
            <p className="text-xs text-text-secondary mt-1">
              Minimum: 30 days
            </p>
          </div>
          
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="secondary" onClick={() => setShowCleanupModal(false)}>
              Cancel
            </Button>
            <Button 
              variant="danger" 
              onClick={handleCleanup}
              loading={cleanupLoading}
            >
              <Trash size={14} />
              Delete Old Logs
            </Button>
          </div>
        </div>
      </Modal>
    </PageLayout>
  );
}
