import { useContext, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  ArrowsClockwise, CaretDown, CaretRight, CaretUp, CheckCircle, Clock, FileX, PaperPlaneTilt, RocketLaunch,
  ShieldCheck, Stamp, Warning,
} from '@phosphor-icons/react'
import { acmeService, certificatesService, crlService, overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { listHref } from '../../lib/overviewFilters'
import { GROUP_OF, QUEUE_GROUPS, SINCE_KINDS, UNDATED_KINDS, isWatch } from '../../lib/overviewQueue'
import { askRenewal } from '../../lib/renewalPrompt'
import { relativeTime, spanText } from '../../lib/overviewTime'
import { formatDate } from '../../lib/utils'
import { CardFrame, OverviewContext, Pill, num, useCardData, useLang } from './shared'

const VISIBLE = 6
const DAY = 86400000

const GROUP_ICON = { renew: ArrowsClockwise, acme: Warning, request: Stamp, crl: FileX, ca: ShieldCheck, deploy: RocketLaunch }
const GROUP_TONE = { acme: 'warn', request: 'accent' }
const REVIEW_KINDS = ['approval_pending', 'scep_request_pending', 'key_recovery_pending']

/** The operations the API offers on a queue row, inside the page (its notifier); any other row links to its object. */
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
  const run = (item, work) => async () => {
    const key = `${item.kind}-${item.id}`
    if (busy) return
    setBusy(key)
    try {
      await work()
    } catch (error) {
      notify.showError(error?.message || t('overview.queue.actionFailed'))
    } finally {
      setBusy(null)
    }
  }
  const actionOf = (item) => {
    if (!notify) return null
    if (item.kind === 'manual_renewal_due' && hasPermission('write:certificates')) {
      return { icon: ArrowsClockwise, label: t('common.renew'), run: run(item, async () => {
        const cert = (await certificatesService.getById(item.id))?.data
        const body = await askRenewal(cert, { ...notify, t })
        if (body === null) return
        await certificatesService.renew(item.id, body)
        done(t('certificates.renewed'), 'certificate')
      }) }
    }
    if (item.kind === 'acme_client_renewal_failed' && hasPermission('write:acme')) {
      return { icon: ArrowsClockwise, label: t('overview.queue.retry'), run: run(item, async () => {
        await acmeService.renewOrder(item.id)
        done(t('overview.queue.retried'), 'certificate')
      }) }
    }
    if ((item.kind === 'crl_due' || item.kind === 'crl_missing') && hasPermission('write:crl')) {
      return { icon: PaperPlaneTilt, label: t('overview.queue.publish'), run: run(item, async () => {
        await crlService.regenerate(item.id)
        done(t('notifications.crlRegenerated', { name: item.label }), 'ca')
      }) }
    }
    return null
  }
  return { actionOf, busy }
}

function Due({ item, lang }) {
  const { t } = useTranslation()
  const at = Date.parse(item.due_at)
  if (!Number.isFinite(at) || UNDATED_KINDS.includes(item.kind)) return <div className="ov-queue-due"><span>–</span></div>
  const now = Date.now()
  const since = SINCE_KINDS.includes(item.kind)
  const late = !since && at < now
  const tone = late ? 'is-bad' : (!since && at - now < 7 * DAY ? 'is-warn' : '')
  const text = late ? t('overview.queue.overdue', { span: spanText(at, lang, now) }) : relativeTime(at, lang, now)
  const Icon = late ? Warning : Clock
  const date = formatDate(item.due_at)
  return (
    <div className={`ov-queue-due ${tone}`} title={date} data-late={late ? 'true' : 'false'}>
      <Icon size={14} aria-hidden="true" />
      <span><strong>{text}</strong><small>{date}</small></span>
    </div>
  )
}

function Row({ item, lang, actions }) {
  const { t } = useTranslation()
  const group = GROUP_OF[item.kind]
  const critical = item.tier === 'critical'
  const Icon = critical ? Warning : (GROUP_ICON[group] || Clock)
  const kind = t(`overview.kind.${item.kind}`, { defaultValue: item.kind })
  const action = actions.actionOf(item)
  const key = `${item.kind}-${item.id}`
  const openLabel = REVIEW_KINDS.includes(item.kind) ? t('overview.queue.review')
    : item.kind === 'ca_expiring' ? t('overview.queue.viewCa') : t('overview.queue.open')
  const cause = t(`overview.cause.${item.kind}`, { defaultValue: '' })
  return (
    <li className="ov-queue-row" data-testid="queue-row" data-kind={item.kind} data-tier={item.tier}>
      <span className="ov-queue-icon" aria-hidden="true"><Icon size={16} /></span>
      <div className="ov-queue-main">
        <p className="ov-queue-headline">
          <Link to={item.href_hint || '#'} className="ov-queue-subject">{item.label || kind}</Link>
          {critical && <span className="sr-only">{t('overview.queue.critical')}</span>}
          <Pill tone={critical ? 'bad' : GROUP_TONE[group]}>{kind}</Pill>
        </p>
        {cause && <p className="ov-queue-cause" title={cause}><strong>{cause}</strong></p>}
      </div>
      <Due item={item} lang={lang} />
      <div className="ov-queue-action">
        {action ? (
          <button type="button" className="ov-btn" disabled={actions.busy !== null} onClick={action.run}
            aria-label={`${action.label}: ${item.label || kind}`} aria-busy={actions.busy === key}>
            <action.icon size={14} aria-hidden="true" />{action.label}
          </button>
        ) : (
          <Link to={item.href_hint || '#'} className="ov-btn" aria-label={`${openLabel}: ${item.label || kind}`}>
            <CaretRight size={14} aria-hidden="true" />{openLabel}
          </Link>
        )}
      </div>
    </li>
  )
}

