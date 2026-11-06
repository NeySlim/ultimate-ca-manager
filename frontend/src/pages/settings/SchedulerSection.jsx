import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Timer, Play, CheckCircle, WarningCircle, MinusCircle, ArrowsClockwise } from '@phosphor-icons/react'
import { Button, Badge, DetailHeader, DetailContent, DetailSection } from '../../components'
import { useNotification } from '../../contexts'
import { systemService } from '../../services'

const POLL_MS = 15000

function humanizeInterval(seconds) {
  if (!seconds || seconds < 1) return '—'
  if (seconds % 86400 === 0) {
    const d = seconds / 86400
    return d === 1 ? 'daily' : `every ${d} days`
  }
  if (seconds % 3600 === 0) {
    const h = seconds / 3600
    return h === 1 ? 'hourly' : `every ${h} h`
  }
  if (seconds % 60 === 0) {
    const m = seconds / 60
    return m === 1 ? 'every minute' : `every ${m} min`
  }
  return `every ${seconds} s`
}

function relativeTime(iso) {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const diff = Date.now() - then
  const future = diff < 0
  const s = Math.abs(diff) / 1000
  let txt
  if (s < 60) txt = '<1 min'
  else if (s < 3600) txt = `${Math.round(s / 60)} min`
  else if (s < 86400) txt = `${Math.round(s / 3600)} h`
  else txt = `${Math.round(s / 86400)} d`
  return future ? `in ${txt}` : `${txt} ago`
}

// A run that did nothing on purpose reads differently from a successful one:
// the backup task reports why it stood down (off, not due yet).
function skipReason(t, reason) {
  if (!reason) return t('scheduler.skipReasons.unknown')
  const key = `scheduler.skipReasons.${reason}`
  const label = t(key)
  return label === key ? reason : label
}

function fmtDuration(ms) {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1) return '<1 ms'
  if (ms < 1000) return `${ms.toFixed(1)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

export default function SchedulerSection({ hasPermission }) {
  const { t } = useTranslation()
  const { showSuccess, showInfo, showError } = useNotification()
  const [tasks, setTasks] = useState([])
  const [meta, setMeta] = useState({ total: 0, warnings: 0, stale: false })
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState({})
  const pollRef = useRef(null)
  const canRun = hasPermission ? hasPermission('admin:system') : false

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await systemService.getSchedulerTasks()
      const data = res.data || res
      setTasks(data.tasks || [])
      setMeta({ total: data.total || 0, warnings: data.warnings || 0, stale: !!data.stale })
    } catch (e) {
      if (!silent) showError(e.message || t('scheduler.loadFailed'))
    } finally {
      if (!silent) setLoading(false)
    }
  }, [showError, t])

  useEffect(() => {
    load()
    pollRef.current = setInterval(() => load(true), POLL_MS)
    return () => clearInterval(pollRef.current)
  }, [load])

  const handleRun = async (name) => {
    setRunning((r) => ({ ...r, [name]: true }))
    try {
      const res = await systemService.runSchedulerTask(name)
      // Still running in the scheduler process after the API's wait
      if ((res?.data || res)?.queued) showInfo(t('scheduler.taskQueued', { name }))
      else showSuccess(t('scheduler.taskRan', { name }))
      await load(true)
    } catch (e) {
      showError(e.message || t('scheduler.runFailed'))
    } finally {
      setRunning((r) => ({ ...r, [name]: false }))
    }
  }

  return (
    <DetailContent>
      <DetailHeader
        icon={Timer}
        title={t('scheduler.title')}
        subtitle={t('scheduler.subtitle')}
        badge={meta.warnings > 0 ? (
          <Badge variant="warning" size="sm">
            <WarningCircle size={12} weight="bold" className="mr-1" />
            {t('scheduler.warningsCount', { count: meta.warnings })}
          </Badge>
        ) : null}
        actions={[
          { label: t('common.refresh'), icon: ArrowsClockwise, onClick: () => load(), variant: 'secondary' },
        ]}
      />

      {meta.stale && (
        <p className="mb-3 flex items-center gap-1.5 text-xs text-status-warning">
          <WarningCircle size={14} className="shrink-0" />
          {t('scheduler.stateStale')}
        </p>
      )}

      <DetailSection title={t('scheduler.tasksTitle')} icon={Timer} iconClass="icon-bg-blue">
        {loading ? (
          <div className="p-6 text-center text-sm text-text-secondary">{t('common.loading')}</div>
        ) : tasks.length === 0 ? (
          <div className="p-6 text-center text-sm text-text-secondary">{t('scheduler.noTasks')}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-tertiary border-b border-white/5">
                  <th className="py-2 pr-3 font-medium">{t('scheduler.colTask')}</th>
                  <th className="py-2 px-3 font-medium">{t('scheduler.colSchedule')}</th>
                  <th className="py-2 px-3 font-medium">{t('scheduler.colLastRun')}</th>
                  <th className="py-2 px-3 font-medium">{t('scheduler.colNextRun')}</th>
                  <th className="py-2 px-3 font-medium">{t('scheduler.colDuration')}</th>
                  <th className="py-2 px-3 font-medium text-right">{t('scheduler.colRuns')}</th>
                  {canRun && <th className="py-2 pl-3" />}
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.name} className="border-b border-white/5 last:border-0">
                    <td className="py-2.5 pr-3">
                      <div className="flex items-center gap-2">
                        {task.last_error || task.last_status === 'warning' ? (
                          <WarningCircle size={16} className="text-amber-500 shrink-0" weight="fill" />
                        ) : task.last_status === 'skipped' ? (
                          <MinusCircle size={16} className="text-text-tertiary shrink-0" weight="fill" />
                        ) : (
                          <CheckCircle size={16} className="text-emerald-500 shrink-0" weight="fill" />
                        )}
                        <div>
                          <p className="font-medium text-text-primary">{task.label}</p>
                          {task.last_error && (
                            <p className="text-xs text-amber-500/90 mt-0.5 font-mono">{task.last_error}</p>
                          )}
                          {!task.last_error && task.last_status === 'warning' && task.last_reason && (
                            <p className="text-xs text-amber-500/90 mt-0.5">{task.last_reason}</p>
                          )}
                          {!task.last_error && task.last_status === 'skipped' && (
                            <p className="text-xs text-text-tertiary mt-0.5">
                              {t('scheduler.skipped', { reason: skipReason(t, task.last_reason) })}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-text-secondary">{humanizeInterval(task.interval)}</td>
                    <td className="py-2.5 px-3 text-text-secondary">{relativeTime(task.last_run)}</td>
                    <td className="py-2.5 px-3 text-text-secondary">{relativeTime(task.next_run)}</td>
                    <td className="py-2.5 px-3 text-text-secondary font-mono">{fmtDuration(task.last_duration_ms)}</td>
                    <td className="py-2.5 px-3 text-right text-text-secondary tabular-nums">{task.run_count}</td>
                    {canRun && (
                      <td className="py-2.5 pl-3 text-right">
                        <Button
                          type="button" size="sm" variant="secondary"
                          onClick={() => handleRun(task.name)}
                          disabled={!!running[task.name]}
                          className="gap-1 whitespace-nowrap"
                        >
                          <Play size={13} weight="fill" />
                          {t('scheduler.runNow')}
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DetailSection>
    </DetailContent>
  )
}
