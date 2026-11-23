/**
 * Journaux système: the server's own application log, drawn with the mockup's list gabarit as
 * the Activity page is (page head, toolbar, applied filters, summary, the journal table, cards on
 * a phone). Every filter is the server's: source, component, level, line count, time window,
 * search and exclusion; the lines are copied as the file wrote them.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Zone, Icon, Btn, IconBtn, Pill, PageHead, Toolbar, SearchField, FilterSelect, ToolsDivider, AppliedFilters,
  BatchBar, DataTable, TableFooter, EmptyBlock, NoMatch, AtelierDialog, useSortParam,
} from '../components/atelier'
import { useNotification } from '../contexts'
import { systemService } from '../services'
import { extractData } from '../lib/utils'

const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
const LINE_COUNTS = [100, 200, 500, 1000, 2000, 5000]
const FOLLOW_INTERVAL_MS = 5000
// Every read costs the server a two megabyte tail, a redaction pass and a parse, on the worker
// that also answers ACME, SCEP and OCSP: a word typed is one request, not one per character.
const TYPING_PAUSE_MS = 300

const SOURCE_LABELS = {
  app: 'logs.sourceApp',
  access: 'logs.sourceAccess',
  error: 'logs.sourceError',
  journal: 'logs.sourceJournal',
}

// A level's tone and icon: the colour is never the only signal
const LEVEL_TONE = {
  DEBUG: { tone: 'muted', icon: 'code' },
  INFO: { tone: '', icon: 'activity' },
  WARNING: { tone: 'warn', icon: 'warning' },
  ERROR: { tone: 'bad', icon: 'warning' },
  CRITICAL: { tone: 'bad', icon: 'block' },
}

// What was typed, once the typing stopped; the box itself stays on the raw value
function useSettled(value, delay = TYPING_PAUSE_MS) {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return settled
}

const levelPill = (level) => (level ? <Pill label={level} tone={LEVEL_TONE[level]?.tone} icon={LEVEL_TONE[level]?.icon} /> : null)

// The file's lines sort by their time only, the newest first by default, kept in the address
const NEWEST_FIRST = { key: 'time', asc: false }
const TIME_KEYS = ['time']

export default function SystemLogsPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || undefined
  const { showError, showSuccess } = useNotification()
  const [source, setSource] = useState('app')
  const [component, setComponent] = useState('')
  const [level, setLevel] = useState('INFO')
  const [lines, setLines] = useState('200')
  const [search, setSearch] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [follow, setFollow] = useState(false)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showFilters, setShowFilters] = useState(false)
  const [exclude, setExclude] = useState('')
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  useEffect(() => { setSelectedIds((prev) => (prev.size ? new Set() : prev)) }, [result])   // ids are row indexes
  const query = useSettled(search)
  const omit = useSettled(exclude)

  // Only the newest request may fill the page, and a poll never stacks on a read
  const sequence = useRef(0)
  const inFlight = useRef(false)
  const load = useCallback(async (quiet = false) => {
    if (quiet && inFlight.current) return
    const mine = ++sequence.current
    inFlight.current = true
    if (!quiet) setLoading(true)
    try {
      const response = await systemService.getApplicationLog({
        source, level, lines: parseInt(lines),
        ...(component ? { component } : {}),
        ...(query ? { q: query } : {}),
        ...(since ? { since } : {}),
        ...(until ? { until } : {}),
        ...(omit ? { exclude: omit } : {}),
      })
      if (mine === sequence.current) setResult(extractData(response))
    } catch {
      if (mine !== sequence.current) return
      if (!quiet) showError(t('logs.unavailable'))
      setResult((prev) => (quiet ? prev : null))
    } finally {
      if (mine === sequence.current) {
        inFlight.current = false
        if (!quiet) setLoading(false)
      }
    }
  }, [source, component, level, lines, query, since, until, omit, showError, t])

  useEffect(() => { load() }, [source, component, level, lines, query, since, until, omit])  // eslint-disable-line react-hooks/exhaustive-deps

  // Live mode polls rather than streaming: a line pushed over the event bus is itself logged by the push
  useEffect(() => {
    if (!follow) return undefined
    const id = setInterval(() => load(true), FOLLOW_INTERVAL_MS)
    return () => clearInterval(id)
  }, [follow, load])

  // The server returns the tail oldest-first: the file's order is the time's, reversed for the newest first
  const { sort, onSort } = useSortParam(NEWEST_FIRST, TIME_KEYS)
  const rows = useMemo(() => {
    const lines = (result?.lines || []).map((line, index) => ({ id: index, ...line }))
    return sort.asc ? lines : lines.reverse()
  }, [result, sort.asc])

  const sourceOptions = (result?.available_sources || ['app']).map((s) => ({ value: s, label: t(SOURCE_LABELS[s] || s) }))
  const componentOptions = [
    { value: '', label: t('logs.allComponents') },
    ...(result?.components || []).map((c) => ({ value: c, label: c })),
  ]

  // A window into the past and a tail of the present are opposite requests: following clears the window
  const toggleFollow = () => {
    const on = !follow
    setFollow(on)
    if (on) { setSince(''); setUntil(''); setShowFilters(false) }
  }
  const clearPanel = () => { setSource('app'); setComponent(''); setSince(''); setUntil(''); setExclude('') }

  // Copied as the log wrote it, whatever the source, so a pasted line parses back here
  const copy = (subset) => {
    const text = subset
      .map((l) => l.raw ?? [l.ts, l.logger && `[${l.logger}]`, l.level, l.message].filter(Boolean).join(' '))
      .join('\n')
    navigator.clipboard.writeText(text).then(
      () => showSuccess(t('common.copy')),
      () => showError(t('common.copy')),
    )
  }

  // The filters the toolbar does not show, one chip each
  const chips = []
  if (source !== 'app') chips.push({ key: 'source', label: t('logs.chipSource', { source: t(SOURCE_LABELS[source] || source) }), onRemove: () => setSource('app') })
  if (component) chips.push({ key: 'component', label: t('logs.chipComponent', { component }), onRemove: () => setComponent('') })
  if (since) chips.push({ key: 'since', label: t('logs.chipFrom', { date: since.replace('T', ' ') }), onRemove: () => setSince('') })
  if (until) chips.push({ key: 'until', label: t('logs.chipTo', { date: until.replace('T', ' ') }), onRemove: () => setUntil('') })
  if (exclude) chips.push({ key: 'exclude', label: t('logs.chipExclude', { text: exclude }), onRemove: () => setExclude('') })

  const levels = result?.levels || {}
  const matched = result?.matched || 0
  const firstRead = loading && !result
  const narrowed = Boolean(search || chips.length)
  const fmt = (n) => Number(n).toLocaleString(locale)

  const empty = result && !result.exists ? (
    <EmptyBlock id="logs" icon="activity" title={t('logs.unavailable')} />
  ) : (
    <NoMatch icon="search" title={t('logs.empty')} text={t('common.tryAdjustFilters')} resetLabel={t('table.clearFilters')}
      onReset={narrowed ? () => { setSearch(''); clearPanel() } : undefined} />
  )

  // Short columns fit their content (adjust.css); the message takes the rest and wraps
  const columns = [
    { id: 'ts', label: t('logs.time'), sort: 'time', fit: true, tone: ['mono', 'muted'], cell: (l) => l.ts || '', skeleton: { width: '130px' } },
    // A line whose format carries no level gets no badge: a placeholder would read as a level of its own
    { id: 'level', label: t('logs.levelShort'), fit: true, cell: (l) => levelPill(l.level), skeleton: { width: '70px', kind: 'pill' } },
    { id: 'logger', label: t('logs.component'), fit: true, tone: ['mono', 'muted', 'small'], cell: (l) => l.logger || '', skeleton: { width: '110px' } },
    { id: 'message', label: t('logs.message'), tone: 'mono', cell: (l) => <span className="log-message">{l.message}</span>, skeleton: { base: 50, spread: 40 } },
  ]
  const card = (l) => ({
    title: <span className="log-message mono">{l.message}</span>,
    meta: [l.logger && <span key="logger" className="mono">{l.logger}</span>],
    status: levelPill(l.level),
    end: l.ts || '',
  })

  const footNote = result ? [
    result.path ? `${t('logs.readingFrom')} ${result.path}` : null,
    `${t('logs.serverTime')}${result.timezone?.name || result.timezone?.offset ? ` (${[result.timezone.name, result.timezone.offset].filter(Boolean).join(' ')})` : ''}`,
    result.truncated ? t('logs.showing', { shown: rows.length, matched }) : null,
    result.scan_truncated ? t('logs.scanCap') : null,
  ].filter(Boolean).join(' · ') : ''

  const selection = {
    selected: selectedIds,
    onToggle: (id) => setSelectedIds((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next }),
    onTogglePage: (on) => setSelectedIds(on ? new Set(rows.map((r) => r.id)) : new Set()),
  }

  return (
    <Zone testId="logs-page" after={showFilters && (
      <AtelierDialog title={t('logs.filters')} subtitle={t('logs.filtersIntent')} size="narrow" onClose={() => setShowFilters(false)} returnTo="logs-filters">
        <div className="form-fields">
          <div className="field">
            <label htmlFor="log-source">{t('logs.source')}</label>
            <select id="log-source" value={source} onChange={(e) => { setSource(e.target.value); if (e.target.value !== 'app') setComponent('') }}>
              {sourceOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="log-component">{t('logs.component')}</label>
            <select id="log-component" value={component} disabled={source !== 'app'} onChange={(e) => setComponent(e.target.value)}>
              {componentOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="log-from">{t('logs.from')}</label>
            <input id="log-from" type="datetime-local" value={since} disabled={follow} aria-describedby="hint-log-time" onChange={(e) => setSince(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="log-to">{t('logs.to')}</label>
            <input id="log-to" type="datetime-local" value={until} disabled={follow} aria-describedby="hint-log-time" onChange={(e) => setUntil(e.target.value)} />
          </div>
          <p className="field full muted small" id="hint-log-time">{t('logs.serverTime')}</p>
          {/* Search and exclusion are substrings, not patterns: a pattern from the browser is unbounded work */}
          <div className="field full">
            <label htmlFor="log-exclude">{t('logs.exclude')}</label>
            <input id="log-exclude" value={exclude} autoComplete="off" spellCheck={false} aria-describedby="hint-log-exclude" onChange={(e) => setExclude(e.target.value)} />
            <small id="hint-log-exclude">{t('logs.excludeHint')}</small>
          </div>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" data-action="reset-filters" onClick={clearPanel}>{t('common.clear')}</button>
          <button type="button" className="btn primary" data-action="close-modal" onClick={() => setShowFilters(false)}>{t('common.done')}</button>
        </div>
      </AtelierDialog>
    )}>
      <PageHead title={t('logs.title')} total={result ? t('logs.unit', { count: matched }) : ''} intent={t('logs.subtitle')} />

      <Toolbar>
        <SearchField id="log-search" name="logSearch" label={t('logs.searchPlaceholder')} placeholder={t('logs.searchPlaceholder')} value={search} onChange={setSearch} />
        <FilterSelect id="log-level" label={t('logs.level')} value={level} onChange={setLevel} options={LEVELS.map((l) => ({ value: l, label: l }))} />
        <FilterSelect id="log-lines" label={t('logs.lines')} value={lines} onChange={setLines}
          options={LINE_COUNTS.map((n) => ({ value: String(n), label: t('logs.linesOpt', { count: n }) }))} />
        <ToolsDivider />
        <Btn icon="filter" id="logs-filters" data-action="filters" title={t('logs.filters')} onClick={() => setShowFilters(true)}><span>{t('logs.filters')}</span></Btn>
        <button type="button" className="btn" id="logs-follow" data-action="follow" aria-pressed={follow} title={t('logs.follow')} onClick={toggleFollow}>
          <Icon name="activity" /><span>{t('logs.follow')}</span>
        </button>
        {/* In the toolbar rather than the head: on a phone the head keeps only a primary action, the toolbar keeps its tools */}
        <Btn icon="copy" data-action="copy-all" title={t('logs.copyAll')} disabled={!rows.length || undefined} onClick={() => copy(rows)}><span>{t('logs.copyAll')}</span></Btn>
        <IconBtn icon="refresh" data-action="refresh" label={t('logs.refresh')} disabled={loading || undefined} onClick={() => load()} />
      </Toolbar>

      <AppliedFilters chips={chips} onClearAll={clearPanel} />

      {selectedIds.size > 0 && (
        <BatchBar count={t('logs.selected', { count: selectedIds.size })} onClear={() => setSelectedIds(new Set())}>
          <Btn icon="copy" data-action="copy-selected" onClick={() => copy(rows.filter((r) => selectedIds.has(r.id)))}>{t('logs.copySelected')}</Btn>
        </BatchBar>
      )}

      <div className="audit-summary" aria-live="polite">
        <span>{firstRead ? '' : t('logs.matched', { count: matched })}</span>
        {result && <span>{t('logs.errorCount', { count: fmt((levels.ERROR || 0) + (levels.CRITICAL || 0)) })}</span>}
        {result && <span>{t('logs.warningCount', { count: fmt(levels.WARNING || 0) })}</span>}
        {result && <span>{t('logs.componentCount', { count: fmt((result.components || []).length) })}</span>}
        {follow && <span role="status">{t('logs.following')}</span>}
      </div>

      <DataTable kind="audit" scrollId="logs-scroll" recordsId="logs-records" label={t('logs.regionLabel')} caption={t('logs.caption')}
        columns={columns} rows={firstRead ? [] : rows} rowKey={(l) => l.id} rowLabel={(l) => `${l.ts || ''} ${l.message || ''}`.trim()}
        loading={firstRead} empty={empty} card={card} selection={selection} sort={sort} onSort={onSort}
        footer={result && <TableFooter range={t('logs.range', { count: rows.length })} note={footNote} />} />
    </Zone>
  )
}
