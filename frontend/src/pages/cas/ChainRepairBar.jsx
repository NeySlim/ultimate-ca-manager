/**
 * CAs Page — chain repair notification/action bar (sits under stats)
 */
import { useState, useEffect } from 'react'
import { LinkSimple, ArrowClockwise, CircleNotch, Timer } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'

export function ChainRepairBar({ data, running, onRun, canRunRepair, t }) {
  const task = data?.task || {}
  const crStats = data?.stats || {}
  const [countdown, setCountdown] = useState('')

  useEffect(() => {
    if (!task.next_run) return
    const update = () => {
      const diff = Math.max(0, Math.floor((new Date(task.next_run).getTime() - Date.now()) / 1000))
      const m = Math.floor(diff / 60)
      const s = diff % 60
      setCountdown(`${m}:${String(s).padStart(2, '0')}`)
    }
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [task.next_run])

  const total = crStats.total_cas || 0
  const orphans = crStats.orphan_cas || 0
  const linked = total - orphans
  const pct = total > 0 ? Math.round((linked / total) * 100) : 100

  if (!data) return null

  return (
    <div className="flex items-center gap-3 px-4 py-1.5 border-b border-border-op30 bg-secondary-op30">
      <div className="flex items-center gap-1.5 text-text-tertiary shrink-0">
        <LinkSimple size={13} weight="duotone" />
        <span className="text-[11px] font-medium">{t('dashboard.chainRepair')}</span>
      </div>

      <div className="flex items-center gap-2 flex-1 max-w-xs">
        <div className="flex-1 h-1.5 rounded-full bg-tertiary-op80 overflow-hidden">
          <div 
            className={`h-full rounded-full transition-all duration-700 ${pct === 100 ? 'bg-accent-success' : 'bg-accent-warning'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-[10px] font-bold font-mono text-text-secondary w-8 text-right">{pct}%</span>
      </div>

      <div className="hidden sm:flex items-center gap-3 text-[10px] text-text-tertiary">
        <span>{crStats.total_cas || 0} CA{(crStats.total_cas || 0) > 1 ? 's' : ''}</span>
        <span>{crStats.total_certs || 0} certs</span>
        {orphans > 0 && <span className="text-accent-warning">{orphans} {t('dashboard.chainRepairOrphans')}</span>}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {running ? (
          <span className="text-[10px] text-accent-primary flex items-center gap-1">
            <CircleNotch size={10} className="animate-spin" />
          </span>
        ) : countdown ? (
          <span className="text-[10px] text-text-tertiary font-mono flex items-center gap-1">
            <Timer size={10} />
            {countdown}
          </span>
        ) : null}
        {canRunRepair && (
        <button
          onClick={onRun}
          disabled={running}
          className="p-1 rounded hover:bg-tertiary-op80 text-text-tertiary hover:text-accent-primary transition-all disabled:opacity-50"
          title={t('dashboard.chainRepairRun')}
        >
          {running 
            ? <CircleNotch size={12} className="animate-spin" />
            : <ArrowClockwise size={12} />
          }
        </button>
        )}
      </div>
    </div>
  )
}
