/**
 * Shared frame of the overview cards: one fetch per card, and the mockup's card() around its
 * body, with the states the product reads separately (skeleton, error, missing right, empty).
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bar, Card, Icon, LoadCause, LoadError, skWidth } from '../atelier'
import { ConnectionState, useWebSocket } from '../../hooks/useWebSocket'
import { usePermission } from '../../hooks/usePermission'
import { REFRESH_EVENT } from '../../lib/overviewRefresh'
import { ChartTable, EmptyLine } from './viz'

/**
 * What the page gives its cards: `share(key, run)` (one request for two readers), `hide(id)`,
 * `customize(id)`, `showQueue(group)`, `notify` (toasts and prompts). Null for a card rendered alone.
 */
export const OverviewContext = createContext(null)

/** A mid-dot between two parts of a line, glued to the part before it: a wrapped line never starts with it. */
export const SEP = '\u00a0· '
/** A sign, figure and unit that never part on a narrow line (« − 33 % »). */
export const NB = '\u00a0'

/** A figure from the API response; anything but a finite number reads as a dash. */
export function num(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : '–'
}

// Events inside this window cost one reload; the only polling is while the live link is down
const COALESCE_MS = 2000
const OFFLINE_POLL_MS = 60000

/**
 * {status: 'loading'|'ready'|'error'|'forbidden', data, error, reload}. After the first load the
 * card reloads in the background (the figures stay on screen) when one of `watch` (resources of
 * the `ucm:data-changed` bus) changes, when the live link comes back, and when the tab returns.
 */
export function useCardData(fetcher, watch = [], shareKey = null) {
  const [state, setState] = useState({ status: 'loading', data: null })
  const seq = useRef(0)
  const page = useContext(OverviewContext)
  // The latest render's fetcher and page: a card whose request depends on its state reloads with it
  const latest = useRef({})
  latest.current = { fetcher, share: shareKey && page?.share ? (run) => page.share(shareKey, run) : null }
  const load = useCallback(async (quiet = false) => {
    const mine = ++seq.current
    if (!quiet) setState((s) => ({ status: 'loading', data: s.data }))
    try {
      const run = () => latest.current.fetcher()
      const res = await (latest.current.share ? latest.current.share(run) : run())
      if (mine === seq.current) setState({ status: 'ready', data: res?.data ?? null, meta: res?.meta ?? null })
    } catch (error) {
      // A background reload that fails leaves the figures shown; with none yet, the card says the error
      if (mine !== seq.current) return
      const failed = { status: error?.status === 403 ? 'forbidden' : 'error', data: null, error }
      setState((s) => (quiet && s.status === 'ready' ? s : failed))
    }
  }, [])
  useEffect(() => { load(); return () => { seq.current += 1 } }, [load])

  const timer = useRef(null)
  const schedule = useCallback(() => {
    if (timer.current) return
    timer.current = setTimeout(() => { timer.current = null; load(true) }, COALESCE_MS)
  }, [load])
  const watched = watch.join(',')
  useEffect(() => {
    const onData = (e) => { if (watched.split(',').includes(e.detail?.type)) schedule() }
    const onShow = () => { if (document.visibilityState === 'visible') schedule() }
    const onRefresh = () => { clearTimeout(timer.current); timer.current = null; load(true) }
    window.addEventListener('ucm:data-changed', onData)
    window.addEventListener(REFRESH_EVENT, onRefresh)
    document.addEventListener('visibilitychange', onShow)
    return () => {
      window.removeEventListener('ucm:data-changed', onData)
      window.removeEventListener(REFRESH_EVENT, onRefresh)
      document.removeEventListener('visibilitychange', onShow)
      clearTimeout(timer.current)
      timer.current = null
    }
  }, [watched, schedule, load])

  const { connectionState } = useWebSocket()
  const lostLink = useRef(false)
  // The link counts as lost only once it was up: the provider starts disconnected
  const seen = useRef(connectionState === ConnectionState.CONNECTED)
  const down = connectionState === ConnectionState.DISCONNECTED || connectionState === ConnectionState.ERROR
  useEffect(() => {
    if (connectionState === ConnectionState.CONNECTED) {
      if (lostLink.current) schedule()
      lostLink.current = false
      seen.current = true
    } else if (connectionState !== ConnectionState.CONNECTING && seen.current) {
      lostLink.current = true
    }
  }, [connectionState, schedule])
  useEffect(() => {
    if (!down) return undefined
    const id = setInterval(schedule, OFFLINE_POLL_MS)
    return () => clearInterval(id)
  }, [down, schedule])

  return { ...state, reload: () => load(), refresh: () => load(true) }
}

/**
 * A card's requests side by side: one that fails leaves what the others gave, listed in
 * `missing`; when what is left shows nothing (`usable` false), the first failure is the card's.
 */
