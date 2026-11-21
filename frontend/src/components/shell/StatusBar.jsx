/**
 * Bottom bar, the mockup's footer.statusbar: what /health reports (version, service state, HA node and cluster) in one line,
 * the live connection, the pending approvals (read:approvals) and the shortcuts (search,
 * close the inspector). Nothing is shown for a field the API omits.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier/Icon'
import { WebSocketIndicator } from '../WebSocketIndicator'
import { approvalsService } from '../../services/approvals.service'
import { haState, useHealth } from './health'

const APPROVALS_POLL_MS = 60000

/** The cluster in a few words, the mockup's haIndicator(): all current, nodes late, or maintenance. */
function haSummary(ha, t) {
  if (ha.maintenance) return ['warn', 'refresh', t('shell.haMaintenanceShort')]
  if (ha.stale > 0) return ['warn', 'warning', t('shell.haLate', { count: ha.stale })]
  if (ha.nodes !== null) return ['good', 'check', t('shell.haNodes', { count: ha.nodes })]
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
  const ha = haState(health)
  // One sentence, as the mockup's "UCM 2.253 · SQLite · Simulation locale"; in HA, the node that answered
  // and its role follow it, a part a phone keeps out of sight (shell.css)
  const line = [health?.version && t('shell.version', { version: health.version }), text].filter(Boolean).join(' · ')
  const node = [ha?.node && t('shell.haNode', { node: ha.node }), ha?.leader === true && t('shell.haLeader'), ha?.leader === false && t('shell.haFollower')]
    .filter(Boolean)
  const summary = ha && haSummary(ha, t)

  const indicator = summary && (() => {
    const [haTone, icon, label] = summary
    const inner = <><Icon name={icon} /><span>{label}</span></>
    return onShowNodes ? (
      <button type="button" className={`ha-link ${haTone}`} id="ha-button" data-action="nodes" aria-haspopup="dialog"
        aria-label={t('shell.haIndicatorLabel', { state: label })} onClick={onShowNodes}>
        {inner}
      </button>
    ) : <span className={`ha-link ${haTone}`} id="ha-button">{inner}</span>
  })()

  return (
    <footer className="statusbar">
      <span className="live" role="status">
        <i className={`dot ${tone}`} aria-hidden="true" />
        {line}
        {node.length > 0 && <span className="ha-node">{node.map((n) => <span key={n}> · {n}</span>)}</span>}
        {/* The live connection, the product's addition, drawn by its own styles after the service state */}
        <span className="atl-out"><WebSocketIndicator className="shell-ws" /></span>
      </span>
      {pending !== null && (
        <Link to="/approvals" className="approvals-link" data-module="approvals">
          <Icon name="approve" />
          {pending > 0 ? t('shell.approvalsPending', { count: pending }) : t('shell.approvalsNone')}
        </Link>
      )}
      {indicator}
      <span className="shortcut">
        <kbd>Ctrl K</kbd> {t('common.search')} <span style={{ marginLeft: 10 }}><kbd>{t('shell.escapeKey')}</kbd> {t('inspector.close')}</span>
      </span>
    </footer>
  )
}
