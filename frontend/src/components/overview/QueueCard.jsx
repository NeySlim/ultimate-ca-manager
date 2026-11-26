/**
 * The mockup's queueCard() and queueRow() over GET /dashboard/queue: chips per type, the
 * interventions by urgency (six shown, the others folded), then the rows only to watch.
 */
import { useContext, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { Icon, QueueDue } from '../atelier'
import { acmeService, certificatesService, crlService, overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { listHref } from '../../lib/overviewFilters'
import { GROUP_OF, QUEUE_GROUPS, SINCE_KINDS, UNDATED_KINDS, isWatch } from '../../lib/overviewQueue'
import { askRenewal } from '../../lib/renewalPrompt'
import { compactAgo, compactDue, dueTone } from '../../lib/relativeTime'
import { DAY_MS, countdownShare } from '../../lib/overviewQueue'
import { formatDate } from '../../lib/utils'
import { CardEmpty, OverviewCard, OverviewContext, num, useCardData } from './shared'

const VISIBLE = 6
// The mockup's queueTypes icons; a group the mockup has not (deployments) takes the server icon
const GROUP_ICON = { renew: 'refresh', acme: 'warning', request: 'approve', crl: 'crl', ca: 'shield', deploy: 'server' }
// The mockup colours its kind pill by data-type: its approval type is the product's request group
const TYPE_OF = { request: 'approval' }
const REVIEW_KINDS = ['approval_pending', 'scep_request_pending', 'key_recovery_pending']

/**
 * The operations the API offers on a queue row, inside the page (its notifier); any other row
 * links to its object. A failed relaunch or publication leaves a message with Réessayer.
 */
function useRowActions(reload) {
  const { t } = useTranslation()
  const notify = useContext(OverviewContext)?.notify
  const { hasPermission } = usePermission()
  const [busy, setBusy] = useState(null)
  const done = (message, type) => {
    notify.showSuccess(message)
    window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type } }))
    reload()
  }
  const run = (item, work, again = false) => {
    const go = async () => {
      if (busy) return
      setBusy(`${item.kind}-${item.id}`)
      try {
        await work()
      } catch (error) {
        const message = error?.message || t('overview.queue.actionFailed')
        // Only an operation the user may start again by hand offers to (the server keeps its own guards)
        notify.showError(message, again ? { action: { label: t('overview.queue.again'), onClick: () => go() } } : undefined)
      } finally {
        setBusy(null)
      }
    }
    return go
  }
  const actionOf = (item) => {
    if (!notify) return null
    if (item.kind === 'manual_renewal_due' && hasPermission('write:certificates')) {
      return { icon: 'refresh', label: t('common.renew'), run: run(item, async () => {
        const cert = (await certificatesService.getById(item.id))?.data
        const body = await askRenewal(cert, { ...notify, t })
        if (body === null) return
        await certificatesService.renew(item.id, body)
        done(t('certificates.renewed'), 'certificate')
      }) }
    }
    if (item.kind === 'acme_client_renewal_failed' && hasPermission('write:acme')) {
      return { icon: 'refresh', label: t('overview.queue.retry'), run: run(item, async () => {
        await acmeService.renewOrder(item.id)
        done(t('overview.queue.retried'), 'certificate')
      }, true) }
    }
    if ((item.kind === 'crl_due' || item.kind === 'crl_missing') && hasPermission('write:crl')) {
      return { icon: 'send', label: t('overview.queue.publish'), run: run(item, async () => {
        await crlService.regenerate(item.id)
        done(t('notifications.crlRegenerated', { name: item.label }), 'ca')
      }, true) }
    }
    return null
  }
  return { actionOf, busy }
}

/** The row's deadline: a delay and the date, the countdown under it; a date that tells when it happened reads as « il y a ». */
function Due({ item }) {
  const { t } = useTranslation()
  const at = Date.parse(item.due_at)
  if (!Number.isFinite(at) || UNDATED_KINDS.includes(item.kind)) return <QueueDue label="–" date="" tone="" />
  const since = SINCE_KINDS.includes(item.kind)
  const tone = since ? '' : dueTone(item.due_at)
  const share = since ? null : countdownShare(at)
  return (
    <QueueDue due={item.due_at} tone={tone}
      label={since ? compactAgo(item.due_at, t) : compactDue(item.due_at, t)} date={formatDate(item.due_at, { time: true })}>
      {share !== null && (
        <span className="countdown" data-tone={tone || 'neutral'} role="img"
          aria-label={t('overview.queue.countdown', { count: Math.ceil((at - Date.now()) / DAY_MS) })}>
          <i style={{ width: `${Math.max(3, Math.round(share * 100))}%` }} />
        </span>
      )}
    </QueueDue>
  )
}

