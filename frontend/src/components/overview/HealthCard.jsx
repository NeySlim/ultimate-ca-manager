import { useTranslation } from 'react-i18next'
import { overviewService } from '../../services'
import { formatDate } from '../../lib/utils'
import { CardFrame, num, useCardData } from './shared'

const PROTOCOLS = ['acme', 'scep', 'est', 'scheduler']

function Bars({ periods }) {
  const peak = Math.max(1, ...periods.map((p) => (Number(p.ok) || 0) + (Number(p.failed) || 0)))
  return (
    <span className="flex items-end gap-0.5 h-5" aria-hidden="true">
      {periods.map((p) => (
        <span key={p.date} title={`${p.date}: ${p.ok} / ${p.failed}`}
          className={`w-1.5 rounded-sm ${p.failed > 0 ? 'bg-status-danger' : 'bg-status-success'}`}
          style={{ height: `${Math.max(8, (((Number(p.ok) || 0) + (Number(p.failed) || 0)) / peak) * 100)}%` }} />
      ))}
    </span>
  )
}

export function HealthCard() {
  const { t } = useTranslation()
  const state = useCardData(() => overviewService.getHealth())
  const protocols = state.data?.protocols || {}
  const present = PROTOCOLS.filter((p) => protocols[p])

  return (
    <CardFrame id="health" title={t('overview.cards.health')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && present.length === 0}>
      <ul className="flex flex-col gap-2">
        {present.map((name) => {
          const p = protocols[name]
          return (
            <li key={name} className="flex items-center justify-between gap-3">
              <span className="text-sm text-text-primary">{t(`overview.health.${name}`)}</span>
              <span className="flex items-center gap-3 text-xs text-text-secondary">
                {Array.isArray(p.periods) && <Bars periods={p.periods} />}
                {name === 'scheduler' && <span>{t('overview.health.tasks')} {num(p.tasks)}</span>}
                <span>{p.last_status ?? '–'}</span>
                <span>{p.last_operation_at ? formatDate(p.last_operation_at) : '–'}</span>
              </span>
            </li>
          )
        })}
      </ul>
    </CardFrame>
  )
}
