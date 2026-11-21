/**
 * Bottom bar: only what /health reports (version, service state, HA node and
 * cluster) and the search shortcut. Nothing is shown for a field the API omits.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

const HEALTH_URL = '/api/v2/health'
const POLL_MS = 30000

export function StatusBar() {
  const { t } = useTranslation()
  // null until the first answer; false when the service did not answer
  const [health, setHealth] = useState(null)

  useEffect(() => {
    // A late answer must not write after unmount or after the next poll started
    const ctrl = new AbortController()
    const load = async () => {
      try {
        const res = await fetch(HEALTH_URL, { signal: ctrl.signal, cache: 'no-store' })
        if (!res.ok) throw new Error(String(res.status))
        const body = await res.json()
        if (!ctrl.signal.aborted) setHealth(body && typeof body === 'object' ? body : false)
      } catch {
        if (!ctrl.signal.aborted) setHealth(false)
      }
    }
    load()
    const timer = setInterval(load, POLL_MS)
    return () => { ctrl.abort(); clearInterval(timer) }
  }, [])

  let tone = 'muted'
  let text = ''
  if (health === false) { tone = 'bad'; text = t('shell.statusUnreachable') }
  else if (health) {
    tone = health.safe_mode ? 'warn' : 'good'
    text = health.safe_mode ? t('shell.statusSafeMode') : t('shell.statusRunning')
  }

  const cluster = health?.ha ? health.cluster : null
  const late = cluster?.stale || 0

  return (
    <footer className="shell-statusbar">
      <span className="shell-status-live" role="status">
        <i className={`shell-dot is-${tone}`} aria-hidden="true" />
        {health?.version && <span>{t('shell.version', { version: health.version })}</span>}
        {text && <span>{text}</span>}
      </span>
      {health?.ha && (
        <span className={`shell-status-ha${late ? ' is-warn' : ''}`}>
          {health.node_id && <span>{t('shell.haNode', { node: health.node_id })}</span>}
          {health.leader === true && <span>{t('shell.haLeader')}</span>}
          {health.leader === false && <span>{t('shell.haFollower')}</span>}
          {cluster && typeof cluster.nodes === 'number' && <span>{t('shell.haNodes', { count: cluster.nodes })}</span>}
          {late > 0 && <span>{t('shell.haLate', { count: late })}</span>}
        </span>
      )}
      <span className="shell-status-shortcut"><kbd>Ctrl K</kbd> {t('common.search')}</span>
    </footer>
  )
}