export function QueueCard({ defaultOpen = false, onToggle }) {
  const { t } = useTranslation()
  const lang = useLang()
  const state = useCardData(() => overviewService.getQueue(), ['certificate', 'ca', 'truststore'], 'queue')
  const actions = useRowActions(state.refresh)
  const [open, setOpen] = useState(defaultOpen)
  const [watchOpen, setWatchOpen] = useState(false)
  const [group, setGroup] = useState('')
  // The saved preference may arrive after mounting: it wins over the initial state
  useEffect(() => { setOpen(defaultOpen) }, [defaultOpen])
  // Another card (a failure count) asks for one group of the queue
  useEffect(() => {
    const onFilter = (e) => {
      setGroup(e.detail?.group || '')
      const card = document.getElementById('card-queue')
      card?.scrollIntoView?.({ block: 'start' })
      card?.querySelector('h2')?.focus()
    }
    window.addEventListener('ucm:overview-queue', onFilter)
    return () => window.removeEventListener('ucm:overview-queue', onFilter)
  }, [])

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
  const rows = capped ? act.slice(0, VISIBLE) : act
  // A chip that keeps only rows to watch unfolds them: folded, it would show nothing
  const forced = Boolean(active) && act.length === 0
  const watchShown = forced || watchOpen
  const expected = active ? groupTotal(active) : (typeof data.total === 'number' ? data.total : shown.length)
  const renewals = Number(counts.manual_renewal_due) || 0
  const renewalsHref = listHref(data.filter_hints?.manual_renewal_due)

  const toggle = () => { setOpen(!open); onToggle?.(!open) }
  const chip = (id, label, n) => (
    <button key={id || 'all'} type="button" className="ov-chip" aria-pressed={active === id} onClick={() => setGroup(id)}>
      {label}<span className="ov-counter">{num(n)}</span>
    </button>
  )

  return (
    <CardFrame id="queue" title={t('overview.cards.queue')} state={state} onRetry={state.reload}
      count={num(data.total)} empty={state.status === 'ready' && items.length === 0}
      emptyHint={t('overview.queue.emptyHint')}
      sub={active
        ? t('overview.queue.subFiltered', { shown: shown.length, total: num(data.total), name: t(`overview.queue.group.${active}`) })
        : t('overview.queue.sub')}
      tools={renewals > 0 && renewalsHref && (
        <Link to={renewalsHref} className="ov-link">
          {t('overview.queue.toRenew', { count: renewals })}<CaretRight size={13} aria-hidden="true" />
        </Link>
      )}>
      {groups.length > 0 && (
        <div className="ov-queue-filters" role="group" aria-label={t('overview.queue.filterLabel')}>
          {chip('', t('overview.queue.group.all'), data.total)}
          {groups.map((g) => chip(g, t(`overview.queue.group.${g}`), groupTotal(g)))}
        </div>
      )}
      {rows.length > 0 && (
        <ol className="ov-queue-list" id="overview-queue-list" aria-label={t('overview.queue.listLabel')}>
          {rows.map((item) => <Row key={`${item.kind}-${item.id}`} item={item} lang={lang} actions={actions} />)}
        </ol>
      )}
      {act.length === 0 && !active && (
        <p className="ov-queue-none"><CheckCircle size={15} aria-hidden="true" />{t('overview.queue.none')}</p>
      )}
      {act.length > VISIBLE && (
        <div className="ov-queue-more">
          <button type="button" className="ov-btn" aria-expanded={open} aria-controls="overview-queue-list" onClick={toggle}>
            {open ? <CaretUp size={14} aria-hidden="true" /> : <CaretDown size={14} aria-hidden="true" />}
            {open ? t('overview.queue.less') : t('overview.queue.unfold', { count: act.length - VISIBLE })}
          </button>
        </div>
      )}
      {watch.length > 0 && (
        <>
          <div className="ov-queue-group">
            <span className="ov-queue-icon" aria-hidden="true"><Clock size={16} /></span>
            <p id="overview-queue-watch-label">
              <strong>{t('overview.queue.watch', { count: watch.length })}</strong>
              <span className="ov-muted">{t('overview.queue.watchNote')}</span>
            </p>
            {!forced && (
              <button type="button" className="ov-btn" aria-expanded={watchShown} aria-controls="overview-queue-watch"
                aria-label={t(watchShown ? 'overview.queue.watchHide' : 'overview.queue.watchShow')}
                onClick={() => setWatchOpen(!watchOpen)}>
                {watchShown ? <CaretUp size={14} aria-hidden="true" /> : <CaretDown size={14} aria-hidden="true" />}
                {watchShown ? t('overview.queue.hide') : t('overview.queue.show')}
              </button>
            )}
          </div>
          {watchShown && (
            <ol className="ov-queue-list ov-queue-watch" id="overview-queue-watch" aria-labelledby="overview-queue-watch-label">
              {watch.map((item) => <Row key={`${item.kind}-${item.id}`} item={item} lang={lang} actions={actions} />)}
            </ol>
          )}
        </>
      )}
      {shown.length < expected && (
        <p className="ov-queue-partial">{t('overview.queue.partial', { shown: shown.length, total: expected })}</p>
      )}
    </CardFrame>
  )
}
