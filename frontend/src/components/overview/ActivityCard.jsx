/**
 * Latest operations over GET /dashboard/activity: a compact timeline grouped by day, each entry with
 * the icon of its family, its operation, its object, who did it and when. Successive sign-ins of one
 * user fold into one line (« 5 sign-ins by admin, 18:37 to 18:53 ») so that they do not hide the PKI.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Icon, TextLink } from '../atelier'
import { dashboardService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { actionLabel, typeIcon, typeOf } from '../../pages/activity/activityTypes'
import { actionDetail } from '../../pages/activity/actionDetails'
import { eventClock, eventDate, fullTime } from '../../pages/activity/activityDates'
import { foldActivity } from '../../lib/overviewViz'
import { OverviewCard, useCardData, useLang } from './shared'

// Read enough entries for the folded sign-ins to leave room for the operations (the route gives 100 at most)
export const ACTIVITY_READ = 50
export const ACTIVITY_SHOWN = 6

// The card's filters: PKI operations, sign-ins and accounts, or everything (settings and system included)
const ACCESS = ['auth', 'users']
const NOT_PKI = [...ACCESS, 'settings', 'backups', 'system']
const ACTIVITY_FILTERS = {
  all: () => true,
  pki: (a) => !NOT_PKI.includes(typeOf(a?.action)),
  access: (a) => ACCESS.includes(typeOf(a?.action)),
}

const failedOf = (a) => /fail|denied|error/i.test(String(a?.action || '')) || a?.success === false

/** The day heading of an entry: today, yesterday, or its date. */
function dayHeading(ts, lang, t) {
  const day = eventDate(ts, lang)
  if (!day) return '–'
  if (day === eventDate(new Date(), lang)) return t('overview.activity.today')
  if (day === eventDate(new Date(Date.now() - 86400000), lang)) return t('overview.activity.yesterday')
  return day
}

export function ActivityCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const navigate = useNavigate()
  const { hasPermission } = usePermission()
  const state = useCardData(() => dashboardService.getActivityLog(ACTIVITY_READ), ['certificate', 'ca', 'user', 'group'])
  const rows = Array.isArray(state.data?.activity) ? state.data.activity : []
  const audit = hasPermission('read:audit')
  const [filter, setFilter] = useState('all')
  const kept = rows.filter(ACTIVITY_FILTERS[filter])
  const items = foldActivity(kept).slice(0, ACTIVITY_SHOWN)
  const days = []
  for (const item of items) {
    const ts = item.folded ? item.last : item.entry.timestamp
    const label = dayHeading(ts, lang, t)
    if (days.at(-1)?.label !== label) days.push({ label, items: [] })
    days.at(-1).items.push(item)
  }
  const journal = (action) => navigate(`/audit?search=${encodeURIComponent(action || '')}`)

  const row = (item, i) => {
    if (item.folded) {
      const text = t('overview.activity.folded', { count: item.count, user: item.user })
      return (
        <li key={`fold-${item.last}-${i}`} className="activity-row tl-row" data-family="auth" data-folded={item.count}>
          <Icon name={typeIcon('auth')} />
          <div>
            {audit ? <button type="button" data-event={item.action} onClick={() => journal(item.action)}>{text}</button> : <strong>{text}</strong>}
          </div>
          <time dateTime={item.last} title={`${fullTime(item.first, lang)} – ${fullTime(item.last, lang)}`}>
            {t('overview.activity.span', { from: eventClock(item.first, lang), to: eventClock(item.last, lang) })}
          </time>
        </li>
      )
    }
    const a = item.entry
    const failed = failedOf(a)
    const operation = actionLabel(a.action, t)
    return (
      <li key={`${a.timestamp}-${i}`} className="activity-row tl-row" data-tone={failed ? 'bad' : undefined} data-family={typeOf(a.action)}>
        <Icon name={failed ? 'warning' : typeIcon(typeOf(a.action))} />
        <div>
          <strong>{operation || actionDetail(a.message, t)}</strong>
          {/* The journal, searched for this operation: the event itself needs its id (not in this feed) */}
          {!operation ? null : audit
            ? <button type="button" data-event={a.action} onClick={() => journal(a.action)}>{actionDetail(a.message, t)}</button>
            : <span className="tl-object">{actionDetail(a.message, t)}</span>}
          <span className="muted small">{a.user}</span>
        </div>
        {a.timestamp
          ? <time dateTime={a.timestamp} title={fullTime(a.timestamp, lang)}>{eventClock(a.timestamp, lang)}</time>
          : <span className="muted">–</span>}
      </li>
    )
  }

  return (
    <OverviewCard id="activity" state={state} route="GET /api/v2/dashboard/activity"
      empty={state.status === 'ready' && rows.length === 0}
      sub={t(audit ? 'overview.activity.sub' : 'overview.activity.subOwn')}
      tools={(
        <>
          <div className="segmented" role="group" aria-label={t('overview.activity.filterLabel')}>
            {Object.keys(ACTIVITY_FILTERS).map((f) => (
              <button key={f} type="button" id={`activity-${f}`} data-activity-filter={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {t(`overview.activity.filter.${f}`)}
              </button>
            ))}
          </div>
          {audit && <TextLink to="/audit" icon="right" data-nav="activity">{t('overview.activity.all')}</TextLink>}
        </>
      )}>
      <div className="panel-content">
        {items.length === 0 && (
          <p className="empty-line" role="status"><Icon name="check" /><span>{t('overview.activity.noneOfKind', { name: t(`overview.activity.filter.${filter}`) })}</span></p>
        )}
        <ol className="timeline">
          {days.map((d) => (
            <li key={d.label} className="tl-day">
              <h3>{d.label}</h3>
              <ol>{d.items.map(row)}</ol>
            </li>
          ))}
        </ol>
      </div>
    </OverviewCard>
  )
}
