/**
 * Discovery: the mockup's discovery module, a simplePage() list of analyses (Plage, Trouvés,
 * Dernière analyse, État) with its one-object dock, on the server's scan profiles and their last
 * run. The certificates found and the run history are the product's further views of the same
 * page, with the scans, export, DNS resolution and removals the server allows (admin:system to
 * scan, delete:certificates to remove a found certificate).
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Zone, Btn, Icon, PageHead, Toolbar, SearchField, FilterSelect, ListView, LoadError, LoadCause, EmptyBlock, NoMatch,
  useClientList, useSortParam,
} from '../components/atelier'
import { discoveryService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useWebSocket } from '../hooks'
import { useDockParam, asId } from '../components/atelier/useDockParam'
import { formatDate, downloadBlob } from '../lib/utils'
import { ScanDialog, RemoveDialog } from './discovery/DiscoveryDialogs'
import {
  ScanDock, RunDock, FoundDock, FoundActions, ScanPill, RunPill, FoundPill,
} from './discovery/DiscoveryDocks'
import { lastRuns, scanState, runState, SCAN_TONES, RUN_TONES, durationLabel, cnOf, useScanFacts, runTitle, foundTitle } from './discovery/discoveryModel'

const VIEWS = ['profiles', 'discovered', 'history']
const DISCOVERY_SECTIONS = ['overview', 'runs']
const VIEW_ICONS = { profiles: 'radar', discovered: 'cert', history: 'clock' }
const pageOf = (res) => {
  const data = res?.data ?? res
  return Array.isArray(data) ? { items: data, total: data.length } : { items: data?.items ?? [], total: data?.total ?? data?.items?.length ?? 0 }
}

// Each view's default sort (T4), kept in the address; a change of view drops it
const BY_NAME = { key: 'name', asc: true }
const LATEST_FIRST = { key: 'started', asc: false }
const EXPIRY_FIRST = { key: 'expires', asc: true }
const SCAN_SORT_KEYS = ['name', 'range', 'found', 'last', 'state']
const RUN_SORT_KEYS = ['name', 'started', 'found', 'targets', 'duration', 'state']
// The certificates found are paged by the server: each column's key there
const FOUND_SORT = { name: 'subject', host: 'target', issuer: 'issuer', expires: 'not_after', state: 'status' }

export default function DiscoveryPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { canDelete, hasPermission } = usePermission()
  // Scans, analyses, the DNS resolution and the purge ask for admin:system on the server
  const canScan = hasPermission('admin:system')
  const canRemove = canDelete('certificates')
  const { subscribe } = useWebSocket({ showToasts: false })
  const [searchParams, setSearchParams] = useSearchParams()
  const facts = useScanFacts()

  const view = VIEWS.includes(searchParams.get('tab')) ? searchParams.get('tab') : 'profiles'
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [profiles, setProfiles] = useState([])
  const [runs, setRuns] = useState([])
  const [found, setFound] = useState({ items: [], total: 0 })
  const [stats, setStats] = useState({ total: 0, managed: 0, unmanaged: 0, errors: 0 })
  const [scanning, setScanning] = useState(false)
  const [progress, setProgress] = useState(null)
  // The object open in the view's dock and its section live in the URL (`item`, `section`)
  const discDock = useDockParam({ sections: DISCOVERY_SECTIONS })
  const opened = discDock.item == null ? null : { view, id: asId(discDock.item) }
  const setOpened = (o) => (o ? discDock.open(o.id) : discDock.close())
  const { section, setSection } = discDock
  const [dialog, setDialog] = useState(null)
  const [busy, setBusy] = useState(false)

  const [query, setQuery] = useState('')
  const [scanView, setScanView] = useState('')
  const [foundView, setFoundView] = useState('')
  const [runView, setRunView] = useState('')
  const [profileFilter, setProfileFilter] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const scanSort = useSortParam(BY_NAME, SCAN_SORT_KEYS)
  const runSort = useSortParam(LATEST_FIRST, RUN_SORT_KEYS)
  const foundSort = useSortParam(EXPIRY_FIRST, Object.keys(FOUND_SORT))
  // A new sort of the server's pages starts from the first one, whether a header or Back set it
  const foundOrder = `${foundSort.sort.key}:${foundSort.sort.asc}`
  const [foundMark, setFoundMark] = useState(foundOrder)
  if (foundMark !== foundOrder) { setFoundMark(foundOrder); setPage(1) }

  const loadProfiles = useCallback(async () => {
    const [p, r] = await Promise.all([discoveryService.getProfiles(), discoveryService.getRuns({ limit: 200 })])
    setProfiles(pageOf(p).items)
    setRuns(pageOf(r).items)
  }, [])
  const loadFound = useCallback(async () => {
    const params = {
      limit: perPage, offset: (page - 1) * perPage, search: query.trim() || undefined,
      sort_by: FOUND_SORT[foundSort.sort.key], sort_order: foundSort.sort.asc ? 'asc' : 'desc',
    }
    if (foundView) params.status = [foundView]
    if (profileFilter) params.profile_id = profileFilter
    const [res, st] = await Promise.all([discoveryService.getAll(params), discoveryService.getStats(profileFilter || null).catch(() => null)])
    setFound(pageOf(res))
    if (st) setStats(st.data ?? st)
  }, [page, perPage, query, foundView, profileFilter, foundSort.sort])
  const loadAll = useCallback(async () => {
    setLoadError(null)
    try {
      await Promise.all([loadProfiles(), loadFound()])
    } catch (err) {
      setLoadError(err || {})
    } finally {
      setLoading(false)
    }
  }, [loadProfiles, loadFound])
  useEffect(() => { loadAll() }, [loadAll])
  const reload = useRef(loadAll)
  reload.current = loadAll

  useEffect(() => {
    const off = [
      subscribe('discovery.scan_started', () => { setScanning(true); setProgress({ scanned: 0, total: 0, found: 0 }) }),
      subscribe('discovery.scan_progress', (d) => setProgress((p) => ({
        scanned: d.scanned ?? p?.scanned ?? 0, total: d.total ?? p?.total ?? 0, found: d.found ?? p?.found ?? 0,
      }))),
      subscribe('discovery.scan_complete', () => { setScanning(false); setProgress(null); reload.current() }),
    ]
    return () => off.forEach((u) => u?.())
  }, [subscribe])

  // The new view's URL carries no object: its dock closes
  const goView = (next) => {
    setQuery('')
    setPage(1)
    setSearchParams(next === 'profiles' ? {} : { tab: next })
  }
  const act = async (fn, okMsg, failMsg) => {
    try {
      setBusy(true)
      const out = await fn()
      if (okMsg) showSuccess(typeof okMsg === 'function' ? okMsg(out) : okMsg)
      return true
    } catch (err) {
      showError(err?.message || failMsg)
      return false
    } finally {
      setBusy(false)
    }
  }
  const startScan = async (call) => {
    setScanning(true)
    try { await call() } catch (err) { showError(err?.message || t('discovery.scanFailed')); setScanning(false) }
  }

  const saveProfile = async (payload) => {
    const editing = dialog?.profile
    const ok = await act(() => (editing ? discoveryService.updateProfile(editing.id, payload) : discoveryService.createProfile(payload)),
      editing ? t('discovery.profileUpdated') : t('discovery.profileCreated'), t('messages.errors.saveFailed'))
    if (ok) { setDialog(null); loadProfiles().catch(() => {}) }
  }
  const quickScan = (payload) => { setDialog(null); startScan(() => discoveryService.scan(payload)) }
  const retry = (c) => startScan(() => discoveryService.scan({ targets: [`${c.target}:${c.port}`], ports: [c.port], timeout: 10 }))
  const retryErrors = () => {
    const targets = found.items.filter((c) => c.status === 'error').map((c) => `${c.target}:${c.port}`)
    if (targets.length) startScan(() => discoveryService.scan({ targets, timeout: 10 }))
  }
  const remove = async () => {
    const d = dialog
    const ok = await act(() => (d.kind === 'removeProfile' ? discoveryService.deleteProfile(d.item.id)
      : d.kind === 'removeFound' ? discoveryService.delete(d.item.id) : discoveryService.deleteAll()),
    d.kind === 'removeProfile' ? t('discovery.profileDeleted') : d.kind === 'removeFound' ? t('messages.success.delete') : t('discovery.found.purged'),
    t('messages.errors.deleteFailed'))
    if (!ok) return
    setDialog(null)
    if (d.kind !== 'removeAll') setOpened(null)
    loadAll()
  }
  const exportFound = () => act(async () => {
    // The file holds what the list holds: the same search, state and analysis
    const params = { search: query.trim() || undefined }
    if (foundView) params.status = [foundView]
    if (profileFilter) params.profile_id = profileFilter
    downloadBlob(await discoveryService.export('csv', params), 'discovered_certificates.csv')
  }, t('discovery.exportSuccess'), t('discovery.exportFailed'))
  const resolveDns = () => act(async () => {
    const res = await discoveryService.bulkResolveDns()
    loadFound().catch(() => {})
    return res?.data ?? res
  }, (d) => t('discovery.bulkDnsSuccess', { updated: d?.updated ?? 0, total: d?.total ?? 0 }), t('discovery.scanFailed'))

  // ── Analyses: a profile and its last run ──
  const last = useMemo(() => lastRuns(runs), [runs])
  const stateOfScan = useCallback((p) => scanState(p, last.get(p.id)), [last])
  const q = query.trim().toLowerCase()
  const scanSearched = useMemo(() => profiles
    .filter((p) => !q || [p.name, p.description, ...(Array.isArray(p.targets) ? p.targets : [])].some((v) => String(v || '').toLowerCase().includes(q))), [profiles, q])
  const scanPresent = Object.keys(SCAN_TONES).filter((s) => profiles.some((p) => stateOfScan(p) === s))
  const scanActive = scanPresent.includes(scanView) ? scanView : ''
  const scanRows = scanSearched.filter((p) => !scanActive || stateOfScan(p) === scanActive)
  const scanStates = Object.keys(SCAN_TONES)
  const scanList = useClientList(scanRows, {
    sortParam: scanSort,
    resetKey: `${q}|${scanActive}`,
    sorts: {
      name: (p) => p.name, range: (p) => facts.range(p),
      found: (p) => { const run = last.get(p.id); return run?.status === 'completed' ? run.certs_found ?? 0 : null },
      last: (p) => { const at = last.get(p.id)?.started_at || p.last_scan_at; return at ? Date.parse(at) : null },
      state: (p) => scanStates.indexOf(stateOfScan(p)),
    },
  })

  // ── Runs ──
  const runSearched = useMemo(() => runs
    .filter((r) => (!profileFilter || String(r.scan_profile_id) === String(profileFilter))
      && (!q || String(runTitle(r, t)).toLowerCase().includes(q))), [runs, profileFilter, q, t])
  const runPresent = Object.keys(RUN_TONES).filter((s) => runs.some((r) => runState(r) === s))
  const runActive = runPresent.includes(runView) ? runView : ''
  const runRows = runSearched.filter((r) => !runActive || runState(r) === runActive)
  // The page reads the last 200 runs (the API has no search nor state filter): sorted and paged here
  const runStates = Object.keys(RUN_TONES)
  const runList = useClientList(runRows, {
    sortParam: runSort,
    resetKey: `${q}|${runActive}|${profileFilter}`,
    sorts: {
      name: (r) => runTitle(r, t), started: (r) => r.started_at && Date.parse(r.started_at), found: (r) => r.certs_found ?? 0,
      targets: (r) => r.targets_scanned, duration: (r) => r.duration_seconds, state: (r) => runStates.indexOf(runState(r)),
    },
  })

  const openedItem = opened && (opened.view === 'profiles' ? profiles : opened.view === 'history' ? runs : found.items).find((x) => x.id === opened.id)
  const open = () => (x) => discDock.open(x.id)
  const openedId = openedItem && opened.view === view ? opened.id : null

  const dock = openedItem && opened.view === view && (
    view === 'profiles' ? (
      <ScanDock profile={openedItem} run={last.get(openedItem.id)} runs={runs} state={stateOfScan(openedItem)} section={section} onSection={setSection}
        onClose={() => setOpened(null)}
        actions={canScan && <>
          <Btn icon="radar" id="scan-run" write disabled={scanning || undefined} onClick={() => startScan(() => discoveryService.scanProfile(openedItem.id))}>{t('discovery.scans.runNow')}</Btn>
          <Btn icon="settings" id="scan-edit" write onClick={() => setDialog({ kind: 'profile', profile: openedItem, from: 'scan-edit' })}>{t('common.edit')}…</Btn>
          <Btn tone="danger" icon="close" id="scan-remove" onClick={() => setDialog({ kind: 'removeProfile', item: openedItem, from: 'scan-remove' })}>{t('common.delete')}…</Btn>
        </>} />
    ) : view === 'history' ? (
      <RunDock run={openedItem} onClose={() => setOpened(null)} />
    ) : (
      <FoundDock cert={openedItem} onClose={() => setOpened(null)}
        actions={<FoundActions cert={openedItem} canScan={canScan} canRemove={canRemove} busy={scanning}
          onRetry={retry} onRemove={(c) => setDialog({ kind: 'removeFound', item: c, from: 'found-remove' })} />} />
    )
  )

  // The head already holds the primary action: the empty block repeats it as a secondary button
  const createScan = canScan ? { label: t('discovery.scans.create'), icon: 'plus', onClick: () => setDialog({ kind: 'profile', profile: null, from: 'scan-new' }) } : undefined
  const quick = canScan ? { label: t('discovery.quickScanAsk'), icon: 'radar', onClick: () => setDialog({ kind: 'quick', from: 'scan-quick' }) } : undefined
  const others = VIEWS.filter((v) => v !== view)
  const switches = others.map((v) => (
    <Btn key={v} icon={VIEW_ICONS[v]} data-view={v} onClick={() => goView(v)}>{t(`discovery.views.${v}`)}</Btn>
  ))
  const profileOptions = [{ value: '', label: t('discovery.allProfiles') }, ...profiles.map((p) => ({ value: String(p.id), label: p.name }))]
  const search = (id, label) => <SearchField id={id} name="q" label={label} placeholder={label} value={query} onChange={(v) => { setQuery(v); setPage(1) }} />
  const resetFilters = () => { setQuery(''); setScanView(''); setFoundView(''); setRunView(''); setProfileFilter(''); setPage(1) }
  const noMatch = <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={resetFilters} />
  const error = loadError && (
    <LoadError id="discovery" title={t('discovery.errors.loadFailed')} onRetry={() => { setLoading(true); loadAll() }} journal={hasPermission('read:audit') && '/audit'}
      cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/discovery', message: loadError.message }} />} />
  )
  const progressNote = scanning && (
    <div className="notice" role="status">
      <Icon name="radar" />
      <span>{progress?.total > 0 ? t('discovery.scans.progress', { scanned: progress.scanned, total: progress.total, found: progress.found }) : t('discovery.scanning')}</span>
    </div>
  )
  const foundPages = Math.max(1, Math.ceil(found.total / perPage))

  const head = {
    profiles: { title: t('shell.moduleLabel.discovery'), total: t('discovery.scans.unit', { count: profiles.length }), intent: t('shell.moduleDesc.discovery') },
    discovered: { title: t('discovery.views.discovered'), total: t('discovery.found.unit', { count: stats.total ?? found.total }), intent: t('discovery.found.intent') },
    history: { title: t('discovery.views.history'), total: t('discovery.runs.unit', { count: runs.length }), intent: t('discovery.runs.intent') },
  }[view]

  return (
    <Zone dock={dock} after={<>
      {(dialog?.kind === 'profile' || dialog?.kind === 'quick') && (
        <ScanDialog quick={dialog.kind === 'quick'} profile={dialog.profile} busy={busy} returnTo={dialog.from}
          onSubmit={dialog.kind === 'quick' ? quickScan : saveProfile} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind?.startsWith('remove') && (
        <RemoveDialog busy={busy} onConfirm={remove} onClose={() => setDialog(null)} returnTo={dialog.from}
          title={dialog.kind === 'removeProfile' ? t('discovery.scans.remove') : dialog.kind === 'removeFound' ? t('discovery.found.remove') : t('discovery.deleteAll')}
          subtitle={dialog.item && (dialog.kind === 'removeProfile' ? dialog.item.name : foundTitle(dialog.item, t))}
          text={dialog.kind === 'removeProfile' ? t('discovery.scans.removeText') : dialog.kind === 'removeFound' ? t('discovery.deleteDiscoveredConfirm') : t('discovery.deleteAllConfirm')}
          confirm={dialog.kind === 'removeAll' ? t('discovery.deleteAll') : t('common.delete')} />
      )}
    </>}>
      <PageHead title={head.title} total={head.total} intent={head.intent}
        actions={<>
          {switches}
          {quick && <Btn icon="radar" id="scan-quick" disabled={scanning || undefined} onClick={quick.onClick}>{quick.label}</Btn>}
          {view === 'profiles' && createScan && <Btn tone="primary" icon="plus" id="scan-new" onClick={createScan.onClick}>{createScan.label}</Btn>}
        </>} />
      {progressNote}

      {view === 'profiles' && (
        <ListView label={t('shell.moduleLabel.discovery')} caption={t('discovery.scans.caption')} icon="radar" list={scanList} nameSort="name" loading={loading}
          filters={{ views: [{ id: '', label: t('common.all'), count: scanSearched.length },
            ...scanPresent.map((s) => ({ id: s, label: t(`discovery.scans.state.${s}`), count: scanSearched.filter((p) => stateOfScan(p) === s).length }))],
          active: scanActive, onChange: setScanView, label: t('discovery.filterByState') }}
          toolbar={<Toolbar>{search('scan-search', t('discovery.searchProfiles'))}</Toolbar>}
          title={(p) => p.name} status={(p) => <ScanPill state={stateOfScan(p)} />} openedId={openedId} onOpen={open('profiles')}
          columns={[
            { id: 'range', label: t('discovery.form.range'), cell: (p) => facts.range(p), kind: 'text', priority: 4, grow: true, sort: 'range' },
            { id: 'found', label: t('discovery.scans.found'), labelFull: t('discovery.certsFound'), cell: (p) => facts.found(p, last.get(p.id)), kind: 'fit', priority: 3, labelled: true, sort: 'found' },
            { id: 'last', label: t('discovery.scans.last'), cell: (p) => facts.last(p, last.get(p.id)), kind: 'fit', priority: 2, labelled: true, sort: 'last' },
            { status: true, sort: 'state' },
          ]}
          error={error}
          empty={q || scanActive ? noMatch : (
            <EmptyBlock id="discovery" icon="radar" title={t('discovery.scans.empty')} text={t('discovery.scans.emptyText')} action={createScan} />
          )}
          footer={{ range: t('discovery.scans.range', scanList.counts(profiles.length)) }} />
      )}

      {view === 'discovered' && (
        <ListView label={t('discovery.views.discovered')} caption={t('discovery.found.caption')} icon="cert" rows={found.items} loading={loading}
          sort={foundSort.sort} onSort={foundSort.onSort} nameSort="name"
          filters={{ views: [
            { id: '', label: t('common.all'), count: stats.total ?? found.total },
            { id: 'managed', label: t('discovery.found.state.managed'), count: stats.managed ?? 0 },
            { id: 'unmanaged', label: t('discovery.found.state.unmanaged'), count: stats.unmanaged ?? 0 },
            ...(stats.errors > 0 ? [{ id: 'error', label: t('discovery.found.state.error'), count: stats.errors, warn: true }] : []),
          ], active: foundView, onChange: (v) => { setFoundView(v); setPage(1) }, label: t('discovery.filterByState') }}
          toolbar={(
            <Toolbar>
              {search('found-search', t('discovery.searchDiscovered'))}
              <FilterSelect id="found-profile" label={t('discovery.filterByProfile')} value={profileFilter} onChange={(v) => { setProfileFilter(v); setPage(1) }} options={profileOptions} />
              <Btn icon="download" id="found-export" disabled={busy || !found.total || undefined} onClick={exportFound}>{t('common.export')}</Btn>
              {canScan && found.total > 0 && <Btn icon="globe" id="found-dns" write disabled={busy || undefined} onClick={resolveDns}>{t('discovery.bulkResolveDns')}</Btn>}
              {canScan && stats.errors > 0 && <Btn icon="refresh" id="found-retry-all" write disabled={scanning || undefined} onClick={retryErrors}>{t('discovery.retryAllErrors')}</Btn>}
              {canScan && found.total > 0 && <Btn tone="danger" icon="close" id="found-purge" onClick={() => setDialog({ kind: 'removeAll', from: 'found-purge' })}>{t('discovery.deleteAll')}…</Btn>}
            </Toolbar>
          )}
          title={(c) => foundTitle(c, t)} status={(c) => <FoundPill cert={c} />} openedId={openedId} onOpen={open('discovered')}
          rowActions={(c) => [
            c.status === 'error' && canScan && { icon: 'refresh', label: t('discovery.retry'), write: true, onClick: retry },
            canRemove && { icon: 'block', label: t('common.delete'), onClick: (x) => setDialog({ kind: 'removeFound', item: x }) },
          ].filter(Boolean)}
          columns={[
            { id: 'host', label: t('discovery.host'), cell: (c) => <span className="mono">{c.target}:{c.port || 443}</span>, title: (c) => `${c.target}:${c.port || 443}`,
              kind: 'text', priority: 3, sort: 'host' },
            { id: 'issuer', label: t('common.issuer'), cell: (c) => (c.status === 'error' ? c.scan_error : cnOf(c.issuer) || c.issuer || '—'), kind: 'text', priority: 4, grow: true, muted: true, sort: 'issuer' },
            { id: 'expires', label: t('common.expires'), labelFull: t('table.fullExpires'), cell: (c) => (c.not_after ? formatDate(c.not_after) : '—'), kind: 'fit', priority: 2, labelled: true, sort: 'expires' },
            { status: true, sort: 'state' },
          ]}
          error={error}
          empty={query.trim() || foundView || profileFilter ? noMatch : (
            <EmptyBlock id="discovered" icon="cert" title={t('discovery.noDiscovered')} text={t('discovery.noResultsDesc')} action={quick} />
          )}
          footer={{
            range: t('discovery.found.range', { start: found.total ? (page - 1) * perPage + 1 : 0, end: Math.min(page * perPage, found.total), count: found.total }),
            pagination: foundPages > 1 || found.total > 10 ? { page, pages: foundPages, perPage, sizes: [10, 25, 50, 100], onPage: setPage, onPerPage: (n) => { setPerPage(n); setPage(1) } } : undefined,
          }} />
      )}

      {view === 'history' && (
        <ListView label={t('discovery.views.history')} caption={t('discovery.runs.caption')} icon="clock" list={runList} nameSort="name" loading={loading}
          filters={{ views: [{ id: '', label: t('common.all'), count: runSearched.length },
            ...runPresent.map((s) => ({ id: s, label: t(`discovery.runs.state.${s}`), count: runSearched.filter((r) => runState(r) === s).length }))],
          active: runActive, onChange: setRunView, label: t('discovery.filterByState') }}
          toolbar={(
            <Toolbar>
              {search('run-search', t('discovery.searchHistory'))}
              <FilterSelect id="run-profile" label={t('discovery.filterByProfile')} value={profileFilter} onChange={setProfileFilter} options={profileOptions} />
            </Toolbar>
          )}
          title={(r) => runTitle(r, t)} status={(r) => <RunPill run={r} />} openedId={openedId} onOpen={open('history')}
          columns={[
            { id: 'started', label: t('discovery.startedAt'), labelFull: t('table.fullStarted'), cell: (r) => (r.started_at ? formatDate(r.started_at, { time: true }) : '—'), kind: 'fit', priority: 2, labelled: true, sort: 'started' },
            { id: 'found', label: t('discovery.scans.found'), labelFull: t('discovery.certsFound'), cell: (r) => r.certs_found ?? 0, kind: 'number', priority: 3, sort: 'found' },
            { id: 'targets', label: t('discovery.runs.targets'), labelFull: t('discovery.targetsScanned'), cell: (r) => r.targets_scanned ?? '—', kind: 'number', priority: 3, sort: 'targets' },
            { id: 'duration', label: t('discovery.duration'), cell: (r) => durationLabel(r.duration_seconds) || '—', kind: 'fit', priority: 3, labelled: true, muted: true, sort: 'duration' },
            { status: true, sort: 'state' },
          ]}
          error={error}
          empty={q || runActive || profileFilter ? noMatch : <EmptyBlock id="history" icon="clock" title={t('discovery.noHistory')} text={t('discovery.noHistoryDesc')} />}
          footer={{ range: t('discovery.runs.range', runList.counts(runs.length)) }} />
      )}
      <p className="phone-only">{others.map((v) => (
        <Btn key={v} icon={VIEW_ICONS[v]} data-view={v} onClick={() => goView(v)}>{t(`discovery.views.${v}`)}</Btn>
      ))}{quick && <Btn icon="radar" disabled={scanning || undefined} onClick={quick.onClick}>{quick.label}</Btn>}</p>
    </Zone>
  )
}