function Row({ item, actions, hidden }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const to = item.href_hint || null
  const group = GROUP_OF[item.kind]
  const critical = item.tier === 'critical'
  const kind = t(`overview.kind.${item.kind}`, { defaultValue: item.kind })
  const name = item.label || kind
  const action = actions.actionOf(item)
  const key = `${item.kind}-${item.id}`
  const cause = t(`overview.cause.${item.kind}`, { defaultValue: '' })
  const open = REVIEW_KINDS.includes(item.kind)
    ? { icon: 'approve', label: t('overview.queue.review') }
    : item.kind === 'ca_expiring' ? { icon: 'shield', label: t('overview.queue.viewCa') } : { icon: 'right', label: t('overview.queue.open') }
  return (
    <li className="queue-row" data-row={key} data-type={TYPE_OF[group] || group} data-kind={item.kind} data-tier={item.tier}
      data-due={Date.parse(item.due_at) || undefined} hidden={hidden}>
      <span className="queue-icon" aria-hidden="true"><Icon name={critical ? 'warning' : (GROUP_ICON[group] || 'clock')} /></span>
      <div className="queue-main">
        <p className="queue-head">
          {/* With an operation, the name keeps the way to the object; otherwise the action is that way */}
          {action && to
            ? <button type="button" className="text-link queue-subject" data-open={key} onClick={() => navigate(to)}>{name}</button>
            : <strong>{name}</strong>}
          {critical && <span className="sr-only">{t('overview.queue.critical')}</span>}
          <span className="queue-kind">{kind}</span>
        </p>
        {cause && <p className="queue-detail" title={cause}><span className="queue-cause">{cause}</span></p>}
      </div>
      <Due item={item} />
      <div className="queue-action">
        {action ? (
          <button type="button" className="btn" disabled={actions.busy !== null} onClick={action.run} data-write=""
            aria-label={`${action.label} ${name}`} aria-busy={actions.busy === key}>
            <Icon name={action.icon} />{action.label}
          </button>
        ) : item.kind === 'ca_expiring' && to ? (
          <Link to={to} className="btn" data-ca-link={item.id} aria-label={`${open.label} ${name}`}><Icon name={open.icon} />{open.label}</Link>
        ) : to && (
          <button type="button" className="btn" data-open={key} aria-label={`${open.label} ${name}`} onClick={() => navigate(to)}>
            <Icon name={open.icon} />{open.label}
          </button>
        )}
      </div>
    </li>
  )
}

