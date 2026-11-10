import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { overviewService } from '../../services'
import { listHref } from '../../lib/overviewFilters'
import { formatDate } from '../../lib/utils'
import { CardFrame, num, useCardData } from './shared'

const VISIBLE = 6

export function QueueCard({ defaultOpen = false, onToggle }) {
  const { t } = useTranslation()
  const state = useCardData(() => overviewService.getQueue())
  const [open, setOpen] = useState(defaultOpen)
  // The saved preference may arrive after mounting: it wins over the initial state
  useEffect(() => { setOpen(defaultOpen) }, [defaultOpen])
  const data = state.data || {}
  const items = Array.isArray(data.items) ? data.items : []
  const counts = data.counts && typeof data.counts === 'object' ? data.counts : {}
  const folded = Object.entries(counts).filter(([, n]) => n > 0)
  const shown = open ? items : items.slice(0, VISIBLE)

  const toggle = () => { setOpen(!open); onToggle?.(!open) }

  return (
    <CardFrame id="queue" title={t('overview.cards.queue')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && items.length === 0}
      action={<span className="text-sm font-semibold tabular-nums" data-testid="queue-total">{num(data.total)}</span>}>
      <ul className="flex flex-col divide-y divide-border-op30">
        {shown.map((item) => (
          <li key={`${item.kind}-${item.id}`} className="py-1.5">
            <Link to={item.href_hint || '#'} className="flex items-center justify-between gap-3">
              <span className="min-w-0">
                <span className="block text-sm text-text-primary truncate">{item.label}</span>
                <span className="block text-xs text-text-secondary">
                  {t(`overview.kind.${item.kind}`, { defaultValue: item.kind })}
                </span>
              </span>
              <span className={item.tier === 'critical' ? 'text-xs text-status-danger' : 'text-xs text-status-warning'}>
                {item.due_at ? formatDate(item.due_at) : '–'}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {folded.length > 0 && (
        <div>
          <button type="button" className="text-xs underline text-text-secondary" aria-expanded={open}
            onClick={toggle}>
            {open ? t('overview.queue.fold') : t('overview.queue.unfold')}
          </button>
          <ul className="mt-1" aria-label={t('overview.queue.perKind')}>
            {folded.map(([kind, n]) => {
              const to = listHref(data.filter_hints?.[kind])
              const row = (
                <>
                  <span>{t(`overview.kind.${kind}`, { defaultValue: kind })}</span>
                  <span className="tabular-nums">{num(n)}</span>
                </>
              )
              return (
                <li key={kind} className="text-xs text-text-secondary">
                  {to
                    ? <Link to={to} className="flex justify-between py-0.5 hover:text-accent-primary">{row}</Link>
                    : <div className="flex justify-between py-0.5">{row}</div>}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </CardFrame>
  )
}
