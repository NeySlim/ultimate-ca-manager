import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Icon, Pill, RecordList, RecordRow, TableFooter } from '../../components/atelier'
import { Modal, SegmentedField } from '../../components/atelier/Form'
import { useNotification } from '../../contexts'
import { settingsService } from '../../services'
import { relativeAgo, relativeDue } from '../../lib/relativeTime'

const PER_PAGE = 25
const STATUS_TONE = { delivered: 'good', failed: 'bad', pending: 'warn' }

export default function WebhookDeliveriesModal({ webhook, onClose, canRetry }) {
  const { t, i18n } = useTranslation()
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

  const number = new Intl.NumberFormat(i18n?.language || undefined)
  const when = (d) => (d.status === 'delivered' ? relativeAgo(d.delivered_at, t)
    : d.status === 'pending' ? `${t('webhooks.deliveries.next')} ${relativeDue(d.next_attempt_at, t)}`
      : relativeAgo(d.created_at, t)) || '—'

  // The mockup's dialog: the state as a segmented choice, the deliveries as records, the table footer to page them
  return (
    <Modal open={!!webhook} onClose={onClose} size="lg"
           title={webhook ? t('webhooks.deliveries.title', { name: webhook.name }) : ''}>
      <div className="settings-stack">
        <div className="settings-actions">
          <SegmentedField id="webhook-deliveries-status" full={false} label={t('webhooks.deliveries.statusCol')}
            options={['', 'pending', 'delivered', 'failed'].map((s) => ({ value: s, label: s ? t(`webhooks.deliveries.status.${s}`) : t('common.all') }))}
            pressed={(s) => statusFilter === s} onPick={(s) => { setStatusFilter(s); setPage(1) }} />
          <Btn icon="refresh" onClick={load}>{t('common.refresh')}</Btn>
        </div>

        {loading ? (
          <p className="muted small" role="status">{t('common.loading')}</p>
        ) : (
          <RecordList empty={t('webhooks.deliveries.empty')}>
            {items.map((d) => (
              <RecordRow key={d.id} title={<span className="mono">{d.event_type}</span>}
                meta={`${when(d)} · ${t('webhooks.deliveries.attempts')} ${d.attempts}/${d.max_attempts}`}
                extra={d.last_error && (
                  <span className="rl-error" title={d.last_error}><Icon name="warning" /><span className="mono">{d.last_response_code ? `${d.last_response_code} · ` : ''}{d.last_error}</span></span>
                )}
                badge={<Pill tone={STATUS_TONE[d.status] || 'muted'} label={t(`webhooks.deliveries.status.${d.status}`, { defaultValue: d.status })} />}
                action={canRetry && d.status !== 'pending' && (
                  <Btn icon="refresh" write onClick={() => handleRetry(d.id)} disabled={!!retrying[d.id] || undefined}>{t('webhooks.deliveries.retry')}</Btn>
                )} />
            ))}
          </RecordList>
        )}

        {totalPages > 1 && (
          <PageFooter page={page} pages={totalPages} total={total} number={number} onPage={setPage} t={t} />
        )}
      </div>
    </Modal>
  )
}

/** The table footer of the mockup: the range in words, previous, the page, next. */
function PageFooter({ page, pages, total, number, onPage, t }) {
  return (
    <TableFooter
      range={t('table.range', { start: number.format((page - 1) * PER_PAGE + 1), end: number.format(Math.min(page * PER_PAGE, total)), total })}
      pagination={{ page, pages, onPage }} />
  )
}
