/**
 * ApprovalsPage — Approval Request Management
 * View, approve, and reject certificate approval requests.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Stamp, CheckCircle, XCircle, Clock, Warning, User,
  ChatText, Gavel, Certificate, Funnel
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Card, Button, Badge,
  Input, Modal, LoadingSpinner, Textarea
} from '../components'
import { approvalsService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, cn } from '../lib/utils'

const STATUS_VARIANTS = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
  expired: 'default',
}

const STATUS_ICONS = {
  pending: Clock,
  approved: CheckCircle,
  rejected: XCircle,
  expired: Warning,
}

export default function ApprovalsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { canWrite } = usePermission()

  // Data
  const [requests, setRequests] = useState([])
  const [stats, setStats] = useState({ pending: 0, approved: 0, rejected: 0, total: 0 })
  const [loading, setLoading] = useState(true)

  // Filters
  const [statusFilter, setStatusFilter] = useState('pending')

  // Detail
  const [selectedRequest, setSelectedRequest] = useState(null)

  // Action modals
  const [actionModal, setActionModal] = useState(null) // { type: 'approve'|'reject', request }
  const [comment, setComment] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [reqRes, statsRes] = await Promise.all([
        approvalsService.list(statusFilter),
        approvalsService.getStats(),
      ])
      setRequests(reqRes.data || [])
      setStats(statsRes.data || { pending: 0, approved: 0, rejected: 0, total: 0 })
    } catch (err) {
      showError(t('approvals.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [statusFilter, showError, t])

  useEffect(() => { loadData() }, [loadData])

  // Stats bar
  const statItems = useMemo(() => [
    {
      icon: Clock,
      label: t('approvals.pending'),
      value: stats.pending,
      variant: 'warning',
      filterValue: 'pending',
    },
    {
      icon: CheckCircle,
      label: t('approvals.approved'),
      value: stats.approved,
      variant: 'success',
      filterValue: 'approved',
    },
    {
      icon: XCircle,
      label: t('approvals.rejected'),
      value: stats.rejected,
      variant: 'danger',
      filterValue: 'rejected',
    },
    {
      icon: Stamp,
      label: t('approvals.total'),
      value: stats.total,
      variant: 'default',
      filterValue: 'all',
    },
  ], [stats, t])

  // Columns
  const columns = useMemo(() => [
    {
      key: 'id',
      header: '#',
      priority: 2,
      sortable: true,
      render: (val) => <span className="font-mono text-text-muted text-sm">#{val}</span>,
    },
    {
      key: 'request_type',
      header: t('common.type'),
      priority: 1,
      sortable: true,
      render: (val) => (
        <Badge variant={val === 'certificate' ? 'info' : val === 'revocation' ? 'danger' : 'default'}>
          {val}
        </Badge>
      ),
    },
    {
      key: 'requester_username',
      header: t('approvals.requester'),
      priority: 1,
      sortable: true,
      render: (val) => (
        <div className="flex items-center gap-1.5">
          <User size={14} className="text-text-muted" />
          <span className="text-text-primary">{val || '—'}</span>
        </div>
      ),
    },
    {
      key: 'policy_name',
      header: t('approvals.policy'),
      priority: 2,
      render: (val) => val ? (
        <div className="flex items-center gap-1.5">
          <Gavel size={14} className="text-text-muted" />
          <span className="text-text-secondary text-sm">{val}</span>
        </div>
      ) : <span className="text-text-muted">—</span>,
    },
    {
      key: 'status',
      header: t('common.status'),
      priority: 1,
      sortable: true,
      render: (val) => {
        const Icon = STATUS_ICONS[val] || Clock
        return (
          <Badge variant={STATUS_VARIANTS[val] || 'default'}>
            <Icon size={12} weight="fill" className="mr-1" />
            {val}
          </Badge>
        )
      },
    },
    {
      key: 'created_at',
      header: t('common.createdAt'),
      priority: 2,
      sortable: true,
      render: (val) => <span className="text-text-secondary text-sm">{formatDate(val)}</span>,
    },
  ], [t])

  // Row actions
  const rowActions = useCallback((row) => {
    if (row.status !== 'pending' || !canWrite('approvals')) return []
    return [
      {
        label: t('approvals.approve'),
        icon: CheckCircle,
        onClick: () => { setActionModal({ type: 'approve', request: row }); setComment('') },
      },
      {
        label: t('approvals.reject'),
        icon: XCircle,
        variant: 'danger',
        onClick: () => { setActionModal({ type: 'reject', request: row }); setComment('') },
      },
    ]
  }, [canWrite, t])

  // Handle approve/reject
  const handleAction = async () => {
    if (!actionModal) return
    const { type, request: req } = actionModal

    if (type === 'reject' && !comment.trim()) {
      showError(t('approvals.commentRequired'))
      return
    }

    try {
      setActionLoading(true)
      if (type === 'approve') {
        await approvalsService.approve(req.id, comment || undefined)
        showSuccess(t('approvals.approvedSuccess'))
      } else {
        await approvalsService.reject(req.id, comment)
        showSuccess(t('approvals.rejectedSuccess'))
      }
      setActionModal(null)
      setComment('')
      loadData()
    } catch (err) {
      showError(err.message || t('approvals.actionFailed'))
    } finally {
      setActionLoading(false)
    }
  }

  // Slide-over detail
  const slideOverContent = selectedRequest ? (
    <div className="p-4 space-y-4">
      {/* Status */}
      <div className="flex items-center gap-2">
        <Badge variant={STATUS_VARIANTS[selectedRequest.status]} size="lg">
          {selectedRequest.status}
        </Badge>
        <Badge variant={selectedRequest.request_type === 'certificate' ? 'info' : 'danger'}>
          {selectedRequest.request_type}
        </Badge>
      </div>

      {/* Request Info */}
      <div className="border-t border-border pt-3">
        <h4 className="text-sm font-semibold text-text-primary mb-2">{t('approvals.requestDetails')}</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="text-text-muted">{t('approvals.requester')}</div>
          <div className="text-text-primary">{selectedRequest.requester_username || '—'}</div>
          <div className="text-text-muted">{t('approvals.policy')}</div>
          <div className="text-text-primary">{selectedRequest.policy_name || '—'}</div>
          {selectedRequest.certificate_id && (
            <>
              <div className="text-text-muted">{t('approvals.certificateId')}</div>
              <div className="text-text-primary font-mono">#{selectedRequest.certificate_id}</div>
            </>
          )}
          <div className="text-text-muted">{t('common.createdAt')}</div>
          <div className="text-text-primary">{formatDate(selectedRequest.created_at)}</div>
          {selectedRequest.expires_at && (
            <>
              <div className="text-text-muted">{t('approvals.expiresAt')}</div>
              <div className="text-text-primary">{formatDate(selectedRequest.expires_at)}</div>
            </>
          )}
          {selectedRequest.resolved_at && (
            <>
              <div className="text-text-muted">{t('approvals.resolvedAt')}</div>
              <div className="text-text-primary">{formatDate(selectedRequest.resolved_at)}</div>
            </>
          )}
        </div>
      </div>

      {/* Requester Comment */}
      {selectedRequest.requester_comment && (
        <div className="border-t border-border pt-3">
          <h4 className="text-sm font-semibold text-text-primary mb-2">{t('approvals.requesterComment')}</h4>
          <p className="text-sm text-text-secondary bg-bg-tertiary rounded-lg p-3">
            {selectedRequest.requester_comment}
          </p>
        </div>
      )}

      {/* Approval History */}
      {selectedRequest.approvals?.length > 0 && (
        <div className="border-t border-border pt-3">
          <h4 className="text-sm font-semibold text-text-primary mb-2">{t('approvals.approvalHistory')}</h4>
          <div className="space-y-2">
            {selectedRequest.approvals.map((approval, idx) => (
              <div key={idx} className="flex items-start gap-2 text-sm bg-bg-tertiary rounded-lg p-3">
                {approval.action === 'approve'
                  ? <CheckCircle size={16} className="text-green-500 mt-0.5 shrink-0" weight="fill" />
                  : <XCircle size={16} className="text-red-500 mt-0.5 shrink-0" weight="fill" />
                }
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-text-primary">{approval.username}</span>
                    <span className="text-text-muted text-xs">{formatDate(approval.timestamp)}</span>
                  </div>
                  {approval.comment && (
                    <p className="text-text-secondary mt-0.5">{approval.comment}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      {selectedRequest.status === 'pending' && canWrite('approvals') && (
        <div className="border-t border-border pt-3 flex gap-2">
          <Button
            size="sm"
            onClick={() => { setActionModal({ type: 'approve', request: selectedRequest }); setComment('') }}
          >
            <CheckCircle size={14} className="mr-1" /> {t('approvals.approve')}
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={() => { setActionModal({ type: 'reject', request: selectedRequest }); setComment('') }}
          >
            <XCircle size={14} className="mr-1" /> {t('approvals.reject')}
          </Button>
        </div>
      )}
    </div>
  ) : null

  return (
    <>
      <ResponsiveLayout
        title={t('approvals.title')}
        subtitle={t('approvals.subtitle')}
        icon={Stamp}
        stats={statItems}
        activeStatFilter={statusFilter}
        onStatClick={(stat) => setStatusFilter(stat.filterValue || 'pending')}
        helpPageKey="approvals"
        slideOverOpen={!!selectedRequest}
        slideOverTitle={selectedRequest ? `#${selectedRequest.id} — ${selectedRequest.request_type}` : ''}
        slideOverContent={slideOverContent}
        onSlideOverClose={() => setSelectedRequest(null)}
        loading={loading}
      >
        <ResponsiveDataTable
          data={requests}
          columns={columns}
          loading={loading}
          selectedId={selectedRequest?.id}
          onRowClick={setSelectedRequest}
          rowActions={rowActions}
          searchable
          searchPlaceholder={t('approvals.searchPlaceholder')}
          searchKeys={['requester_username', 'policy_name', 'request_type', 'status']}
          sortable
          defaultSort={{ key: 'created_at', direction: 'desc' }}
          emptyIcon={Stamp}
          emptyTitle={t('approvals.noRequests')}
          emptyDescription={t('approvals.noRequestsDesc')}
        />
      </ResponsiveLayout>

      {/* Approve/Reject Modal */}
      <Modal
        open={!!actionModal}
        onOpenChange={(open) => { if (!open) { setActionModal(null); setComment('') } }}
        title={actionModal?.type === 'approve' ? t('approvals.approveRequest') : t('approvals.rejectRequest')}
        size="sm"
      >
        <div className="p-4 space-y-4">
          <div className="flex items-center gap-2 text-sm">
            {actionModal?.type === 'approve'
              ? <CheckCircle size={20} className="text-green-500" weight="fill" />
              : <XCircle size={20} className="text-red-500" weight="fill" />
            }
            <span className="text-text-primary">
              {actionModal?.type === 'approve'
                ? t('approvals.approveConfirm', { id: actionModal?.request?.id })
                : t('approvals.rejectConfirm', { id: actionModal?.request?.id })
              }
            </span>
          </div>

          <Textarea
            label={t('approvals.comment')}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={actionModal?.type === 'reject'
              ? t('approvals.rejectReasonPlaceholder')
              : t('approvals.commentPlaceholder')
            }
            rows={3}
            required={actionModal?.type === 'reject'}
          />

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => { setActionModal(null); setComment('') }}>
              {t('common.cancel')}
            </Button>
            <Button
              variant={actionModal?.type === 'approve' ? 'primary' : 'danger'}
              onClick={handleAction}
              disabled={actionLoading || (actionModal?.type === 'reject' && !comment.trim())}
            >
              {actionLoading ? <LoadingSpinner size="sm" /> : (
                actionModal?.type === 'approve' ? t('approvals.approve') : t('approvals.reject')
              )}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
