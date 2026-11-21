/**
 * Orders of the built-in ACME server (#303 M6), drawn as the mockup's module list with its dock:
 * paged by the server, filtered by state, an order opens its detail; deletion and the purge of
 * expired orders stay with delete:acme. A linked order (?order=N) opens in the dock.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, Pill, ListView, Toolbar, Dock, DockBody, Section, Props, EmptyBlock } from '../../components/atelier'
import { useDockSelection, asId } from '../../components/atelier/useDockParam'
import { apiClient } from '../../services'
import { buildQueryString } from '../../services/apiClient'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { stateLabel } from '../../lib/stateLabel'
import { dateTimeOf, dateOf } from '../admin/adminDates'
import { Copyable } from '../protocols/atelierParts'
import { SlotDock } from '../protocols/dockSlot'

const TONES = { valid: 'good', ready: 'good', pending: 'warn', processing: 'warn', invalid: 'bad' }
const STATES = ['pending', 'ready', 'processing', 'valid', 'invalid']
const PER_PAGE = 50

export default function LocalOrdersTab({ linkedOrder = null, onCloseLinked }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canDelete } = usePermission()
  const canDeleteOrders = canDelete('acme')
  const [items, setItems] = useState([])
  const [meta, setMeta] = useState({ page: 1, per_page: PER_PAGE, total: 0 })
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  // The open order lives in the URL (`item`); one off the page (a link, a reload) is read by id
  const loadOrder = useCallback((id) => apiClient.get(`/acme/orders/${asId(id)}`).then((res) => res?.data), [])
  const orderSel = useDockSelection(items, { ready: !loading, load: loadOrder })
  const opened = orderSel.selected
  const setOpened = orderSel.select

  const load = useCallback(async (p = page, s = status) => {
    setLoading(true)
    try {
      const qs = buildQueryString({ page: p, per_page: PER_PAGE, status: s || undefined })
      const response = await apiClient.get(`/acme/orders${qs}`)
      const data = response?.data || response || {}
      const nextMeta = data.meta || { page: p, per_page: PER_PAGE, total: 0 }
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
  useEffect(() => { if (linkedOrder) setOpened(linkedOrder) }, [linkedOrder]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleDelete = async (row) => {
    const confirmed = await showConfirm(t('acme.deleteLocalOrderConfirmDesc', { domain: row.domain }), {
      title: t('acme.deleteLocalOrderConfirm'), confirmText: t('common.delete'), cancelText: t('common.cancel'), variant: 'danger',
    })
    if (!confirmed) return
    try {
      await apiClient.delete(`/acme/orders/${row.id}`)
      showSuccess(t('acme.localOrderDeleted'))
      if (opened?.id === row.id) setOpened(null)
      load()
    } catch (err) {
      showError(err.message || t('common.deleteFailed'))
    }
  }

  const handlePurge = async () => {
    const confirmed = await showConfirm(t('acme.purgeLocalOrdersConfirmDesc'), {
      title: t('acme.purgeLocalOrdersConfirm'), confirmText: t('acme.purgeLocalOrders'), cancelText: t('common.cancel'), variant: 'danger',
    })
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

  const tone = (o) => TONES[String(o.status || '').toLowerCase()] || 'muted'
  const pill = (o) => <Pill label={stateLabel(t, o.status)} tone={tone(o)} />
  const pages = Math.max(1, Math.ceil((meta.total || 0) / (meta.per_page || PER_PAGE)))
  const close = () => { setOpened(null); onCloseLinked?.() }

  const dock = opened && (
    <Dock label={t('atelier.detailOf', { name: t('acme.localOrders') })} tabsLabel={t('atelier.openItem')} activeKey={opened.id}
      tabs={[{ key: opened.id, title: opened.domain, icon: 'refresh' }]} onClose={close}>
      <DockBody icon="refresh" title={opened.domain} badge={pill(opened)} section="order" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: opened.domain })} sections={[['order', t('acme.orderInfo')]]}
        actions={canDeleteOrders && <Btn icon="close" id="acme-order-delete" onClick={() => handleDelete(opened)}>{t('common.delete')}</Btn>}>
        <div className="module-detail">
          <Section title={t('acme.orderInfo')}>
            <Props items={[
              [t('acme.domains'), opened.domain], [t('acme.account'), <span key="a" className="mono">{opened.account}</span>],
              [t('acme.challengeType'), opened.method || '—'], [t('atelier.state'), pill(opened)],
              [t('common.expires'), dateOf(opened.expires, locale) || '—'], [t('common.created'), dateTimeOf(opened.created_at, locale) || '—'],
              opened.order_id && [t('acme.orderId'), <Copyable key="o" value={opened.order_id} label={t('acme.orderId')} />],
            ]} />
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

  return (
    <>
      <ListView label={t('acme.localOrders')} caption={t('acme.ordersCaption')} icon="refresh" rows={items} loading={loading}
        filters={{
          views: [{ id: '', label: t('common.all') }, ...STATES.map((s) => ({ id: s, label: stateLabel(t, s) }))],
          active: status, onChange: (v) => { setPage(1); setStatus(v) }, label: t('acme.filterByState'),
          aside: t('acme.localOrdersCount', { count: meta.total }),
        }}
        toolbar={(
          <Toolbar>
            <IconBtn icon="refresh" label={t('common.refresh')} onClick={() => load()} />
            {canDeleteOrders && <Btn icon="close" id="acme-orders-purge" onClick={handlePurge}>{t('acme.purgeLocalOrders')}</Btn>}
          </Toolbar>
        )}
        title={(o) => o.domain} status={pill} openedId={opened?.id} onOpen={setOpened}
        columns={[
          { id: 'account', label: t('acme.account'), cell: (o) => <span className="mono">{o.account}</span>, grow: true, muted: true },
          { id: 'method', label: t('acme.challengeType'), cell: (o) => o.method || '—' },
          { id: 'expires', label: t('common.expires'), cell: (o) => dateOf(o.expires, locale) || '—' },
          { id: 'created', label: t('common.created'), cell: (o) => dateTimeOf(o.created_at, locale) || '—' },
          { status: true },
        ]}
        rowActions={canDeleteOrders ? () => [{ icon: 'close', label: t('common.delete'), onClick: handleDelete, write: true }] : undefined}
        empty={<EmptyBlock id="acme-orders" icon="refresh" title={t('acme.noLocalOrders')} text={t('acme.noLocalOrdersDesc')} />}
        footer={{
          range: t('acme.localOrdersCount', { count: meta.total }),
          pagination: meta.total > (meta.per_page || PER_PAGE) ? { page, pages, perPage: PER_PAGE, sizes: [PER_PAGE], onPage: setPage } : undefined,
        }} />
      <SlotDock>{dock}</SlotDock>
    </>
  )
}
