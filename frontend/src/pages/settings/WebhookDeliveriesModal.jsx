import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, ArrowClockwise, CaretLeft, CaretRight } from '@phosphor-icons/react'
import { Modal, Button, Badge } from '../../components'
import { useNotification } from '../../contexts'
import { settingsService } from '../../services'

const PER_PAGE = 25
const STATUS_VARIANT = { delivered: 'success', failed: 'danger', pending: 'warning' }

function rel(iso) {
  if (!iso) return '—'
  const d = Date.now() - new Date(iso).getTime()
  const future = d < 0
  const s = Math.abs(d) / 1000
  let t
  if (s < 60) t = '<1 min'
  else if (s < 3600) t = `${Math.round(s / 60)} min`
  else if (s < 86400) t = `${Math.round(s / 3600)} h`
  else t = `${Math.round(s / 86400)} d`
  return future ? `in ${t}` : `${t} ago`
}

export default function WebhookDeliveriesModal({ webhook, onClose, canRetry }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [retrying, setRetrying] = useState({})

  const loadSeq = useRef(0)
  const load = useCallback(async () => {
    if (!webhook) return
    // An answer older than the last request sent is dropped
    const seq = ++loadSeq.current
    setLoading(true)
    try {
      const res = await settingsService.getWebhookDeliveries(webhook.id, { page, perPage: PER_PAGE, status: statusFilter || undefined })
      if (seq !== loadSeq.current) return
      setItems((res.data || res) || [])
      setTotal(res.meta?.total ?? 0)
      setTotalPages(Math.max(1, res.meta?.total_pages ?? 1))
    } catch (e) {
      if (seq === loadSeq.current) showError(e.message || t('webhooks.deliveries.loadFailed'))
    } finally {
      if (seq === loadSeq.current) setLoading(false)
    }
  }, [webhook, statusFilter, page, showError, t])

  useEffect(() => { load() }, [load])

  const handleRetry = async (deliveryId) => {
    setRetrying((r) => ({ ...r, [deliveryId]: true }))
    try {
      await settingsService.retryWebhookDelivery(webhook.id, deliveryId)
      showSuccess(t('webhooks.deliveries.requeued'))
      await load()
    } catch (e) {
      showError(e.message || t('webhooks.deliveries.retryFailed'))
    } finally {
      setRetrying((r) => ({ ...r, [deliveryId]: false }))
    }
  }

  return (
    <Modal open={!!webhook} onClose={onClose}
           title={webhook ? t('webhooks.deliveries.title', { name: webhook.name }) : ''}>
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex gap-1">
            {['', 'pending', 'delivered', 'failed'].map((s) => (
              <Button key={s || 'all'} type="button" size="sm"
                      variant={statusFilter === s ? 'primary' : 'secondary'}
                      onClick={() => { setStatusFilter(s); setPage(1) }}>
                {s ? t(`webhooks.deliveries.status.${s}`) : t('common.all')}
              </Button>
            ))}
          </div>
          <Button type="button" size="sm" variant="secondary" onClick={load}>
            <ArrowsClockwise size={14} />{t('common.refresh')}
          </Button>
        </div>

        {loading ? (
          <div className="p-6 text-center text-sm text-text-secondary">{t('common.loading')}</div>
        ) : items.length === 0 ? (
          <div className="p-6 text-center text-sm text-text-secondary">{t('webhooks.deliveries.empty')}</div>
        ) : (
          <div className="max-h-[55vh] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-secondary">
                <tr className="text-left text-xs text-text-tertiary border-b border-border-op30">
                  <th className="py-2 pr-3 font-medium">{t('webhooks.deliveries.event')}</th>
                  <th className="py-2 px-3 font-medium">{t('webhooks.deliveries.statusCol')}</th>
                  <th className="py-2 px-3 font-medium text-right">{t('webhooks.deliveries.attempts')}</th>
                  <th className="py-2 px-3 font-medium">{t('webhooks.deliveries.when')}</th>
                  {canRetry && <th className="py-2 pl-3" />}
                </tr>
              </thead>
              <tbody>
                {items.map((d) => (
                  <tr key={d.id} className="border-b border-border-op30 last:border-0 align-top">
                    <td className="py-2 pr-3 font-mono text-xs text-text-primary">{d.event_type}</td>
                    <td className="py-2 px-3">
                      <Badge variant={STATUS_VARIANT[d.status] || 'secondary'} size="sm">{d.status}</Badge>
                      {d.last_error && (
                        <p className="text-xs text-status-warning mt-1 font-mono max-w-[260px] truncate" title={d.last_error}>
                          {d.last_response_code ? `${d.last_response_code} · ` : ''}{d.last_error}
                        </p>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right text-text-secondary tabular-nums">{d.attempts}/{d.max_attempts}</td>
                    <td className="py-2 px-3 text-text-secondary whitespace-nowrap">
                      {d.status === 'delivered' ? rel(d.delivered_at)
                        : d.status === 'pending' ? `${t('webhooks.deliveries.next')} ${rel(d.next_attempt_at)}`
                        : rel(d.created_at)}
                    </td>
                    {canRetry && (
                      <td className="py-2 pl-3 text-right">
                        {d.status !== 'pending' && (
                          <Button type="button" size="sm" variant="secondary"
                                  onClick={() => handleRetry(d.id)} disabled={!!retrying[d.id]}>
                            <ArrowClockwise size={13} />{t('webhooks.deliveries.retry')}
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-between text-xs text-text-secondary">
            <span className="tabular-nums">{page} / {totalPages} ({total})</span>
            <div className="flex gap-1">
              <Button type="button" size="sm" variant="secondary" aria-label={t('common.back')}
                      disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                <CaretLeft size={14} />
              </Button>
              <Button type="button" size="sm" variant="secondary" aria-label={t('common.next')}
                      disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                <CaretRight size={14} />
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
