import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Pill, Notice, DataTable, SkeletonPanel, Dock, DockBody, Section, Facts, useClientList, useSortParam, useDockParam } from '../../components/atelier'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { cardFacts, labelledFact } from '../../components/atelier/cardFacts'
import { SlotDock } from '../protocols/dockSlot'
import { useNotification } from '../../contexts'
import { systemService } from '../../services'
import { useRefocusAfter } from '../../hooks/useRefocus'
import { compactRun } from '../../lib/relativeTime'
import { formatDate } from '../../lib/utils'

const POLL_MS = 15000
// The tasks by name (T4), the sort kept in the address under this list's own scope (the settings stack their sections)
const BY_TASK = { key: 'task', asc: true }
const SORT_KEYS = ['task', 'note', 'status', 'schedule', 'last', 'next', 'duration', 'runs']
const STATE_RANK = ['warning', 'skipped', 'ok']
const time = (iso) => (iso ? Date.parse(iso) : null)

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
  // The task open in the inspector lives in the address (`item`), as in every module list (E4)
  const taskDock = useDockParam()

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

  // A task's state as [tone, text, icon], drawn as a pill in its row and in the inspector
  const stateFact = (task) => (task.last_error || task.last_status === 'warning' ? ['warn', t('scheduler.statusWarning')]
    : task.last_status === 'skipped' ? ['muted', t('scheduler.statusSkipped'), 'clock'] : ['good', t('scheduler.statusOk')])
  const status = (task) => { const [tone, label, icon] = stateFact(task); return <Pill tone={tone} label={label} icon={icon} /> }
  // What the last run said: its error, its warning, or why it stood down
  const note = (task) => (task.last_error ? <span className="mono">{task.last_error}</span>
    : task.last_status === 'warning' && task.last_reason ? task.last_reason
      : task.last_status === 'skipped' ? t('scheduler.skipped', { reason: skipReason(t, task.last_reason) }) : null)
  const run = (task) => (
    <RunButton busy={!!running[task.name]} onRun={() => handleRun(task.name, taskLabel(t, task))}>{t('scheduler.runNow')}</RunButton>
  )
  const stateOf = (task) => (task.last_error || task.last_status === 'warning' ? 'warning' : task.last_status === 'skipped' ? 'skipped' : 'ok')
  const noteText = (task) => task.last_error || (task.last_status === 'warning' ? task.last_reason : null)
    || (task.last_status === 'skipped' ? t('scheduler.skipped', { reason: skipReason(t, task.last_reason) }) : null)
  const sortParam = useSortParam(BY_TASK, SORT_KEYS, { scope: 'tasks' })
  const list = useClientList(tasks, {
    sortParam,
    sizes: [1000],
    sorts: {
      task: (task) => taskLabel(t, task), note: noteText, status: (task) => STATE_RANK.indexOf(stateOf(task)),
      schedule: (task) => task.interval || null, last: (task) => time(task.last_run), next: (task) => time(task.next_run),
      duration: (task) => task.last_duration_ms ?? null, runs: (task) => task.run_count ?? null,
    },
  })
  // The task names the row and opens it in the inspector; what its last run said is the free text that takes the room left
  const columns = [
    { id: 'task', label: t('scheduler.colTask'), kind: 'entity', priority: 1, sort: 'task', cell: (task) => taskLabel(t, task) },
    { id: 'note', label: t('scheduler.colNote'), kind: 'text', priority: 4, grow: true, tone: 'muted', sort: 'note', cell: (task) => note(task) || '—',
      title: (task) => noteText(task) || undefined },
    { id: 'status', label: t('atelier.state'), kind: 'fit', priority: 1, sort: 'status', cell: status },
    { id: 'schedule', label: t('scheduler.colSchedule'), kind: 'fit', priority: 4, sort: 'schedule', tone: 'muted', cell: (task) => humanizeInterval(task.interval, t) },
    { id: 'last', label: t('scheduler.colLastRun'), kind: 'fit', priority: 3, labelled: true, sort: 'last', tone: 'muted', cell: (task) => compactRun(task.last_run, t) || '—' },
    { id: 'next', label: t('scheduler.colNextRun'), kind: 'fit', priority: 2, labelled: true, sort: 'next', tone: 'muted', cell: (task) => compactRun(task.next_run, t) || '—' },
    { id: 'duration', label: t('scheduler.colDuration'), kind: 'number', priority: 4, sort: 'duration', tone: 'muted', cell: (task) => fmtDuration(task.last_duration_ms, i18n?.language) },
    { id: 'runs', label: t('scheduler.colRuns'), kind: 'number', priority: 4, sort: 'runs', tone: 'muted', cell: (task) => task.run_count },
    ...(canRun ? [{ id: 'run', label: <span className="sr-only">{t('common.actions')}</span>, kind: 'fit', priority: 1, cell: run }] : []),
  ]
  const opened = taskDock.item ? tasks.find((task) => task.name === taskDock.item) : null
  // A run's moment: when, then how long ago or how soon; none is an absence, in grey
  const moment = (label, iso) => (iso
    ? [label, <>{formatDate(iso, { time: true })} <span className="muted">({compactRun(iso, t)})</span></>]
    : { label, absent: '—' })
  // Every column of the list and the task's action, the columns folded for want of room included (E4)
  const dock = opened && (
    <Dock label={t('atelier.detailOf', { name: t('scheduler.tasksTitle') })} tabsLabel={t('atelier.openItem')} activeKey={opened.name}
      tabs={[{ key: opened.name, title: taskLabel(t, opened), icon: 'clock' }]} onClose={() => taskDock.close()}>
      <DockBody icon="clock" title={taskLabel(t, opened)} badge={status(opened)} section="overview" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: taskLabel(t, opened) })} sections={[['overview', t('atelier.overview')]]}
        actions={canRun && run(opened)}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Facts items={[
              { label: t('atelier.state'), state: stateFact(opened) },
              note(opened) ? { label: t('scheduler.colNote'), value: note(opened), long: true } : { label: t('scheduler.colNote'), absent: '—' },
              [t('scheduler.colSchedule'), humanizeInterval(opened.interval, t)],
              moment(t('scheduler.colLastRun'), opened.last_run),
              moment(t('scheduler.colNextRun'), opened.next_run),
              opened.last_duration_ms == null ? { label: t('scheduler.colDuration'), absent: '—' } : [t('scheduler.colDuration'), fmtDuration(opened.last_duration_ms, i18n?.language)],
              opened.run_count == null ? { label: t('scheduler.colRuns'), absent: '—' } : [t('scheduler.colRuns'), opened.run_count],
            ]} />
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

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
            columns={columns} rows={list.rows} rowKey={(task) => task.name} rowLabel={(task) => taskLabel(t, task)} sort={list.sort} onSort={list.onSort}
            onOpen={(task) => taskDock.open(task.name)} openedId={opened?.name}
            empty={<div className="empty"><p>{t('scheduler.noTasks')}</p></div>}
            // The record names its facts as every list does; the inspector holds the others
            card={(task) => ({
              description: note(task),
              meta: [...cardFacts(columns, task), labelledFact(t('scheduler.colSchedule'), humanizeInterval(task.interval, t))],
              status: status(task),
              end: canRun ? run(task) : undefined,
            })} />
        )}
      </SettingsGroup>
      <SlotDock>{dock}</SlotDock>
    </>
  )
}