export function QueueCard({ defaultOpen = false, onToggle }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const state = useCardData(() => overviewService.getQueue(), ['certificate', 'ca', 'truststore'], 'queue')
  const actions = useRowActions(state.refresh)
  const [open, setOpen] = useState(defaultOpen)
  const [watchOpen, setWatchOpen] = useState(false)
  const [group, setGroup] = useState('')
  // The saved preference may arrive after mounting: it wins over the initial state
  useEffect(() => { setOpen(defaultOpen) }, [defaultOpen])
  // A figure or another card asks for one type: kept by the page until this card is mounted and loaded
  const page = useContext(OverviewContext)
  const [ask, setAsk] = useState(null)
  useEffect(() => {
    const take = (e) => setAsk((prev) => page?.takeQueueAsk?.() || (e ? { group: e.detail?.group || '' } : prev))
    take()
    window.addEventListener('ucm:overview-queue', take)
    return () => window.removeEventListener('ucm:overview-queue', take)
  }, [page])
  const loading = state.status === 'loading'
  useEffect(() => {
    if (!ask) return
    setGroup(ask.group)
    if (loading) return
    setAsk(null)
    requestAnimationFrame(() => {
      document.getElementById('card-queue')?.scrollIntoView?.({ block: 'start' })
      document.getElementById('card-queue-title')?.focus({ preventScroll: true })
    })
  }, [ask, loading])

  const data = state.data || {}
  const items = Array.isArray(data.items) ? data.items : []
  const counts = data.counts && typeof data.counts === 'object' ? data.counts : {}
  const groupTotal = (g) => QUEUE_GROUPS[g].reduce((sum, k) => sum + (Number(counts[k]) || 0), 0)
  const groups = Object.keys(QUEUE_GROUPS).filter((g) => groupTotal(g) > 0)
  const active = groups.includes(group) ? group : ''
  const shown = active ? items.filter((i) => GROUP_OF[i.kind] === active) : items
  const act = shown.filter((i) => !isWatch(i))
  const watch = shown.filter(isWatch)
  const capped = act.length > VISIBLE && !open
  // A chip that keeps only rows to watch unfolds them: folded, it would show nothing
  const forced = Boolean(active) && act.length === 0
  const watchShown = forced || watchOpen
  const expected = active ? groupTotal(active) : (typeof data.total === 'number' ? data.total : shown.length)
  const renewals = Number(counts.manual_renewal_due) || 0
  const renewalsHref = listHref(data.filter_hints?.manual_renewal_due)
  const groupName = (g) => t(`overview.queue.group.${g}`)

  const toggle = () => { setOpen(!open); onToggle?.(!open) }
  const chip = (id, label, n) => (
    <button key={id || 'all'} type="button" className="queue-chip" id={`queue-chip-${id || 'all'}`} data-queue-type={id}
      aria-pressed={active === id} onClick={() => setGroup(id)}>
      {label}<span className="counter">{num(n)}</span>
    </button>
  )
  const more = act.length > VISIBLE && (
    <div className="queue-more">
      <button type="button" className="btn queue-more-btn" id="queue-more" aria-expanded={!capped} aria-controls="queue-list" onClick={toggle}>
        <Icon name={capped ? 'down' : 'up'} />
        {capped ? t('overview.queue.unfold', { count: act.length - VISIBLE }) : t('overview.queue.less')}
      </button>
    </div>
  )
  const watchGroup = watch.length > 0 && (
    <>
      <div className="queue-group" id="queue-watch-group">
        <span className="queue-icon" aria-hidden="true"><Icon name="clock" /></span>
        <p className="queue-group-text" id="queue-watch-label">
          <strong>{t('overview.queue.watch', { count: watch.length })}</strong>
          <span className="queue-group-note">{t('overview.queue.watchNote')}</span>
        </p>
        {!forced && (
          <button type="button" className="btn queue-watch-btn" id="queue-watch-toggle" aria-expanded={watchShown} aria-controls="queue-watch"
            aria-label={t(watchShown ? 'overview.queue.watchHide' : 'overview.queue.watchShow', { count: watch.length })}
            onClick={() => setWatchOpen(!watchOpen)}>
            <Icon name={watchShown ? 'up' : 'down'} />{watchShown ? t('overview.queue.hide') : t('overview.queue.show')}
          </button>
        )}
      </div>
      <ol className="queue-list queue-watch" id="queue-watch" aria-labelledby="queue-watch-label" hidden={!watchShown}>
        {watch.map((item) => <Row key={`${item.kind}-${item.id}`} item={item} actions={actions} />)}
      </ol>
    </>
  )
  const empty = state.status === 'ready' && shown.length === 0 && (
    <CardEmpty id="queue-empty" title={t('overview.queue.emptyTitle')}
      text={active ? t('overview.queue.emptyType', { name: groupName(active) }) : t('overview.queue.emptyHint')}>
      {active && <button type="button" className="btn" data-queue-type="" onClick={() => setGroup('')}>{t('overview.queue.seeAll')}</button>}
    </CardEmpty>
  )

  return (
    <OverviewCard id="queue" state={state} route="GET /api/v2/dashboard/queue" count={num(data.total)}
      sub={active
        ? t('overview.queue.subFiltered', { shown: shown.length, total: num(data.total), name: groupName(active) })
        : t('overview.queue.sub')}
      tools={renewals > 0 && renewalsHref && (
        <button type="button" className="text-link" data-dashboard-link="renewal" onClick={() => navigate(renewalsHref)}>
          {t('overview.queue.toRenew', { count: renewals })} <Icon name="right" />
        </button>
      )}>
      {groups.length > 0 && (
        <div className="queue-filters" role="group" aria-label={t('overview.queue.filterLabel')}>
          {chip('', t('overview.queue.group.all'), data.total)}
          {groups.map((g) => chip(g, groupName(g), groupTotal(g)))}
        </div>
      )}
      {empty || (
        <>
          {act.length > 0 && (
            <ol className="queue-list" id="queue-list" aria-label={t('overview.queue.listLabel')}>
              {act.map((item, n) => <Row key={`${item.kind}-${item.id}`} item={item} actions={actions} hidden={capped && n >= VISIBLE} />)}
            </ol>
          )}
          {act.length === 0 && !active && <p className="queue-none"><Icon name="check" />{t('overview.queue.none')}</p>}
          {more}
          {watchGroup}
        </>
      )}
      {shown.length < expected && (
        <p className="queue-none" data-partial="">{t('overview.queue.partial', { shown: shown.length, total: expected })}</p>
      )}
    </OverviewCard>
  )
}
