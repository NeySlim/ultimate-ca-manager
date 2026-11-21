/**
 * Activité: the audit journal, as the mockup's activity() draws it (page head, toolbar, summary,
 * event rows, detail dialog, empty state), on the server's entries. What the mockup has not and
 * the product keeps (filters, server pages, export formats, integrity check, clean-up, saved
 * filters) borrows the mockup's own gabarits: filter selects, applied filters, table footer, dialogs.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation, Trans } from 'react-i18next'
import { Icon } from '../components/atelier/Icon'
import { useNotification, useInspector } from '../contexts'
import { integrityMessage } from '../lib/auditIntegrity'
import { usePermission, usePersistedState, useJob } from '../hooks'
import { acceptedJob } from '../services/jobs.service'
import auditService from '../services/audit.service'
import { downloadBlob } from '../lib/utils'
import { reportSilentFailure } from '../lib/silentFailure'
import { typeOf, typeIcon, presentTypes, effectiveActions, actionLabel } from './activity/activityTypes'
import { rowTime, eventDate } from './activity/activityDates'
import { EventDialog } from './activity/EventDialog'
import { ExportDialog, ActionsDialog, CleanupDialog } from './activity/JournalDialogs'
import { FiltersDialog } from './activity/FiltersDialog'
import '../styles/atelier/scope.css'
import '../styles/atelier/maquette.css'
import { useMobile } from '../contexts/MobileContext'

const PAGE_SIZES = [10, 25, 50, 100]
const PRESETS_KEY = 'ucm-audit-presets'
const skWidth = (i, base, spread) => `${base + ((i * 37) % spread)}%`
const Bar = ({ width, cls = '' }) => <span className={`sk ${cls}`.trim()} style={{ width }} />

function readPresets() {
  try { const saved = localStorage.getItem(PRESETS_KEY); return saved ? JSON.parse(saved) : [] } catch { return [] }
}

export default function AuditLogsPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.language || 'en'
  const { showError, showSuccess, showWarning } = useNotification()
  const { openEntity } = useInspector()
  const { canDelete, canWrite, hasPermission } = usePermission()
  // On a phone each entry is a record, its chevron on screen; the table stays on wider screens
  const { isMobile } = useMobile()

  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [journalTotal, setJournalTotal] = useState(null)
  const [oldest, setOldest] = useState(null)
  const [stats, setStats] = useState(null)
  const [actions, setActions] = useState([])

  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(50)
  const [pageInput, setPageInput] = useState('1')

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
    date_to: filterDateTo || undefined,
  }), [search, filterUsername, sentActions, filterSuccess, filterDateFrom, filterDateTo])
  // A type whose actions do not meet the chosen ones selects nothing: nothing is read
  const impossible = Array.isArray(sentActions) && sentActions.length === 0 && (Boolean(filterType) || chosenActions.length > 0)
  const typeWaits = Boolean(filterType) && actions.length === 0

  const seq = useRef(0)
  const loadLogs = useCallback(async () => {
    const mine = ++seq.current
    if (typeWaits) return
    if (impossible) { setLogs([]); setTotal(0); setLoading(false); setLoadError(null); return }
    try {
      const res = await auditService.getLogs({ page, per_page: perPage, ...filterParams })
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
  }, [page, perPage, filterParams, impossible, typeWaits])

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
      if (count > 0) {
        const last = await auditService.getLogs({ page: count, per_page: 1 })
        setOldest(last?.data?.[0]?.timestamp || null)
      } else setOldest(null)
    } catch (error) { reportSilentFailure('loadJournal', error) }
  }, [])

  useEffect(() => { loadJournal() }, [loadJournal])
  useEffect(() => { loadLogs() }, [loadLogs])
  useEffect(() => { setPageInput(String(page)) }, [page])
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
  const goTo = (n) => setPage(Math.min(pages, Math.max(1, n)))
  const narrowed = Boolean(search || filterType || filterUsername || chosenActions.length || filterSuccess || filterDateFrom || filterDateTo)
  const journalEmpty = journalTotal === 0 && !narrowed && !loading && !loadError

  const resourceOf = (log) => log.resource_name
    || (log.resource_type ? `${log.resource_type}${log.resource_id ? ` #${log.resource_id}` : ''}` : '—')
  const openEvent = (log) => setDialog({ kind: 'event', log })

  // Chips of the filters the toolbar does not show
  const chips = []
  if (filterUsername) chips.push(['user', t('audit.chipUser', { user: filterUsername }), () => changeFilter(setFilterUsername)('')])
  if (filterSuccess) chips.push(['result', filterSuccess === 'true' ? t('audit.resultsOk') : t('audit.resultsFailed'), () => changeFilter(setFilterSuccess)('')])
  if (filterDateFrom) chips.push(['from', t('audit.chipFrom', { date: eventDate(`${filterDateFrom}T12:00:00`, locale) }), () => changeFilter(setFilterDateFrom)('')])
  if (filterDateTo) chips.push(['to', t('audit.chipTo', { date: eventDate(`${filterDateTo}T12:00:00`, locale) }), () => changeFilter(setFilterDateTo)('')])
  for (const a of chosenActions) chips.push([`action-${a}`, t('audit.chipAction', { action: actionLabel(a) }), () => changeFilter(setFilterAction)(chosenActions.filter((x) => x !== a))])

  const cause = loadError?.status && loadError.request ? (
    <Trans i18nKey="work.cause.status"
      values={{ status: loadError.status, reason: t(`certificates.httpStatus${loadError.status}`, { defaultValue: '' }), request: loadError.request }}
      components={{ mono: <span className="mono" /> }} />
  ) : loadError?.request ? (
    <Trans i18nKey="work.cause.noAnswer" values={{ request: loadError.request }} components={{ mono: <span className="mono" /> }} />
  ) : t('work.cause.message', { message: loadError?.message || t('messages.errors.loadFailed.auditLogs') })

  const firstRead = loading && !loadError
  const shown = firstRead ? [] : logs

  const emptyBlock = journalEmpty ? (
    <div className="empty empty-hint" id="empty-activity">
      <Icon name="activity" />
      <h3>{t('audit.emptyTitle')}</h3>
      <p>{t('audit.emptyText')}</p>
      {canWrite('certificates') && (
        <Link className="btn primary" to="/certificates?action=create" data-write=""><Icon name="plus" />{t('audit.emptyAction')}</Link>
      )}
    </div>
  ) : (
    <div className="empty">
      <h3>{t('audit.noMatchTitle')}</h3>
      <p>{t('audit.noMatchText')}</p>
      {narrowed && <button type="button" className="btn" data-action="reset-filters" onClick={clearFilters}>{t('audit.resetFilters')}</button>}
    </div>
  )
  const badgeOf = (e) => (e.success
    ? <span className="badge good"><Icon name="check" />{t('audit.badgeOk')}</span>
    : <span className="badge bad"><Icon name="warning" />{t('audit.badgeFailed')}</span>)

  return (
    <div className="atl" data-testid="audit-page">
      <main className="stage" id="main">
        <div className="page-content">
          <header className="page-head">
            <div>
              <div className="title-line">
                <h1 id="main-title" tabIndex={-1}>{t('audit.pageTitle')}</h1>
                <span className="total">{journalTotal === null ? '' : t('audit.events', { count: journalTotal })}</span>
              </div>
              <p>{t('audit.intent')}</p>
            </div>
            <div className="actions">
              <button type="button" className="btn" data-action="export-events" onClick={() => setDialog('export')}>
                <Icon name="download" />{t('audit.exportJournal')}
              </button>
              <button type="button" className="icon-btn quiet" data-action="journal-menu" aria-label={t('audit.moreActions')} title={t('audit.moreActions')} onClick={() => setDialog('actions')}>
                <Icon name="more" />
              </button>
            </div>
          </header>

          <div className="toolbar">
            <label className="search">
              <Icon name="search" />
              <span className="sr-only">{t('audit.searchLabel')}</span>
              <input type="search" id="event-search" name="eventSearch" value={search} placeholder={t('audit.searchPlaceholder')} autoComplete="off"
                onChange={(e) => changeFilter(setSearch)(e.target.value)} />
            </label>
            <select className="filter-select" id="event-type" aria-label={t('audit.typeLabel')} value={filterType} onChange={(e) => changeFilter(setFilterType)(e.target.value)}>
              <option value="">{t('audit.allTypes')}</option>
              {types.map((k) => <option key={k} value={k}>{t(`audit.types.${k}`)}</option>)}
            </select>
            <span className="tools-divider" />
            <button type="button" className="btn" data-action="filters" onClick={() => setDialog('filters')}>
              <Icon name="filter" /><span>{t('audit.filters')}</span>
            </button>
            <button type="button" className="icon-btn" data-action="refresh" aria-label={t('audit.refresh')} title={t('audit.refresh')} onClick={refresh}>
              <Icon name="refresh" />
            </button>
          </div>

          {chips.length > 0 && (
            <div className="applied-filters" role="group" aria-label={t('audit.activeFilters')}>
              <span className="applied-label"><Icon name="filter" />{t('audit.activeFilters')}</span>
              {chips.map(([key, label, remove]) => (
                <span key={key} className="chip filter-chip">{label}
                  <button type="button" className="icon-btn" id={`clear-${key}`} aria-label={t('audit.removeFilter', { label })} title={t('audit.removeFilterShort')} onClick={remove}>
                    <Icon name="close" />
                  </button>
                </span>
              ))}
            </div>
          )}

          {loadError ? (
            <div className="load-error" id="load-error-activity" role="alert">
              <Icon name="warning" />
              <div>
                <h2>{t('audit.loadErrorTitle')}</h2>
                <p>{cause}</p>
                <div className="load-error-actions">
                  <button type="button" className="btn primary" id="retry-activity" onClick={retry}><Icon name="refresh" />{t('table.retry')}</button>
                </div>
              </div>
            </div>
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
              <div className="table-container audit-container" style={{ marginBottom: 20 }} aria-busy={firstRead || undefined}>
                {isMobile ? (
                  <div className="mobile-list" id="audit-records">
                    {firstRead ? Array.from({ length: 6 }, (_, i) => (
                      <article key={`sk-${i}`} className="mobile-record sk-record" aria-hidden={i > 0 || undefined}>
                        {i === 0 && <span className="sr-only" role="status">{t('table.loadingRows')}</span>}
                        <Bar width={skWidth(i, 50, 30)} /><Bar width={skWidth(i, 30, 40)} cls="sk-thin" /><Bar width="90px" cls="sk-pill" />
                      </article>
                    )) : shown.length ? shown.map((e) => {
                      const type = typeOf(e.action)
                      return (
                        // The whole record opens the detail; its two buttons reach it from the keyboard
                        <article key={e.id} className="mobile-record opens" data-event={e.id} onClick={() => openEvent(e)}>
                          <div className="row-top">
                            <button type="button" className="entity-name" data-event={e.id}>{resourceOf(e)}</button>
                            <button type="button" className="icon-btn quiet" data-event={e.id} aria-label={t('audit.detailOf', { id: e.id })}><Icon name="right" /></button>
                          </div>
                          <div className="row-meta">
                            <span className="audit-type"><Icon name={typeIcon(type)} />{actionLabel(e.action)}</span>
                            <span>{e.username || t('common.system')}</span>
                          </div>
                          <div className="row-status">{badgeOf(e)}<span className="remaining">{rowTime(e.timestamp, locale)}</span></div>
                        </article>
                      )
                    }) : emptyBlock}
                  </div>
                ) : (
                  <div className="table-scroll" id="audit-scroll" role="region" tabIndex={0} aria-label={t('audit.regionLabel')}>
                    <table className="audit-table">
                      <thead>
                        <tr>
                          <th scope="col" className="fit">{t('audit.colTime')}</th>
                          <th scope="col">{t('audit.colOperation')}</th>
                          <th scope="col">{t('audit.colResource')}</th>
                          <th scope="col" className="fit">{t('audit.colUser')}</th>
                          <th scope="col" className="fit">{t('audit.colResult')}</th>
                          <th scope="col" className="fit"><span className="sr-only">{t('audit.colDetail')}</span></th>
                        </tr>
                      </thead>
                      <tbody>
                        {firstRead ? Array.from({ length: 12 }, (_, i) => (
                          <tr key={`sk-${i}`} className="sk-row" aria-hidden={i > 0 || undefined}>
                            <td>{i === 0 && <span className="sr-only" role="status">{t('table.loadingRows')}</span>}<Bar width="64px" /></td>
                            <td><Bar width={skWidth(i, 45, 35)} /></td>
                            <td><Bar width={skWidth(i, 50, 40)} /></td>
                            <td><Bar width="70px" /></td>
                            <td><Bar width="74px" cls="sk-pill" /></td>
                            <td />
                          </tr>
                        )) : shown.length ? shown.map((e) => {
                          const type = typeOf(e.action)
                          const label = actionLabel(e.action)
                          return (
                            <tr key={e.id}>
                              <td className="mono muted">{rowTime(e.timestamp, locale)}</td>
                              <td><span className="audit-type"><Icon name={typeIcon(type)} />{label}</span></td>
                              <td><button type="button" className="resource" data-event={e.id} onClick={() => openEvent(e)}>{resourceOf(e)}</button></td>
                              <td className="muted small">{e.username || t('common.system')}</td>
                              <td>{badgeOf(e)}</td>
                              <td><button type="button" className="icon-btn quiet" data-event={e.id} aria-label={t('audit.detailOf', { id: e.id })} onClick={() => openEvent(e)}><Icon name="right" /></button></td>
                            </tr>
                          )
                        }) : (
                          <tr><td colSpan={6}>{emptyBlock}</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
                {!firstRead && total > 0 && (
                  <footer className="table-footer">
                    <span id="page-range">{t('audit.pageRange', {
                      from: ((page - 1) * perPage + 1).toLocaleString(locale),
                      to: Math.min(page * perPage, total).toLocaleString(locale),
                      count: total,
                    })}</span>
                    <div className="controls">
                      <select id="page-size" aria-label={t('audit.perPageLabel')} value={perPage} onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1) }}>
                        {PAGE_SIZES.map((n) => <option key={n} value={n}>{t('audit.perPage', { n })}</option>)}
                      </select>
                      <button type="button" className="icon-btn" data-page="prev" aria-label={t('audit.prevPage')} disabled={page === 1} onClick={() => goTo(page - 1)}><Icon name="left" /></button>
                      <label className="page-jump"><span>{t('audit.pageWord')}</span>
                        <input id="page-jump" type="number" min="1" max={pages} value={pageInput} inputMode="numeric" aria-describedby="page-total"
                          onChange={(e) => setPageInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') goTo(parseInt(pageInput, 10) || 1) }} />
                      </label>
                      <span id="page-total">{t('audit.pageTotal', { total: pages.toLocaleString(locale) })}</span>
                      <button type="button" className="btn" id="page-go" data-action="page-go" onClick={() => goTo(parseInt(pageInput, 10) || 1)}>{t('audit.pageGo')}</button>
                      <button type="button" className="icon-btn" data-page="next" aria-label={t('audit.nextPage')} disabled={page >= pages} onClick={() => goTo(page + 1)}><Icon name="right" /></button>
                    </div>
                  </footer>
                )}
              </div>
            </>
          )}
        </div>

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
      </main>
    </div>
  )
}
