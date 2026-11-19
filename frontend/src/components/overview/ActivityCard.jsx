import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  ArrowsClockwise, CaretRight, ClockCounterClockwise, DownloadSimple, PencilSimple, PlusCircle, Prohibit,
  SignIn, SignOut, Trash, UploadSimple, WarningCircle,
} from '@phosphor-icons/react'
import { dashboardService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { ConnectionState, useWebSocket } from '../../hooks/useWebSocket'
import { relativeTime } from '../../lib/overviewTime'
import { formatDate } from '../../lib/utils'
import { CardFrame, useCardData, useLang } from './shared'

const LATEST = 6
// First match wins: the audit action names carry their verb
const ICONS = [
  [/fail|denied|error/, WarningCircle], [/logout/, SignOut], [/login/, SignIn], [/revoke/, Prohibit],
  [/delete|remove/, Trash], [/renew|regenerat|rotate/, ArrowsClockwise], [/export|download/, DownloadSimple],
  [/import|upload/, UploadSimple], [/create|issue|sign|add/, PlusCircle], [/update|edit|change|set/, PencilSimple],
]

function activityIcon(action) {
  const name = String(action || '').toLowerCase()
  return (ICONS.find(([re]) => re.test(name)) || [null, ClockCounterClockwise])[1]
}

export function ActivityCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const { hasPermission } = usePermission()
  const { connectionState } = useWebSocket()
  const state = useCardData(() => dashboardService.getActivityLog(LATEST), ['certificate', 'ca', 'user', 'group'])
  const rows = Array.isArray(state.data?.activity) ? state.data.activity : []
  const audit = hasPermission('read:audit')

  return (
    <CardFrame id="activity" title={t('overview.cards.activity')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && rows.length === 0}
      sub={t(audit ? 'overview.activity.sub' : 'overview.activity.subOwn')}
      tools={(
        <>
          {connectionState === ConnectionState.CONNECTED && (
            <span className="ov-live" data-testid="activity-live"><i aria-hidden="true" />{t('common.live')}</span>
          )}
          {audit && <Link to="/audit" className="ov-link">{t('overview.activity.all')}<CaretRight size={13} aria-hidden="true" /></Link>}
        </>
      )}>
      <ul className="ov-body ov-activity">
        {rows.slice(0, LATEST).map((a, i) => {
          const Icon = activityIcon(a.action)
          return (
            <li key={`${a.timestamp}-${i}`} data-tone={Icon === WarningCircle ? 'bad' : undefined}>
              <Icon size={15} aria-hidden="true" />
              <div className="ov-activity-text">
                <strong>{a.message}</strong>
                <span className="ov-muted">{a.user}</span>
              </div>
              {a.timestamp
                ? <time dateTime={a.timestamp} title={formatDate(a.timestamp)}>{relativeTime(a.timestamp, lang) || formatDate(a.timestamp)}</time>
                : <span className="ov-muted">–</span>}
            </li>
          )
        })}
      </ul>
    </CardFrame>
  )
}
