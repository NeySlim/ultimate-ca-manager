/**
 * Bottom bar: only what /health reports (version, service state, HA node and cluster),
 * the live connection and the shortcuts (search, close the inspector). Nothing is shown for a field the API omits.
 */
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, Check, Warning } from '@phosphor-icons/react'
import { WebSocketIndicator } from '../WebSocketIndicator'
import { haState, useHealth } from './health'

/** The cluster in a few words, as the mockup's indicator: all current, nodes late, or maintenance. */
function haSummary(ha, t) {
  if (ha.maintenance) return ['warn', ArrowsClockwise, t('shell.haMaintenanceShort')]
  if (ha.stale > 0) return ['warn', Warning, t('shell.haLate', { count: ha.stale })]
  if (ha.nodes !== null) return ['good', Check, t('shell.haNodes', { count: ha.nodes })]
  return null
}

/** onShowNodes: opens the node list; omitted (no read:settings), the indicator is plain text. */
export function StatusBar({ onShowNodes }) {
  const { t } = useTranslation()
  const health = useHealth()

  let tone = 'muted'
  let text = ''
  if (health === false) { tone = 'bad'; text = t('shell.statusUnreachable') }
  else if (health) {
    tone = health.safe_mode ? 'warn' : 'good'
    text = health.safe_mode ? t('shell.statusSafeMode') : t('shell.statusRunning')
  }

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
          {health?.version && <span>{t('shell.version', { version: health.version })}</span>}
          {health?.version && text && <span aria-hidden="true">·</span>}
          {text && <span>{text}</span>}
        </span>
        {/* The live connection, at the most discreet place: an icon after the service state */}
        <WebSocketIndicator className="shell-ws" />
      </span>
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
