/**
 * Shared frame of the overview cards: one fetch, four states (loading, error,
 * missing permission, empty), and a number that is a dash when the API gave none.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  ArrowDown, ArrowUp, CheckCircle, DotsSixVertical, DotsThree, EyeSlash, SquaresFour, WarningCircle,
} from '@phosphor-icons/react'
import { ConnectionState, useWebSocket } from '../../hooks/useWebSocket'
import { REFRESH_EVENT } from '../../lib/overviewRefresh'
import './overview.css'

/**
 * What the page gives its cards: `share(key, run)` (one request for two readers), `grip(id)`,
 * `step(id, delta)`, `hide(id)`, `customize()`, `showQueue(group)`, `notify` (toasts and prompts).
 * Null for a card rendered alone.
 */
export const OverviewContext = createContext(null)

/** A figure from the API response; anything but a finite number reads as a dash. */
export function num(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : '–'
}

// Events inside this window cost one reload; the only polling is while the live link is down
const COALESCE_MS = 2000
const OFFLINE_POLL_MS = 60000

/**
 * {status: 'loading'|'ready'|'error'|'forbidden', data, reload}. After the first load the card
 * reloads in the background (the figures stay on screen) when one of `watch` (resources of the
 * `ucm:data-changed` bus) changes, when the live link comes back, and when the tab returns.
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
      const failed = { status: error?.status === 403 ? 'forbidden' : 'error', data: null }
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
  const results = await Promise.allSettled(names.map((name) => parts[name]()))
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

/** A state in words, with its icon; the tone only repeats it in colour. */
export function Pill({ tone, icon: Icon, children, className = '', ...rest }) {
  return (
    <span className={`ov-pill${tone ? ` is-${tone}` : ''}${className ? ` ${className}` : ''}`} {...rest}>
      {Icon && <Icon size={12} weight="bold" aria-hidden="true" />}
      <span>{children}</span>
    </span>
  )
}

function CardMenu({ id, title, page }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const root = useRef(null)
  const button = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => { if (!root.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])
  const onKeyDown = (e) => {
    if (open && e.key === 'Escape') { e.preventDefault(); setOpen(false); button.current?.focus() }
  }
  const run = (action) => () => { setOpen(false); action() }
  return (
    <div className="ov-menu-wrap" ref={root} onKeyDown={onKeyDown}>
      <button type="button" ref={button} className="ov-btn is-quiet is-icon ov-menu-btn" aria-expanded={open}
        aria-controls={`overview-${id}-menu`} aria-label={t('overview.layout.menu', { name: title })}
        title={t('overview.layout.menuTitle')} onClick={() => setOpen(!open)}>
        <DotsThree size={18} weight="bold" aria-hidden="true" />
      </button>
      {open && (
        <div className="ov-menu" id={`overview-${id}-menu`}>
          <button type="button" disabled={!page.canStep(id, -1)} onClick={run(() => page.step(id, -1))}>
            <ArrowUp size={15} aria-hidden="true" />{t('overview.layout.earlier')}
          </button>
          <button type="button" disabled={!page.canStep(id, 1)} onClick={run(() => page.step(id, 1))}>
            <ArrowDown size={15} aria-hidden="true" />{t('overview.layout.later')}
          </button>
          <button type="button" onClick={run(() => page.hide(id))}>
            <EyeSlash size={15} aria-hidden="true" />{t('overview.layout.hide')}
          </button>
          <button type="button" onClick={run(() => page.customize())}>
            <SquaresFour size={15} aria-hidden="true" />{t('overview.layout.customize')}
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * The common frame: title with its counter, a sentence under it, tools on the right, then one
 * of the four states or the card's body. Inside the page it also carries the grip and the menu.
 */
export function CardFrame({ id, title, count, sub, tools, state, empty, emptyHint, onRetry, children, missing }) {
  const { t } = useTranslation()
  const page = useContext(OverviewContext)
  const { status } = state
  const ready = status === 'ready'
  let body
  if (status === 'loading') {
    body = (
      <>
        <p role="status" className="ov-state">{t('overview.state.loading')}</p>
        <div className="ov-skeleton" aria-hidden="true"><span /><span /><span /></div>
      </>
    )
  } else if (status === 'forbidden') {
    body = <p className="ov-state">{t('overview.state.forbidden')}</p>
  } else if (status === 'error') {
    body = (
      <div role="alert" className="ov-state is-error">
        <WarningCircle size={16} aria-hidden="true" />
        <span>{t('overview.state.error')}</span>
        <button type="button" className="ov-btn" onClick={onRetry}>{t('overview.state.retry')}</button>
      </div>
    )
  } else if (empty) {
    body = (
      <div className="ov-state is-empty">
        <CheckCircle size={26} aria-hidden="true" />
        <p>{t('overview.state.empty')}</p>
        {emptyHint && <small>{emptyHint}</small>}
      </div>
    )
  } else {
    body = children
  }
  const note = ready && missing?.length > 0 && (
    <p role="note" className="ov-note">
      {t(missing.some((m) => m.forbidden) ? 'overview.state.partialForbidden' : 'overview.state.partial')}
    </p>
  )
  return (
    <section data-testid={`card-${id}`} id={`card-${id}`} aria-labelledby={`overview-${id}-title`}
      className={`ov-card ov-card-${id}`}>
      <header className="ov-card-head">
        {page?.grip && (
          <span role="button" tabIndex={0} className="ov-grip" aria-label={t('overview.layout.grip', { name: title })}
            title={t('overview.layout.gripHint')} {...page.grip(id)}>
            <DotsSixVertical size={16} weight="bold" aria-hidden="true" />
          </span>
        )}
        <div className="ov-card-titles">
          <h2 tabIndex={-1}>
            <span id={`overview-${id}-title`}>{title}</span>
            {ready && count !== undefined && <span className="ov-counter" data-testid={`${id}-total`}>{count}</span>}
          </h2>
          {ready && !empty && sub && <p>{sub}</p>}
        </div>
        <div className="ov-card-tools">
          {ready && tools}
          {page?.hide && <CardMenu id={id} title={title} page={page} />}
        </div>
      </header>
      {note}
      {body}
    </section>
  )
}

/** An in-app link when there is somewhere to go, the same content as plain text otherwise. */
export function MaybeLink({ to, className, children, ...rest }) {
  return to
    ? <Link to={to} className={className} {...rest}>{children}</Link>
    : <div className={className} {...rest}>{children}</div>
}
