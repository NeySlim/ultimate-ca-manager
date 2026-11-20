import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Play, CheckCircle, WarningCircle, MinusCircle, ArrowsClockwise } from '@phosphor-icons/react'
import { Button, Badge } from '../../components'
import { useNotification } from '../../contexts'
import { systemService } from '../../services'
import { FormGroup } from '../../components/sectioned'
import { compactRun } from '../../lib/relativeTime'

const POLL_MS = 15000

// The interval in words: whole days, hours or minutes when it divides, else seconds
function humanizeInterval(seconds, t) {
  if (!seconds || seconds < 1) return '—'
  if (seconds % 86400 === 0) {
    const d = seconds / 86400
    return d === 1 ? t('scheduler.interval.daily') : t('scheduler.interval.everyDays', { count: d })
  }
  if (seconds % 3600 === 0) {
    const h = seconds / 3600
    return h === 1 ? t('scheduler.interval.hourly') : t('scheduler.interval.everyHours', { count: h })
  }
  if (seconds % 60 === 0) {
    const m = seconds / 60
    return m === 1 ? t('scheduler.interval.everyMinute') : t('scheduler.interval.everyMinutes', { count: m })
  }
  return t('scheduler.interval.everySeconds', { count: seconds })
}

// The task's name in the interface language; one the interface does not know keeps the server's label
function taskLabel(t, task) {
  const key = `scheduler.tasks.${task.name}`
  const label = t(key)
  return label === key ? task.label : label
}

// A run that did nothing on purpose reads differently from a successful one:
// the backup task reports why it stood down (off, not due yet).
function skipReason(t, reason) {
  if (!reason) return t('scheduler.skipReasons.unknown')
  const key = `scheduler.skipReasons.${reason}`
  const label = t(key)
  return label === key ? reason : label
}

function fmtDuration(ms, lang) {
  if (ms === null || ms === undefined) return '—'
  const num = (v, digits) => new Intl.NumberFormat(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v)
  if (ms < 1) return '<1 ms'
  if (ms < 1000) return `${num(ms, 1)} ms`
  return `${num(ms / 1000, 2)} s`
}

export default function SchedulerSection({ hasPermission }) {
  const { t, i18n } = useTranslation()
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

  const handleRun = async (name, label) => {
    setRunning((r) => ({ ...r, [name]: true }))
    try {
      const res = await systemService.runSchedulerTask(name)
      // Still running in the scheduler process after the API's wait
      if ((res?.data || res)?.queued) showInfo(t('scheduler.taskQueued', { name: label }))
      else showSuccess(t('scheduler.taskRan', { name: label }))
      await load(true)
    } catch (e) {
      showError(e.message || t('scheduler.runFailed'))
    } finally {
      setRunning((r) => ({ ...r, [name]: false }))
    }
  }

  return (
    <>
      {meta.stale && (
        <p className="mb-3 flex items-center gap-1.5 text-xs text-status-warning">
          <WarningCircle size={14} className="shrink-0" />
          {t('scheduler.stateStale')}
        </p>
      )}

      <FormGroup
        title={t('scheduler.tasksTitle')}
        badge={meta.warnings > 0 ? (
          <Badge variant="warning" size="sm">
            <WarningCircle size={12} weight="bold" className="mr-1" />
            {t('scheduler.warningsCount', { count: meta.warnings })}
          </Badge>
        ) : null}
        actions={(
          <Button type="button" variant="secondary" size="sm" onClick={() => load()}>
            <ArrowsClockwise size={14} />
            {t('common.refresh')}
          </Button>
        )}
      >
        {loading ? (
          <div className="p-6 text-center text-sm text-text-secondary">{t('common.loading')}</div>
        ) : tasks.length === 0 ? (
          <div className="p-6 text-center text-sm text-text-secondary">{t('scheduler.noTasks')}</div>
        ) : (
          <div className="ui-table-box overflow-x-auto">
            <table className="ui-table">
              <thead>
                <tr>
                  <th>{t('scheduler.colTask')}</th>
                  <th>{t('scheduler.colSchedule')}</th>
                  <th>{t('scheduler.colLastRun')}</th>
                  <th>{t('scheduler.colNextRun')}</th>
                  <th>{t('scheduler.colDuration')}</th>
                  <th className="text-right">{t('scheduler.colRuns')}</th>
                  {canRun && <th />}
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.name}>
                    <td>
                      <div className="flex items-center gap-2">
                        {task.last_error || task.last_status === 'warning' ? (
                          <WarningCircle size={16} className="text-status-warning shrink-0" weight="fill" />
                        ) : task.last_status === 'skipped' ? (
                          <MinusCircle size={16} className="text-text-tertiary shrink-0" weight="fill" />
                        ) : (
                          <CheckCircle size={16} className="text-status-success shrink-0" weight="fill" />
                        )}
                        <div>
                          <p className="font-medium text-text-primary">{taskLabel(t, task)}</p>
                          {task.last_error && (
                            <p className="text-xs text-status-warning mt-0.5 font-mono">{task.last_error}</p>
                          )}
                          {!task.last_error && task.last_status === 'warning' && task.last_reason && (
                            <p className="text-xs text-status-warning mt-0.5">{task.last_reason}</p>
                          )}
                          {!task.last_error && task.last_status === 'skipped' && (
                            <p className="text-xs text-text-tertiary mt-0.5">
                              {t('scheduler.skipped', { reason: skipReason(t, task.last_reason) })}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="text-text-secondary">{humanizeInterval(task.interval, t)}</td>
                    <td className="text-text-secondary">{compactRun(task.last_run, t) || '—'}</td>
                    <td className="text-text-secondary">{compactRun(task.next_run, t) || '—'}</td>
                    <td className="text-text-secondary tabular-nums">{fmtDuration(task.last_duration_ms, i18n?.language)}</td>
                    <td className="text-right text-text-secondary tabular-nums">{task.run_count}</td>
                    {canRun && (
                      <td className="text-right">
                        <Button
                          type="button" size="sm" variant="secondary"
                          onClick={() => handleRun(task.name, taskLabel(t, task))}
                          disabled={!!running[task.name]}
                          data-write
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
      </FormGroup>
    </>
  )
}
