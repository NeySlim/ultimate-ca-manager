import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Pill, Notice, DataTable, SkeletonPanel } from '../../components/atelier'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { useNotification } from '../../contexts'
import { systemService } from '../../services'
import { useRefocusAfter } from '../../hooks/useRefocus'
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
// Reasons some tasks give as English sentences rather than codes
const REASON_CODES = {
  'not configured or disabled': 'notConfigured',
  'bind credentials missing': 'bindMissing',
  'another operation in progress': 'busy',
  'claimed by another node': 'otherNode',
  'another node is running the expiry checks': 'otherNode',
}

// Disabled while its task runs, it gets the focus back when the run ends, as the mockup's test
function RunButton({ busy, onRun, children }) {
  const ref = useRef(null)
  useRefocusAfter(busy, ref)
  return (
    <Btn ref={ref} icon="refresh" write onClick={onRun} disabled={busy}>{children}</Btn>
  )
}

function skipReason(t, reason) {
  if (!reason) return t('scheduler.skipReasons.unknown')
  const key = `scheduler.skipReasons.${REASON_CODES[reason] || reason}`
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

  const status = (task) => (task.last_error || task.last_status === 'warning'
    ? <Pill tone="warn" label={t('scheduler.statusWarning')} />
    : task.last_status === 'skipped' ? <Pill tone="muted" icon="clock" label={t('scheduler.statusSkipped')} />
      : <Pill tone="good" label={t('scheduler.statusOk')} />)
  // What the last run said: its error, its warning, or why it stood down
  const note = (task) => (task.last_error ? <span className="mono">{task.last_error}</span>
    : task.last_status === 'warning' && task.last_reason ? task.last_reason
      : task.last_status === 'skipped' ? t('scheduler.skipped', { reason: skipReason(t, task.last_reason) }) : null)
  const run = (task) => (
    <RunButton busy={!!running[task.name]} onRun={() => handleRun(task.name, taskLabel(t, task))}>{t('scheduler.runNow')}</RunButton>
  )
  const columns = [
    { id: 'task', label: t('scheduler.colTask'), grow: true, cell: (task) => (
      <span className="task-cell"><strong>{taskLabel(t, task)}</strong>{note(task) && <span className="rl-meta">{note(task)}</span>}</span>
    ) },
    { id: 'status', label: t('atelier.state'), fit: true, cell: status },
    { id: 'schedule', label: t('scheduler.colSchedule'), fit: true, tone: 'muted', cell: (task) => humanizeInterval(task.interval, t) },
    { id: 'last', label: t('scheduler.colLastRun'), fit: true, tone: 'muted', cell: (task) => compactRun(task.last_run, t) || '—' },
    { id: 'next', label: t('scheduler.colNextRun'), fit: true, tone: 'muted', cell: (task) => compactRun(task.next_run, t) || '—' },
    { id: 'duration', label: t('scheduler.colDuration'), fit: true, tone: 'muted', cell: (task) => fmtDuration(task.last_duration_ms, i18n?.language) },
    { id: 'runs', label: t('scheduler.colRuns'), fit: true, tone: 'muted', cell: (task) => task.run_count },
    ...(canRun ? [{ id: 'run', label: <span className="sr-only">{t('common.actions')}</span>, fit: true, cell: run }] : []),
  ]
  const labelled = (key, value) => `${t(key)}${t('work.sep')}${value}`

  return (
    <>
      {meta.stale && <Notice tone="warn">{t('scheduler.stateStale')}</Notice>}
      <SettingsGroup grid={false} legend={(
        <>{t('scheduler.tasksTitle')}{meta.warnings > 0 && <>{' '}<Pill tone="warn" label={t('scheduler.warningsCount', { count: meta.warnings })} /></>}</>
      )}>
        <div className="settings-actions">
          <Btn icon="refresh" onClick={() => load()}>{t('common.refresh')}</Btn>
        </div>
        {loading ? (
          <SkeletonPanel label={t('common.loading')} />
        ) : (
          <DataTable kind="module" scrollId="scheduler-scroll" recordsId="scheduler-records" label={t('scheduler.tasksTitle')}
            columns={columns} rows={tasks} rowKey={(task) => task.name} rowLabel={(task) => taskLabel(t, task)}
            empty={<div className="empty"><p>{t('scheduler.noTasks')}</p></div>}
            card={(task) => ({
              description: note(task),
              meta: [
                labelled('scheduler.colSchedule', humanizeInterval(task.interval, t)),
                labelled('scheduler.colLastRun', compactRun(task.last_run, t) || '—'),
                labelled('scheduler.colNextRun', compactRun(task.next_run, t) || '—'),
                labelled('scheduler.colDuration', fmtDuration(task.last_duration_ms, i18n?.language)),
                labelled('scheduler.colRuns', task.run_count),
              ],
              status: status(task),
              end: canRun ? run(task) : undefined,
            })} />
        )}
      </SettingsGroup>
    </>
  )
}
