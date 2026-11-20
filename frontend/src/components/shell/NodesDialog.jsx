/**
 * Nodes of the cluster, read from the service status (read:settings): role, last heartbeat,
 * state and version. UCM nodes share one database: there is no replication lag to show
 * and no manual failover to offer, so neither appears here.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import * as Dialog from '@radix-ui/react-dialog'
import { Check, HardDrives, Warning } from '@phosphor-icons/react'
import { ListDialog } from '../list/ListDialog'
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

  return (
    <ListDialog open={open} onOpenChange={(next) => { if (!next) onClose() }} title={t('shell.nodes.title')} wide narrow={false} testId="shell-nodes-dialog">
      <p className="shell-nodes-intro">{intro}</p>
      {failed && <p className="shell-nodes-intro" role="alert">{t('shell.nodes.loadFailed')}</p>}
      {nodes && (
        <ul className="shell-node-list">
          {nodes.map(n => {
            const late = n.stale && !n.stopped
            const beat = Date.parse(n.heartbeat_at)
            return (
              <li key={n.node_id} className={`shell-node-card${late ? ' is-late' : ''}`}>
                <div className="shell-node-head">
                  <strong className="shell-mono">{n.node_id}</strong>
                  {n.leader
                    ? <span className="shell-node-badge is-good"><Check size={13} aria-hidden="true" />{t('shell.nodes.leader')}</span>
                    : <span className="shell-node-badge"><HardDrives size={13} aria-hidden="true" />{t('shell.nodes.secondary')}</span>}
                </div>
                <dl className="shell-node-props">
                  <dt>{t('shell.nodes.heartbeat')}</dt>
                  <dd>{Number.isFinite(beat) ? beatText(beat, t) : '–'}</dd>
                  <dt>{t('shell.nodes.state')}</dt>
                  <dd>
                    {n.stopped ? t('shell.nodes.stopped')
                      : late ? <span className="is-warn"><Warning size={13} aria-hidden="true" />{t('shell.nodes.silent')}</span>
                        : <span className="is-good"><Check size={13} aria-hidden="true" />{t('shell.nodes.live')}</span>}
                  </dd>
                  <dt>{t('shell.nodes.version')}</dt>
                  <dd>{n.version || '–'}</dd>
                </dl>
              </li>
            )
          })}
        </ul>
      )}
      <div className="lv-dialog-actions">
        <Dialog.Close className="lv-btn is-primary" data-write="false">{t('common.close')}</Dialog.Close>
      </div>
    </ListDialog>
  )
}
