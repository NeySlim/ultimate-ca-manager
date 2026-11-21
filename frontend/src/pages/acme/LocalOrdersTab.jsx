/**
 * LocalOrdersTab — orders of the built-in ACME server (#303 M6).
 * Self-contained: fetches its own data, supports status filter, delete and
 * purge of expired orders.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash, Broom, ArrowsClockwise, Globe } from '@phosphor-icons/react'
import { Badge, Button, EmptyState, ResponsiveDataTable, FilterSelect } from '../../components'
import { apiClient } from '../../services'
import { buildQueryString } from '../../services/apiClient'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { formatDate } from '../../lib/utils'
import { stateLabel } from '../../lib/stateLabel'

const STATUS_VARIANT = {
  valid: 'success', ready: 'info', pending: 'warning',
  processing: 'warning', invalid: 'danger',
}

export default function LocalOrdersTab({ linkedOrder = null, onCloseLinked }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canDelete } = usePermission()
  const canDeleteOrders = canDelete('acme')
  const [items, setItems] = useState([])
  const [meta, setMeta] = useState({ page: 1, per_page: 50, total: 0 })
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (p = page, s = status) => {
    setLoading(true)
    try {
      const qs = buildQueryString({ page: p, per_page: 50, status: s || undefined })
      const response = await apiClient.get(`/acme/orders${qs}`)
      const data = response?.data || response || {}
      const nextMeta = data.meta || { page: p, per_page: 50, total: 0 }
      const totalPages = Math.max(1, Math.ceil(nextMeta.total / nextMeta.per_page))
      setMeta(nextMeta)
      if (p > totalPages) {
        setPage(totalPages)
        return
      }
      setItems(data.items || [])
    } catch (err) {
      showError(err.message || t('acme.localOrdersLoadFailed'))
    } finally {
      setLoading(false)
    }
  }, [page, status, showError, t])

  useEffect(() => { load(page, status) }, [page, status]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleDelete = async (row) => {
    const confirmed = await showConfirm(
      t('acme.deleteLocalOrderConfirmDesc', { domain: row.domain }),
      {
        title: t('acme.deleteLocalOrderConfirm'),
        confirmText: t('common.delete'),
        cancelText: t('common.cancel'),
        variant: 'danger',
      }
    )
    if (!confirmed) return
    try {
      await apiClient.delete(`/acme/orders/${row.id}`)
      showSuccess(t('acme.localOrderDeleted'))
      load()
    } catch (err) {
      showError(err.message || t('common.deleteFailed'))
    }
  }

  const handlePurge = async () => {
    const confirmed = await showConfirm(
      t('acme.purgeLocalOrdersConfirmDesc'),
      {
        title: t('acme.purgeLocalOrdersConfirm'),
        confirmText: t('acme.purgeLocalOrders'),
        cancelText: t('common.cancel'),
        variant: 'danger',
      }
    )
    if (!confirmed) return
    try {
      const response = await apiClient.post('/acme/orders/purge')
      const stats = response?.data || {}
      showSuccess(t('acme.purgeLocalOrdersDone', { count: stats.orders ?? 0 }))
      load()
    } catch (err) {
      showError(err.message || t('acme.purgeLocalOrdersFailed'))
    }
  }

  const columns = useMemo(() => [
    { key: 'domain', header: t('acme.domains'), priority: 1, sortable: true },
    { key: 'account', header: t('acme.account'), priority: 3,
      render: (v) => <span className="text-xs text-text-tertiary truncate">{v}</span> },
    { key: 'status', header: t('common.status'), priority: 1,
      render: (v) => <Badge variant={STATUS_VARIANT[(v || '').toLowerCase()] || 'default'}>{stateLabel(t, v)}</Badge> },
    { key: 'method', header: t('acme.challengeType'), priority: 4 },
    { key: 'expires', header: t('common.expires'), priority: 2,
      render: (v) => v ? formatDate(v) : '-' },
    { key: 'created_at', header: t('common.created'), priority: 3,
      render: (v) => v ? formatDate(v) : '-' },
    ...(canDeleteOrders ? [{
      key: '_actions', header: '', priority: 1,
      render: (_v, row) => (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label={t('common.delete')}
          onClick={(e) => { e.stopPropagation(); handleDelete(row) }}
        >
          <Trash size={14} />
        </Button>
      ),
    }] : []),
  ], [t, canDeleteOrders]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FilterSelect
            value={status}
            onChange={(v) => { setPage(1); setStatus(v) }}
            allLabel={t('common.allStatuses')}
            options={['pending', 'ready', 'processing', 'valid', 'invalid'].map(sv => ({ value: sv, label: stateLabel(t, sv) }))}
          />
          <span className="text-xs text-text-tertiary">{t('acme.localOrdersCount', { count: meta.total })}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={() => load()}>
            <ArrowsClockwise size={14} />
          </Button>
          {canDeleteOrders && (
            <Button type="button" size="sm" variant="secondary" onClick={handlePurge}>
              <Broom size={14} />
              {t('acme.purgeLocalOrders')}
            </Button>
          )}
        </div>
      </div>

      {linkedOrder && (
        <div aria-current="true" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-accent-primary p-3">
          <div className="min-w-0">
            <div className="text-sm font-medium text-text-primary truncate">{linkedOrder.domain}</div>
            <div className="text-xs text-text-tertiary">
              {linkedOrder.account} · {linkedOrder.method} · {linkedOrder.created_at ? formatDate(linkedOrder.created_at) : '-'}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={STATUS_VARIANT[(linkedOrder.status || '').toLowerCase()] || 'default'}>{stateLabel(t, linkedOrder.status)}</Badge>
            {onCloseLinked && <Button type="button" size="sm" variant="ghost" onClick={onCloseLinked}>{t('common.close')}</Button>}
          </div>
        </div>
      )}

      {items.length === 0 && !loading ? (
        <EmptyState icon={Globe} title={t('acme.noLocalOrders')} description={t('acme.noLocalOrdersDesc')} />
      ) : (
        <ResponsiveDataTable
          columns={columns}
          data={items}
          selectable={false}
        />
      )}

      {meta.total > meta.per_page && (
        <div className="flex items-center justify-end gap-2 text-xs">
          <Button type="button" size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</Button>
          <span>{page} / {Math.max(1, Math.ceil(meta.total / meta.per_page))}</span>
          <Button type="button" size="sm" variant="ghost" disabled={page >= Math.ceil(meta.total / meta.per_page)} onClick={() => setPage(page + 1)}>›</Button>
        </div>
      )}
    </div>
  )
}