export async function settle(parts, usable) {
  const names = Object.keys(parts)
  // A part that throws before its promise is one failed part, not the whole card
  const results = await Promise.allSettled(names.map((name) => Promise.resolve().then(() => parts[name]())))
  const got = {}
  const missing = []
  const errors = []
  results.forEach((r, i) => {
    if (r.status === 'fulfilled') got[names[i]] = r.value
    else { missing.push({ name: names[i], forbidden: r.reason?.status === 403 }); errors.push(r.reason) }
  })
  if (errors.length > 0 && !usable(got)) throw errors[0]
  return { got, missing }
}

/** The interface language, for the dates and delays the browser writes. */
export function useLang() {
  const { i18n } = useTranslation()
  return i18n?.language || 'en'
}

/** The mockup's dashSkeleton() card: its title, a thin line, five bars, at its usual height. */
export function CardSkeleton({ id, title }) {
  const { t } = useTranslation()
  return (
    <section className={`panel dash-card card-${id} sk-card`} id={`card-${id}`} data-card={id} aria-labelledby={`sk-${id}-title`} aria-busy="true">
      <header className="panel-heading">
        <div><h2 id={`sk-${id}-title`}>{title}</h2><Bar width="55%" kind="thin" /></div>
      </header>
      <p className="sr-only" role="status">{t('overview.state.loading')}</p>
      <div className="panel-content sk-body" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => <Bar key={i} width={skWidth(i, 40, 55)} />)}
      </div>
    </section>
  )
}

/** A card with nothing to show: the mockup's queue-empty block (icon, title, sentence). */
export function CardEmpty({ id, icon = 'check', title, text, children }) {
  return (
    <div className="queue-empty" id={id}>
      <Icon name={icon} />
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {children}
    </div>
  )
}

/**
 * The mockup's card() for one overview card: `state` from useCardData; `route` the request the
 * card reads, named by its load error; `empty` (a node, or true for the common one-line state)
 * replaces the body; `missing` lists the parts of the card that did not load; `table` (a function
 * giving [{caption, columns, rows}]) adds the table view of its figures to the card's menu.
 */
export function OverviewCard({ id, count, sub, tools, state, route, empty, missing, table, children }) {
  const { t } = useTranslation()
  const page = useContext(OverviewContext)
  const { hasPermission } = usePermission()
  const [asTable, setAsTable] = useState(false)
  const title = t(`overview.cards.${id}`)
  if (state.status === 'loading') return <CardSkeleton id={id} title={title} />
  const ready = state.status === 'ready'
  let body
  if (state.status === 'forbidden') {
    body = <CardEmpty icon="lock" title={t('overview.state.forbiddenTitle')} text={t('overview.state.forbidden')} />
  } else if (state.status === 'error') {
    const error = { status: state.error?.status, request: state.error?.request || route, message: state.error?.message }
    body = (
      <div className="panel-content">
        <LoadError id={`card-${id}`} title={t('overview.state.errorTitle', { name: title })}
          cause={<LoadCause error={error} fallback={t('overview.state.error')} />} onRetry={state.reload}
          journal={hasPermission('read:audit') ? '/audit' : undefined} />
      </div>
    )
  } else if (empty) {
    body = empty === true ? <div className="panel-content"><EmptyLine text={t('overview.state.empty')} /></div> : empty
  } else if (asTable && table) {
    body = <ChartTable tables={table()} filename={`ucm-${id}`} />
  } else {
    body = children
  }
  const tableable = ready && !empty && Boolean(table)
  const toggle = () => {
    setAsTable((v) => !v)
    requestAnimationFrame(() => document.getElementById(`card-${id}-title`)?.focus())
  }
  const note = ready && missing?.length > 0 && (
    <div className="panel-content">
      <p role="note" className="notice warn">
        <Icon name="warning" />
        <span>{t(missing.some((m) => m.forbidden) ? 'overview.state.partialForbidden' : 'overview.state.partial')}</span>
      </p>
    </div>
  )
  return (
    <Card id={id} title={title} count={ready ? count : undefined} sub={ready && !empty ? sub : undefined}
      tools={ready ? tools : undefined}
      onHide={page?.hide ? () => page.hide(id) : undefined}
      onCustomize={page?.customize ? () => page.customize(id) : undefined}
      onTable={tableable ? toggle : undefined} tableShown={tableable && asTable}>
      {note}
      {body}
    </Card>
  )
}

/** A lead (a gap, a pill) kept on the line of the text's first word: it never ends a line alone. */
export function KeepWith({ lead, text }) {
  const cut = text.indexOf(' ')
  return <><span className="keep-with">{lead}{cut < 0 ? text : text.slice(0, cut)}</span>{cut < 0 ? '' : text.slice(cut)}</>
}
