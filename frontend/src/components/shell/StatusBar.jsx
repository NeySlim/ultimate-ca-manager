/**
 * Bottom bar, the mockup's footer.statusbar: what /health reports (version, service state, HA node and cluster) in one line,
 * the live connection, then the activity in short: pending approvals, background jobs running, the overview's interventions
 * to make and the detached windows, each a way to its page; « Nothing pending » when all that may be read is calm. Then the
 * shortcuts (search, close the inspector). Nothing is shown for a field the API omits.
 */
import { useEffect } from 'react'
import { usePanel } from './openPanel'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier/Icon'
import { WebSocketIndicator } from '../WebSocketIndicator'
import { useToolbarMenu } from '../list/useToolbarMenu'
import { useDetached } from '../detached/useDetached'
import { KIND_ICONS } from '../detached/kindIcons'
import { haState, useHealth } from './health'
import { useActivity } from './useActivity'

// Where a running job is followed: backup and restore in Settings, the chain check in the journal
const JOB_PAGES = { backup: '/settings?tab=backup', restore: '/settings?tab=backup', audit_verify: '/audit' }
const JOB_KINDS = ['backup', 'restore', 'audit_verify']

/** The cluster in a few words, the mockup's haIndicator(): all current, nodes late, or maintenance. */
function haSummary(ha, t) {
  if (ha.maintenance) return ['warn', 'refresh', t('shell.haMaintenanceShort')]
  if (ha.stale > 0) return ['warn', 'warning', t('shell.haLate', { count: ha.stale })]
  if (ha.nodes !== null) return ['good', 'check', t('shell.haNodes', { count: ha.nodes })]
  return null
}

/** The detached windows, in a small menu of the bar: choosing one brings it in front with the focus. */
function DetachedMenu({ detached, t }) {
  // One of the shell's panels: opening it closes the bar's menus, and the reverse
  const [open, setOpen] = usePanel('status-windows')
  const { buttonRef, menuRef, onButtonKeyDown } = useToolbarMenu(open, setOpen)
  const { windows, front } = detached
  useEffect(() => { if (!windows.length) setOpen(false) }, [windows.length])
  // A click elsewhere closes it, as the bar's other menus
  useEffect(() => {
    if (!open) return undefined
    const away = (e) => { if (!menuRef.current?.contains(e.target) && !buttonRef.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('pointerdown', away)
    return () => document.removeEventListener('pointerdown', away)
  }, [open, menuRef, buttonRef])
  return (
    <span className="pop-wrap detached-wrap">
      <button ref={buttonRef} type="button" className="status-link" id="detached-button" aria-haspopup="menu" aria-expanded={open}
        aria-controls="detached-menu" onClick={() => setOpen(!open)} onKeyDown={onButtonKeyDown}>
        <Icon name="layers" />{t('shell.activity.windows', { count: windows.length })}
      </button>
      <ul ref={menuRef} className="pop-menu detached-menu" id="detached-menu" role="menu" aria-label={t('shell.activity.windowsLabel')} hidden={!open}>
        {/* The front window first */}
        {windows.map((w, i) => [w, w.z ?? i]).sort((a, b) => b[1] - a[1]).map(([w]) => (
          <li key={w.key} role="none">
            <button type="button" role="menuitem" tabIndex={-1} className="pop-item" data-detached-front={w.key}
              onClick={() => { setOpen(false); front(w.key, { focus: true }) }}>
              <Icon name={KIND_ICONS[w.kind] || 'layers'} /><span className="pop-label">{w.title || t('common.loading')}</span>
            </button>
          </li>
        ))}
      </ul>
    </span>
  )
}

/** The activity in short, each part a link to its page; « Nothing pending » when all that is readable is calm. */
function Activity({ can, t }) {
  const { approvals, queue, jobs, calm } = useActivity(can)
  const detached = useDetached()
  const windows = detached?.available && detached.windows.length > 0
  if (!calm && !approvals && !queue && !jobs.length && !windows) return null
  return (
    <span className="status-activity" role="group" aria-label={t('shell.activity.label')}>
      {approvals > 0 && (
        <Link to="/approvals" className="approvals-link" data-module="approvals">
          <Icon name="approve" />{t('shell.approvalsPending', { count: approvals })}
        </Link>
      )}
      {jobs.map((job) => (
        <Link key={job.id} to={JOB_PAGES[job.kind] || '/'} className="status-link" data-job={job.kind}>
          <Icon name="refresh" />{t(`shell.activity.jobs.${JOB_KINDS.includes(job.kind) ? job.kind : 'other'}`)}
        </Link>
      ))}
      {queue > 0 && (
        <Link to="/" className="status-link" data-dashboard-link="queue">
          <Icon name="warning" />{t('shell.activity.queue', { count: queue })}
        </Link>
      )}
      {calm && <span className="status-link calm" data-calm=""><Icon name="check" />{t('shell.activity.calm')}</span>}
      {windows && <DetachedMenu detached={detached} t={t} />}
    </span>
  )
}

/** onShowNodes: opens the node list; omitted (no read:settings), the indicator is plain text. */
export function StatusBar({ onShowNodes, can }) {
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
        {/* The live connection, the product's addition, after the service state */}
        <WebSocketIndicator />
      </span>
      <Activity can={can} t={t} />
      {indicator}
      <span className="shortcut">
        <kbd>Ctrl K</kbd> {t('common.search')} <span style={{ marginLeft: 10 }}><kbd>{t('shell.escapeKey')}</kbd> {t('inspector.close')}</span>
      </span>
    </footer>
  )
}
