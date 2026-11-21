/**
 * Nodes of the cluster, read from the service status (read:settings): role, last heartbeat,
 * state and version. UCM nodes share one database: there is no replication lag to show
 * and no manual failover to offer, so neither appears here. The mockup's nodesDialog(), wide.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from '../atelier/AtelierDialog'
import { Icon } from '../atelier/Icon'
import { systemService } from '../../services/system.service'
import { relativeAgo } from '../../lib/relativeTime'

// Heartbeats are seconds apart: seconds and minutes first, then the usual wording
function beatText(ms, t, now = Date.now()) {
  const s = Math.max(0, Math.round((now - ms) / 1000))
  if (s < 60) return t('shell.nodes.secondsAgo', { count: s })
  if (s < 3600) return t('shell.nodes.minutesAgo', { count: Math.round(s / 60) })
  return relativeAgo(ms, t)
}

export function NodesDialog({ open, onClose, ha }) {
  const { t } = useTranslation()
  const [nodes, setNodes] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!open) return undefined
    let alive = true
    setFailed(false)
    systemService.getServiceStatus()
      .then(res => { if (alive) setNodes(Array.isArray(res?.data?.cluster?.nodes) ? res.data.cluster.nodes : []) })
      .catch(() => { if (alive) { setNodes(null); setFailed(true) } })
    return () => { alive = false }
  }, [open])

  const intro = ha?.maintenance ? t('shell.nodes.introMaintenance')
    : ha?.stale ? t('shell.nodes.introLate', { count: ha.stale })
      : t('shell.nodes.introCurrent')

  if (!open) return null
  return (
    <AtelierDialog title={t('shell.nodes.title')} size="wide" onClose={onClose} returnTo="ha-button" testId="shell-nodes-dialog">
      <p className="small muted nodes-intro">{intro}</p>
      {failed && <p className="small muted nodes-intro" role="alert">{t('shell.nodes.loadFailed')}</p>}
      {nodes && (
        <ul className="node-list">
          {nodes.map(n => {
            const late = n.stale && !n.stopped
            const beat = Date.parse(n.heartbeat_at)
            return (
              <li key={n.node_id} className={`node-card${late ? ' late' : ''}`} id={`node-${n.node_id}`}>
                <div className="node-head">
                  <strong className="mono">{n.node_id}</strong>
                  {n.leader
                    ? <span className="badge good"><Icon name="check" />{t('shell.nodes.leader')}</span>
                    : <span className="badge"><Icon name="server" />{t('shell.nodes.secondary')}</span>}
                </div>
                <dl className="node-props">
                  <dt>{t('shell.nodes.heartbeat')}</dt>
                  <dd>{Number.isFinite(beat) ? beatText(beat, t) : '–'}</dd>
                  <dt>{t('shell.nodes.state')}</dt>
                  <dd>
                    {n.stopped ? t('shell.nodes.stopped')
                      : late ? <span className="warn"><Icon name="warning" />{t('shell.nodes.silent')}</span>
                        : <span className="good"><Icon name="check" />{t('shell.nodes.live')}</span>}
                  </dd>
                  <dt>{t('shell.nodes.version')}</dt>
                  <dd>{n.version || '–'}</dd>
                </dl>
              </li>
            )
          })}
        </ul>
      )}
      <div className="modal-actions">
        <button type="button" className="btn primary" data-action="close-modal" data-write="false" onClick={onClose}>{t('common.close')}</button>
      </div>
    </AtelierDialog>
  )
}
