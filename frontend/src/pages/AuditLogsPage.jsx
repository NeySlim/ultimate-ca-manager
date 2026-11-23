/**
 * Activité: the audit journal, as the mockup's activity() draws it (page head, toolbar, summary,
 * event rows, detail dialog, empty state), on the server's entries. What the mockup has not and
 * the product keeps (filters, server pages, export formats, integrity check, clean-up, saved
 * filters) borrows the mockup's own gabarits: filter selects, applied filters, table footer, dialogs.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Zone, Icon, Btn, IconBtn, PageHead, Toolbar, SearchField, FilterSelect, ToolsDivider, AppliedFilters,
  DataTable, TableFooter, LoadError, LoadCause, NoMatch, useSortParam,
} from '../components/atelier'
import { SetupEmptyBlock } from '../components/shell/SetupEmptyBlock'
import { useNotification, useInspector } from '../contexts'
import { integrityMessage } from '../lib/auditIntegrity'
import { usePermission, usePersistedState, useJob } from '../hooks'
import { acceptedJob } from '../services/jobs.service'
import auditService from '../services/audit.service'
import { downloadBlob } from '../lib/utils'
import { reportSilentFailure } from '../lib/silentFailure'
import { TYPES, typeOf, typeIcon, presentTypes, effectiveActions, actionLabel } from './activity/activityTypes'
import { rowTime, eventDate } from './activity/activityDates'
import { EventDialog } from './activity/EventDialog'
import { ExportDialog, ActionsDialog, CleanupDialog } from './activity/JournalDialogs'
import { FiltersDialog } from './activity/FiltersDialog'

const PAGE_SIZES = [10, 25, 50, 100]
// A journal sorts by its time only, the newest first (T7), by the server, kept in the address
const NEWEST_FIRST = { key: 'timestamp', asc: false }
const TIME_KEYS = ['timestamp']
const PRESETS_KEY = 'ucm-audit-presets'
// The filters an overview link may carry in the address
const LINK_KEYS = ['type', 'action_prefix', 'success', 'date_from', 'date_to']

function readPresets() {
  try { const saved = localStorage.getItem(PRESETS_KEY); return saved ? JSON.parse(saved) : [] } catch { return [] }
}

export default function AuditLogsPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.language || 'en'
  const { showError, showSuccess, showWarning } = useNotification()
  const { openEntity } = useInspector()
  const { canDelete, canWrite, hasPermission } = usePermission()

  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [journalTotal, setJournalTotal] = useState(null)
  const [oldest, setOldest] = useState(null)
  const [stats, setStats] = useState(null)
  const [actions, setActions] = useState([])
  const [actionsRead, setActionsRead] = useState(false)

  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(50)
  const { sort, onSort } = useSortParam(NEWEST_FIRST, TIME_KEYS)
  // A new order starts from the first page, whether the header or Back set it
  const order = sort.asc ? 'asc' : 'desc'
  const [orderMark, setOrderMark] = useState(order)
  if (orderMark !== order) { setOrderMark(order); setPage(1) }

  // A link may open the journal on a search (an inspector's « View its activity »)
  const location = useLocation()
  const [search, setSearch] = useState(() => new URLSearchParams(location.search).get('search') || '')
  const [filterType, setFilterType] = usePersistedState('ucm-filter-audit-type', '')
  const [filterUsername, setFilterUsername] = usePersistedState('ucm-filter-audit-username', '')
  const [filterAction, setFilterAction] = usePersistedState('ucm-filter-audit-action', [])
  const [filterSuccess, setFilterSuccess] = usePersistedState('ucm-filter-audit-success', '')
  const [filterDateFrom, setFilterDateFrom] = usePersistedState('ucm-filter-audit-datefrom', '')
  const [filterDateTo, setFilterDateTo] = usePersistedState('ucm-filter-audit-dateto', '')
  const [presets, setPresets] = useState(readPresets)
  // A link of the overview opens the journal on one UTC day's failures of one type: it sets these filters, the others go
  const linked = useRef(null)
  // A link's action prefix, resolved into the journal's actions once the server listed them
  const prefixOf = (search) => {
    const v = new URLSearchParams(search).get('action_prefix') || ''
    return /^[\w.-]+$/.test(v) ? v : null
  }
  const [linkPrefix, setLinkPrefix] = useState(() => prefixOf(location.search))
  useEffect(() => {
    const q = new URLSearchParams(location.search)
    if (!LINK_KEYS.some((k) => q.has(k)) || linked.current === location.search) return
    linked.current = location.search
    const day = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(v || '') ? v : '')
    setFilterType(TYPES.some((x) => x.key === q.get('type')) ? q.get('type') : '')
    setFilterSuccess(['true', 'false'].includes(q.get('success')) ? q.get('success') : '')
    setFilterDateFrom(day(q.get('date_from')))
    setFilterDateTo(day(q.get('date_to')))
    setFilterUsername('')
    setFilterAction([])
    setLinkPrefix(prefixOf(location.search))
    setPage(1)
  }, [location.search]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (linkPrefix == null || !actionsRead) return
    const held = actions.filter((a) => a.startsWith(linkPrefix))
    // No action holds the prefix: the prefix itself, which no entry carries, selects nothing
    setFilterAction(held.length ? held : [linkPrefix])
    setLinkPrefix(null)
  }, [linkPrefix, actionsRead, actions]) // eslint-disable-line react-hooks/exhaustive-deps

  const [dialog, setDialog] = useState(null)
  const [cleanupLoading, setCleanupLoading] = useState(false)
  const [verifyingIntegrity, setVerifyingIntegrity] = useState(false)
  const { job: verifyJob, running: verifyRunning, follow: followJob, resume: resumeJob, cancel: cancelJob } = useJob()

  const chosenActions = Array.isArray(filterAction) ? filterAction : []
  const sentActions = useMemo(() => effectiveActions(actions, filterType, chosenActions),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [actions, filterType, JSON.stringify(chosenActions)])

  // The filters of the list, shared with the export so both select the same entries
  const filterParams = useMemo(() => ({
    search: search || undefined,
    username: filterUsername || undefined,
    action: sentActions && sentActions.length ? sentActions : undefined,
    success: filterSuccess !== '' ? filterSuccess : undefined,
    date_from: filterDateFrom || undefined,
    // The last day chosen is included: the server reads a bare date as its midnight
    date_to: filterDateTo ? `${filterDateTo}T23:59:59.999999` : undefined,
  }), [search, filterUsername, sentActions, filterSuccess, filterDateFrom, filterDateTo])
  // A type whose actions do not meet the chosen ones selects nothing: nothing is read
  const impossible = Array.isArray(sentActions) && sentActions.length === 0 && (Boolean(filterType) || chosenActions.length > 0)
  const typeWaits = (Boolean(filterType) && actions.length === 0) || linkPrefix != null

  const seq = useRef(0)
  const loadLogs = useCallback(async () => {
    const mine = ++seq.current
    if (typeWaits) return
    if (impossible) { setLogs([]); setTotal(0); setLoading(false); setLoadError(null); return }
    try {
      const res = await auditService.getLogs({ page, per_page: perPage, ...filterParams, sort_by: 'timestamp', sort_order: order })
      if (mine !== seq.current) return
      setLogs(res.data || [])
      setTotal(res.meta?.total || 0)
      setLoadError(null)
    } catch (error) {
      if (mine !== seq.current) return
      setLoadError({ status: error?.status, request: error?.request, message: error?.message })
      reportSilentFailure('loadLogs', error)
    } finally {
      if (mine === seq.current) setLoading(false)
    }
  }, [page, perPage, filterParams, impossible, typeWaits, order])

  // The journal as a whole: its size, its oldest entry, the last 30 days, the action codes
  const loadJournal = useCallback(async () => {
    try {
      const [head, statsRes, actionsRes] = await Promise.all([
        auditService.getLogs({ page: 1, per_page: 1 }),
        auditService.getStats(30),
        auditService.getActions(),
      ])
      const count = head?.meta?.total || 0
      setJournalTotal(count)
      setStats(statsRes?.data || null)
      setActions(actionsRes?.data?.actions || [])
      setActionsRead(true)
      if (count > 0) {
        const last = await auditService.getLogs({ page: count, per_page: 1 })
        setOldest(last?.data?.[0]?.timestamp || null)
      } else setOldest(null)
    } catch (error) { setActionsRead(true); reportSilentFailure('loadJournal', error) }
  }, [])

  useEffect(() => { loadJournal() }, [loadJournal])
  useEffect(() => { loadLogs() }, [loadLogs])
  useEffect(() => { try { localStorage.setItem(PRESETS_KEY, JSON.stringify(presets)) } catch { /* private mode */ } }, [presets])

  const refresh = () => { loadLogs(); loadJournal() }
  const retry = () => { setLoading(true); setLoadError(null); loadLogs() }

  const handleExport = async (format) => {
    try {
      const res = await auditService.exportLogs({ format, ...filterParams, limit: 10000 })
      const blob = new Blob([typeof res === 'string' ? res : JSON.stringify(res, null, 2)], {
        type: format === 'csv' ? 'text/csv' : 'application/json',
      })
      downloadBlob(blob, `audit_logs_${new Date().toISOString().slice(0, 10)}.${format}`)
      showSuccess(t('common.exportedFormat', { format: format.toUpperCase() }))
      setDialog(null)
    } catch {
      showError(t('audit.exportLogs') + ' ' + t('common.failed').toLowerCase())
    }
  }

  const handleCleanup = async (days) => {
    try {
      setCleanupLoading(true)
      const res = await auditService.cleanupLogs(days)
      showSuccess(res.message || t('audit.cleanedUpLogs', { count: res.data?.deleted || 0 }))
      setDialog(null)
      refresh()
    } catch {
      showError(t('audit.cleanupFailed'))
    } finally {
      setCleanupLoading(false)
    }
  }

  const showIntegrity = useCallback((data) => {
    const { level, key, params } = integrityMessage(data)
    const show = { error: showError, warning: showWarning, success: showSuccess }[level]
    show(t(key, params))
  }, [showError, showWarning, showSuccess, t])

  // A verification that outlasts the request runs as a job: its end is shown once it comes
  const showVerificationEnd = useCallback((job) => {
    if (job.state === 'succeeded' && job.result?.data) showIntegrity(job.result.data)
    else if (job.state === 'cancelled') showWarning(t('audit.verifyCancelled'))
    else if (job.reason === 'executor_lost' || job.reason === 'not_taken') showError(t('audit.verifyLost'))
    else showError(t('audit.integrityError'))
  }, [showIntegrity, showWarning, showError, t])

  const followVerification = useCallback(async (job) => {
    setVerifyingIntegrity(true)
    try {
      showVerificationEnd(await followJob(job))
    } catch {
      showError(t('audit.integrityError'))
    } finally {
      setVerifyingIntegrity(false)
    }
  }, [followJob, showVerificationEnd, showError, t])

  // After a reload: a verification still running is followed again, once per mount
  const verificationEnd = useRef(showVerificationEnd)
  verificationEnd.current = showVerificationEnd
  useEffect(() => {
    let gone = false
    resumeJob('audit_verify').then((job) => {
      if (!gone && job) verificationEnd.current(job)
    }).catch(() => {})
    return () => { gone = true }
  }, [resumeJob])

  const handleVerifyIntegrity = async () => {
    setDialog(null)
    setVerifyingIntegrity(true)
    try {
      const response = await auditService.verifyIntegrity()
      const job = acceptedJob(response)
      if (job) {
        await followVerification(job)
        return
      }
      showIntegrity(response.data || response)
    } catch {
      showError(t('audit.integrityError'))
    } finally {
      setVerifyingIntegrity(false)
    }
  }

  const handleCancelVerification = async () => {
    try { await cancelJob() } catch { showError(t('audit.verifyCancelFailed')) }
  }

  const verifying = verifyingIntegrity || verifyRunning
  const verifyProgress = verifyRunning && verifyJob?.progress?.total
    ? t('audit.verifyProgress', { done: verifyJob.progress.done || 0, total: verifyJob.progress.total })
    : null

  // Every filter change goes back to the first page
  const changeFilter = (set) => (value) => { set(value); setPage(1) }
  const clearFilters = useCallback(() => {
    setSearch(''); setFilterType(''); setFilterUsername(''); setFilterAction([])
    setFilterSuccess(''); setFilterDateFrom(''); setFilterDateTo(''); setPage(1)
  }, [setFilterType, setFilterUsername, setFilterAction, setFilterSuccess, setFilterDateFrom, setFilterDateTo])

  const applyPreset = (filters = {}) => {
    setPage(1)
    setFilterAction(filters.action ? (Array.isArray(filters.action) ? filters.action : [filters.action]) : [])
    setFilterSuccess(filters.status || '')
    setFilterUsername(filters.username || '')
    setFilterType(filters.type || '')
    setFilterDateFrom(filters.date_from || '')
    setFilterDateTo(filters.date_to || '')
    if (filters._search !== undefined) setSearch(filters._search || '')
  }
  const savePreset = (name) => {
    const filters = {}
    if (chosenActions.length) filters.action = chosenActions
    if (filterSuccess) filters.status = filterSuccess
    if (filterUsername) filters.username = filterUsername
    if (filterType) filters.type = filterType
    if (filterDateFrom) filters.date_from = filterDateFrom
    if (filterDateTo) filters.date_to = filterDateTo
    if (search) filters._search = search
    setPresets((prev) => [...prev, { id: Date.now(), name, filters }])
  }

  const usernames = useMemo(() => {
    const names = new Set(logs.map((l) => l.username).filter(Boolean))
    if (filterUsername) names.add(filterUsername)
    return [...names].sort()
  }, [logs, filterUsername])
  const types = useMemo(() => {
    const list = presentTypes(actions)
    return filterType && !list.includes(filterType) ? [...list, filterType] : list
  }, [actions, filterType])

  const pages = Math.max(1, Math.ceil(total / perPage))
  const narrowed = Boolean(search || filterType || filterUsername || chosenActions.length || filterSuccess || filterDateFrom || filterDateTo)
  const journalEmpty = journalTotal === 0 && !narrowed && !loading && !loadError

  const resourceOf = (log) => log.resource_name
    || (log.resource_type ? `${log.resource_type}${log.resource_id ? ` #${log.resource_id}` : ''}` : '—')
  const openEvent = (log) => setDialog({ kind: 'event', log })

  // Chips of the filters the toolbar does not show
  const chips = []
  const chip = (key, label, onRemove) => chips.push({ key, label, onRemove })
  if (filterUsername) chip('user', t('audit.chipUser', { user: filterUsername }), () => changeFilter(setFilterUsername)(''))
  if (filterSuccess) chip('result', filterSuccess === 'true' ? t('audit.resultsOk') : t('audit.resultsFailed'), () => changeFilter(setFilterSuccess)(''))
  if (filterDateFrom) chip('from', t('audit.chipFrom', { date: eventDate(`${filterDateFrom}T12:00:00`, locale) }), () => changeFilter(setFilterDateFrom)(''))
  if (filterDateTo) chip('to', t('audit.chipTo', { date: eventDate(`${filterDateTo}T12:00:00`, locale) }), () => changeFilter(setFilterDateTo)(''))
  for (const a of chosenActions) chip(`action-${a}`, t('audit.chipAction', { action: actionLabel(a, t) }), () => changeFilter(setFilterAction)(chosenActions.filter((x) => x !== a)))

  const firstRead = loading && !loadError
  const shown = firstRead ? [] : logs

  const emptyBlock = journalEmpty ? (
    <SetupEmptyBlock id="activity" icon="activity" title={t('audit.emptyTitle')} text={t('audit.emptyText')}
      action={canWrite('certificates') ? { label: t('audit.emptyAction'), icon: 'plus', to: '/certificates?action=create', primary: true } : undefined} />
  ) : (
    <NoMatch icon={false} title={t('audit.noMatchTitle')} text={t('audit.noMatchText')} resetLabel={t('audit.resetFilters')} onReset={narrowed ? clearFilters : undefined} />
  )
  const badgeOf = (e) => (e.success
    ? <span className="badge good"><Icon name="check" />{t('audit.badgeOk')}</span>
    : <span className="badge bad"><Icon name="warning" />{t('audit.badgeFailed')}</span>)

  // The journal's columns: short ones fit their content (adjust.css), the operation and the resource share the rest
  const columns = [
    { id: 'time', label: t('audit.colTime'), fit: true, sort: 'timestamp', tone: ['mono', 'muted'], cell: (e) => rowTime(e.timestamp, locale), skeleton: { width: '64px' } },
    { id: 'operation', label: t('audit.colOperation'), cell: (e) => <span className="audit-type"><Icon name={typeIcon(typeOf(e.action))} />{actionLabel(e.action, t)}</span>, skeleton: { base: 45, spread: 35 } },
    // The resource takes the room left and gives way by an ellipsis, its whole text in a title (audit-resource, R1, L6)
    { id: 'resource', label: t('audit.colResource'), resource: true, tone: 'audit-resource', title: resourceOf, cell: resourceOf, skeleton: { base: 50, spread: 40 } },
    { id: 'user', label: t('audit.colUser'), fit: true, tone: ['muted', 'small'], cell: (e) => e.username || t('common.system'), skeleton: { width: '70px' } },
    { id: 'result', label: t('audit.colResult'), fit: true, cell: badgeOf, skeleton: { width: '74px', kind: 'pill' } },
  ]
  const card = (e) => ({
    title: resourceOf(e),
    meta: [<span key="type" className="audit-type"><Icon name={typeIcon(typeOf(e.action))} />{actionLabel(e.action, t)}</span>, e.username || t('common.system')],
    status: badgeOf(e),
    end: rowTime(e.timestamp, locale),
  })

  return (
    <Zone testId="audit-page" after={<>
      {dialog?.kind === 'event' && (
        <EventDialog log={dialog.log} locale={locale} resource={resourceOf(dialog.log)} onClose={() => setDialog(null)}
          canInspect={(type) => hasPermission(type === 'ca' ? 'read:cas' : 'read:certificates')}
          onInspect={(type, id) => { setDialog(null); openEntity(type, id) }} />
      )}
      {dialog === 'export' && (
        <ExportDialog count={total} onExport={handleExport} onClose={() => setDialog(null)} />
      )}
      {dialog === 'actions' && (
        <ActionsDialog canClean={canDelete('audit')} verifying={verifying} onExport={() => setDialog('export')}
          onVerify={handleVerifyIntegrity} onClean={() => setDialog('cleanup')} onClose={() => setDialog(null)} />
      )}
      {dialog === 'cleanup' && canDelete('audit') && (
        <CleanupDialog loading={cleanupLoading} onConfirm={handleCleanup} onClose={() => setDialog(null)} />
      )}
      {dialog === 'filters' && (
        <FiltersDialog
          actions={actions} type={filterType} chosen={chosenActions}
          usernames={usernames} username={filterUsername} onUsername={changeFilter(setFilterUsername)}
          result={filterSuccess} onResult={changeFilter(setFilterSuccess)}
          dateFrom={filterDateFrom} dateTo={filterDateTo}
          onDateFrom={changeFilter(setFilterDateFrom)} onDateTo={changeFilter(setFilterDateTo)}
          onActions={changeFilter(setFilterAction)}
          onQuick={(kind) => {
            setPage(1)
            if (kind === 'failedLogins') { setFilterAction(['login_failure']); setFilterSuccess('') }
            else { setFilterSuccess('false'); setFilterAction([]) }
            setDialog(null)
          }}
          quick={{ failedLogins: chosenActions.length === 1 && chosenActions[0] === 'login_failure', failures: filterSuccess === 'false' && !chosenActions.length }}
          presets={presets} onApplyPreset={(p) => { applyPreset(p.filters); setDialog(null) }}
          onDeletePreset={(id) => setPresets((prev) => prev.filter((p) => p.id !== id))}
          onSavePreset={savePreset} canSave={narrowed}
          narrowed={narrowed} onClear={() => { clearFilters(); setDialog(null) }}
          onClose={() => setDialog(null)} />
      )}
    </>}>
      <PageHead title={t('audit.pageTitle')} total={journalTotal === null ? '' : t('audit.events', { count: journalTotal })} intent={t('audit.intent')}
        actions={<>
          <Btn icon="download" data-action="export-events" onClick={() => setDialog('export')}>{t('audit.exportJournal')}</Btn>
          <IconBtn quiet icon="more" data-action="journal-menu" label={t('audit.moreActions')} onClick={() => setDialog('actions')} />
        </>} />

      <Toolbar>
        <SearchField id="event-search" name="eventSearch" label={t('audit.searchLabel')} placeholder={t('audit.searchPlaceholder')} value={search}
          onChange={changeFilter(setSearch)} />
        <FilterSelect id="event-type" label={t('audit.typeLabel')} value={filterType} onChange={changeFilter(setFilterType)}
          options={[{ value: '', label: t('audit.allTypes') }, ...types.map((k) => ({ value: k, label: t(`audit.types.${k}`) }))]} />
        <ToolsDivider />
        <Btn icon="filter" data-action="filters" onClick={() => setDialog('filters')}><span>{t('audit.filters')}</span></Btn>
        <IconBtn icon="refresh" data-action="refresh" label={t('audit.refresh')} onClick={refresh} />
      </Toolbar>

      <AppliedFilters chips={chips} />

      {loadError ? (
        <LoadError id="activity" title={t('audit.loadErrorTitle')} onRetry={retry}
          cause={<LoadCause error={loadError} fallback={t('messages.errors.loadFailed.auditLogs')} />} />
      ) : (
        <>
          <div className="audit-summary">
            <span>{firstRead ? '' : t('audit.events', { count: total })}</span>
            {oldest && <span>{t('audit.since', { date: eventDate(oldest, locale) })}</span>}
            {stats && <span>{t('audit.last30', { success: (stats.success_count || 0).toLocaleString(locale), failed: (stats.failure_count || 0).toLocaleString(locale), users: (stats.unique_users || 0).toLocaleString(locale) })}</span>}
            {verifying && (
              <span role="status">{verifyProgress || t('audit.verifying')}
                {verifyRunning && <> <button type="button" className="text-link" data-testid="audit-verify-cancel" onClick={handleCancelVerification}>{t('audit.verifyCancel')}</button></>}
              </span>
            )}
          </div>
          <DataTable kind="audit" scrollId="audit-scroll" recordsId="audit-records" label={t('audit.regionLabel')} columns={columns} rows={shown}
            rowKey={(e) => e.id} rowLabel={resourceOf} loading={firstRead} onOpen={openEvent} sort={sort} onSort={onSort} openLabel={(e) => t('audit.detailOf', { id: e.id })}
            actionsLabel={t('audit.colDetail')} empty={emptyBlock} card={card}
            footer={!firstRead && total > 0 && (
              <TableFooter range={t('audit.pageRange', {
                from: ((page - 1) * perPage + 1).toLocaleString(locale),
                to: Math.min(page * perPage, total).toLocaleString(locale),
                count: total,
              })} pagination={{ page, pages, perPage, sizes: PAGE_SIZES, onPage: setPage, onPerPage: (n) => { setPerPage(n); setPage(1) }, perPageLabel: t('audit.perPageLabel'), jump: true }} />
            )} />
        </>
      )}
    </Zone>
  )
}
