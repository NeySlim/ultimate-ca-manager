/**
 * Shared frame of the overview cards: one fetch, four states (loading, error,
 * missing permission, empty), and a number that is a dash when the API gave none.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

/** A figure from the API response; anything but a finite number reads as a dash. */
export function num(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : '–'
}

/** {status: 'loading'|'ready'|'error'|'forbidden', data, reload}. */
export function useCardData(fetcher) {
  const [state, setState] = useState({ status: 'loading', data: null })
  const seq = useRef(0)
  const load = useCallback(async () => {
    const mine = ++seq.current
    setState((s) => ({ status: 'loading', data: s.data }))
    try {
      const res = await fetcher()
      if (mine === seq.current) setState({ status: 'ready', data: res?.data ?? null, meta: res?.meta ?? null })
    } catch (error) {
      if (mine === seq.current) setState({ status: error?.status === 403 ? 'forbidden' : 'error', data: null })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => { load(); return () => { seq.current += 1 } }, [load])
  return { ...state, reload: load }
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

export function CardFrame({ id, title, state, empty, onRetry, children, action, missing }) {
  const { t } = useTranslation()
  const { status } = state
  let body
  if (status === 'loading') {
    body = <p role="status" className="text-sm text-text-secondary">{t('overview.state.loading')}</p>
  } else if (status === 'forbidden') {
    body = <p className="text-sm text-text-secondary">{t('overview.state.forbidden')}</p>
  } else if (status === 'error') {
    body = (
      <div role="alert" className="text-sm text-status-danger flex items-center gap-2">
        <span>{t('overview.state.error')}</span>
        <button type="button" className="underline" onClick={onRetry}>{t('overview.state.retry')}</button>
      </div>
    )
  } else if (empty) {
    body = <p className="text-sm text-text-secondary">{t('overview.state.empty')}</p>
  } else {
    body = children
  }
  if (status === 'ready' && missing?.length > 0) {
    const key = missing.some((m) => m.forbidden) ? 'overview.state.partialForbidden' : 'overview.state.partial'
    body = <>{<p role="note" className="text-xs text-status-warning">{t(key)}</p>}{body}</>
  }
  return (
    <section
      data-testid={`card-${id}`}
      aria-labelledby={`overview-${id}-title`}
      className="card-soft p-4 flex flex-col gap-3 min-w-0"
    >
      <header className="flex items-center justify-between gap-2">
        <h2 id={`overview-${id}-title`} className="text-sm font-semibold text-text-primary">{title}</h2>
        {status === 'ready' && action}
      </header>
      {body}
    </section>
  )
}

/** A counter that opens the list it counts, or plain text without a list filter. */
export function Counter({ label, count, to }) {
  const inner = (
    <>
      <span className="text-sm text-text-secondary">{label}</span>
      <span className="text-sm font-semibold text-text-primary tabular-nums">{num(count)}</span>
    </>
  )
  const cls = 'flex items-center justify-between gap-3 py-1'
  return to
    ? <Link to={to} className={`${cls} hover:text-accent-primary`}>{inner}</Link>
    : <div className={cls}>{inner}</div>
}
