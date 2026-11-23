/**
 * Orders of the built-in ACME server (#303 M6), drawn as the mockup's module list with its dock:
 * paged by the server, filtered by state, an order opens its detail; deletion and the purge of
 * expired orders stay with delete:acme. A linked order (?order=N) opens in the dock.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, Pill, ListView, Toolbar, Dock, DockBody, Section, Facts, EmptyBlock, useSortParam } from '../../components/atelier'
import { useDockSelection, asId } from '../../components/atelier/useDockParam'
import { apiClient } from '../../services'
import { buildQueryString } from '../../services/apiClient'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { stateLabel } from '../../lib/stateLabel'
import { dateTimeOf, dateOf } from '../admin/adminDates'
import { copyRow, fact } from '../../components/atelier/facts'
import { SlotDock } from '../protocols/dockSlot'

const TONES = { valid: 'good', ready: 'good', pending: 'warn', processing: 'warn', invalid: 'bad' }
const STATES = ['pending', 'ready', 'processing', 'valid', 'invalid']
const PER_PAGE = 50
// Paged by the server, so sorted by it: its keys, the newest order first
const NEWEST = { key: 'created_at', asc: false }
const SORT_KEYS = ['domain', 'account', 'expires', 'created_at', 'status']

export default function LocalOrdersTab({ linkedOrder = null, onCloseLinked, onTotal }) {
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
  const { sort, onSort } = useSortParam(NEWEST, SORT_KEYS)
  // A sort read from the address (a click, Back, a shared link) goes back to page one
  const sortMark = `${sort.key}:${sort.asc}`
  const [marked, setMarked] = useState(sortMark)
  if (marked !== sortMark) { setMarked(sortMark); setPage(1) }
  // The open order lives in the URL (`item`); one off the page (a link, a reload) is read by id
  const loadOrder = useCallback((id) => apiClient.get(`/acme/orders/${asId(id)}`).then((res) => res?.data), [])
  const orderSel = useDockSelection(items, { ready: !loading, load: loadOrder })
  const opened = orderSel.selected
  const setOpened = orderSel.select

  const load = useCallback(async (p = page, s = status) => {
    setLoading(true)
    try {
      const qs = buildQueryString({ page: p, per_page: PER_PAGE, status: s || undefined, sort_by: sort.key, sort_order: sort.asc ? 'asc' : 'desc' })
      const response = await apiClient.get(`/acme/orders${qs}`)
      const data = response?.data || response || {}
      const nextMeta = data.meta || { page: p, per_page: PER_PAGE, total: 0 }
      const totalPages = Math.max(1, Math.ceil(nextMeta.total / nextMeta.per_page))
      setMeta(nextMeta)
      // Unfiltered, the total is the view's: the page head and the tab say it
      if (!s) onTotal?.(nextMeta.total)
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
  }, [page, status, sort, showError, t, onTotal])

  useEffect(() => { load(page, status) }, [page, status, sort]) // eslint-disable-line react-hooks/exhaustive-deps
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
            <Facts items={[
              [t('acme.domains'), opened.domain], copyRow(t('acme.account'), opened.account, undefined, { long: true }),
              fact(t('acme.challengeType'), opened.method), [t('atelier.state'), pill(opened)],
              fact(t('common.expires'), dateOf(opened.expires, locale)), fact(t('common.created'), dateTimeOf(opened.created_at, locale)),
              opened.order_id && copyRow(t('acme.orderId'), opened.order_id, undefined, { long: true }),
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
          aside: <span className="phone-aside">{t('acme.localOrdersCount', { count: meta.total })}</span>,
        }}
        toolbar={(
          <Toolbar>
            {canDeleteOrders && <Btn icon="close" id="acme-orders-purge" onClick={handlePurge}>{t('acme.purgeLocalOrders')}</Btn>}
            {/* Refresh closes the bar on the right in every ACME view, as in Accounts */}
            <span className="spacer" />
            <IconBtn icon="refresh" label={t('common.refresh')} onClick={() => load()} />
          </Toolbar>
        )}
        title={(o) => o.domain} status={pill} openedId={opened?.id} onOpen={setOpened} nameSort="domain" sort={sort} onSort={onSort}
        columns={[
          { id: 'account', label: t('acme.account'), cell: (o) => <span className="mono">{o.account}</span>, kind: 'text', priority: 4, muted: true,
            title: (o) => o.account || undefined, sort: 'account' },
          { id: 'method', label: t('acme.method'), cell: (o) => o.method || '—', kind: 'fit', priority: 3 },
          { id: 'expires', label: t('common.expires'), labelFull: t('table.fullExpires'), cell: (o) => dateOf(o.expires, locale) || '—', kind: 'fit', priority: 2, labelled: true, sort: 'expires' },
          { id: 'created', label: t('common.created'), labelFull: t('table.fullCreated'), cell: (o) => dateTimeOf(o.created_at, locale) || '—', kind: 'fit', priority: 2, labelled: true, sort: 'created_at' },
          { status: true, sort: 'status' },
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
