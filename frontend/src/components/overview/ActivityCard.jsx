/**
 * The mockup's activityCard() over GET /dashboard/activity: the five latest operations, each
 * with the icon of its type, its operation, its object, who did it and when.
 */
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Icon, TextLink } from '../atelier'
import { dashboardService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { actionLabel, typeIcon, typeOf } from '../../pages/activity/activityTypes'
import { fullTime, rowTime } from '../../pages/activity/activityDates'
import { OverviewCard, useCardData, useLang } from './shared'

const LATEST = 5

export function ActivityCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const navigate = useNavigate()
  const { hasPermission } = usePermission()
  const state = useCardData(() => dashboardService.getActivityLog(LATEST), ['certificate', 'ca', 'user', 'group'])
  const rows = Array.isArray(state.data?.activity) ? state.data.activity : []
  const audit = hasPermission('read:audit')

  return (
    <OverviewCard id="activity" state={state} route="GET /api/v2/dashboard/activity"
      empty={state.status === 'ready' && rows.length === 0}
      sub={t(audit ? 'overview.activity.sub' : 'overview.activity.subOwn')}
      tools={audit && <TextLink to="/audit" icon="right" data-nav="activity">{t('overview.activity.all')}</TextLink>}>
      <div className="panel-content">
        {rows.slice(0, LATEST).map((a, i) => {
          const failed = /fail|denied|error/i.test(String(a.action || '')) || a.success === false
          const operation = actionLabel(a.action)
          return (
            <div key={`${a.timestamp}-${i}`} className="activity-row" data-tone={failed ? 'bad' : undefined}>
              <Icon name={failed ? 'warning' : typeIcon(typeOf(a.action))} />
              <div>
                <strong>{operation || a.message}</strong>
                {/* The journal, searched for this operation: the event itself needs its id (not in this feed) */}
                {!operation ? null : audit
                  ? <button type="button" data-event={a.action} onClick={() => navigate(`/audit?search=${encodeURIComponent(a.action || '')}`)}>{a.message}</button>
                  : <span>{a.message}</span>}
                <span className="muted small">{a.user}</span>
              </div>
              {a.timestamp
                ? <time dateTime={a.timestamp} title={fullTime(a.timestamp, lang)}>{rowTime(a.timestamp, lang)}</time>
                : <span className="muted">–</span>}
            </div>
          )
        })}
      </div>
    </OverviewCard>
  )
}
