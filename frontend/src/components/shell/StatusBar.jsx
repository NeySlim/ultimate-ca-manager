/**
 * Bottom bar: what /health reports (version, service state, HA node and cluster) in one line,
 * the live connection, the pending approvals (read:approvals) and the shortcuts (search,
 * close the inspector). Nothing is shown for a field the API omits.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ArrowsClockwise, Check, CheckCircle, Warning } from '@phosphor-icons/react'
import { WebSocketIndicator } from '../WebSocketIndicator'
import { approvalsService } from '../../services/approvals.service'
import { haState, useHealth } from './health'

const APPROVALS_POLL_MS = 60000

/** The cluster in a few words, as the mockup's indicator: all current, nodes late, or maintenance. */
function haSummary(ha, t) {
  if (ha.maintenance) return ['warn', ArrowsClockwise, t('shell.haMaintenanceShort')]
  if (ha.stale > 0) return ['warn', Warning, t('shell.haLate', { count: ha.stale })]
  if (ha.nodes !== null) return ['good', Check, t('shell.haNodes', { count: ha.nodes })]
  return null
}

/** Pending approvals, null while unknown; read again on a data change and once a minute. */
function usePendingApprovals(enabled) {
  const [pending, setPending] = useState(null)
  useEffect(() => {
    if (!enabled) return undefined
    let alive = true
    const load = () => approvalsService.getStats()
      .then(res => { const n = Number((res?.data ?? res)?.pending); if (alive && Number.isFinite(n)) setPending(n) })
      .catch(() => {})
    load()
    const timer = setInterval(load, APPROVALS_POLL_MS)
    window.addEventListener('ucm:data-changed', load)
    return () => { alive = false; clearInterval(timer); window.removeEventListener('ucm:data-changed', load) }
  }, [enabled])
  return enabled ? pending : null
}

/** onShowNodes: opens the node list; omitted (no read:settings), the indicator is plain text. */
export function StatusBar({ onShowNodes, can }) {
  const { t } = useTranslation()
  const health = useHealth()
  const pending = usePendingApprovals(!!can?.hasPermission?.('read:approvals'))

  let tone = 'muted'
  let text = ''
  if (health === false) { tone = 'bad'; text = t('shell.statusUnreachable') }
  else if (health) {
    tone = health.safe_mode ? 'warn' : 'good'
    text = health.safe_mode ? t('shell.statusSafeMode') : t('shell.statusRunning')
  }
  // One sentence, as the mockup's "UCM 2.253 · SQLite · Simulation locale"
  const line = [health?.version && t('shell.version', { version: health.version }), text].filter(Boolean).join(' · ')

  const ha = haState(health)
  const summary = ha && haSummary(ha, t)

  const indicator = summary && (() => {
    const [haTone, Icon, label] = summary
    const inner = <><Icon size={14} aria-hidden="true" /><span>{label}</span></>
    return onShowNodes ? (
      <button type="button" className={`shell-ha-link is-${haTone}`} aria-haspopup="dialog"
        aria-label={t('shell.haIndicatorLabel', { state: label })} onClick={onShowNodes}>
        {inner}
      </button>
    ) : <span className={`shell-ha-link is-${haTone}`}>{inner}</span>
  })()

  return (
    <footer className="shell-statusbar">
      <span className="shell-status-live">
        <span className="shell-status-text" role="status">
          <i className={`shell-dot is-${tone}`} aria-hidden="true" />
          {line && <span>{line}</span>}
        </span>
        {/* The live connection, at the most discreet place: an icon after the service state */}
        <WebSocketIndicator className="shell-ws" />
      </span>
      {pending !== null && (
        <Link to="/approvals" className="shell-approvals-link" data-module="approvals">
          <CheckCircle size={14} aria-hidden="true" />
          {pending > 0 ? t('shell.approvalsPending', { count: pending }) : t('shell.approvalsNone')}
        </Link>
      )}
      {ha && (
        <span className="shell-status-ha">
          {indicator}
          {ha.node && <span>{t('shell.haNode', { node: ha.node })}</span>}
          {ha.leader === true && <span>{t('shell.haLeader')}</span>}
          {ha.leader === false && <span>{t('shell.haFollower')}</span>}
        </span>
      )}
      <span className="shell-status-shortcut">
        <kbd>Ctrl K</kbd> {t('common.search')}
        <span className="shell-status-escape"><kbd>{t('shell.escapeKey')}</kbd> {t('inspector.close')}</span>
      </span>
    </footer>
  )
}
