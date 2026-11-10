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

export function CardFrame({ id, title, state, empty, onRetry, children, action }) {
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
