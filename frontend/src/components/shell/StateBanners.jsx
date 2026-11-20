/**
 * Banners at the top of the workspace, HA mode only: a cluster maintenance (every write
 * suspended, as the server refuses them) or a degraded cluster (silent nodes, what still works).
 * Outside HA, or with a healthy cluster, nothing is rendered.
 */
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, Check, Clock, HardDrives, Warning } from '@phosphor-icons/react'
import { formatDate } from '../../lib/utils'
import { haState, useHealth, WRITES_NOTE_ID } from './health'

/** onShowNodes: opens the node list (read:settings); omitted, the banner has no button. */
export function StateBanners({ onShowNodes }) {
  const { t } = useTranslation()
  const ha = haState(useHealth())
  if (!ha) return null

  if (ha.maintenance) {
    const m = ha.maintenance
    const reason = t(`shell.ha.reasons.${m.reason}`, { defaultValue: m.reason || '' })
    return (
      <div className="shell-state-banner is-warn" id="shell-maintenance-banner">
        <ArrowsClockwise size={18} aria-hidden="true" />
        <p id={WRITES_NOTE_ID}>
          <strong>{t('shell.ha.maintenanceTitle', { reason })}</strong>{' '}
          {m.expires_at ? t('shell.ha.maintenanceUntil', { date: formatDate(m.expires_at) }) : t('shell.ha.maintenanceOpen')}
        </p>
      </div>
    )
  }

  if (ha.stale > 0) {
    return (
      <div className="shell-state-banner is-warn" id="shell-ha-banner">
        <Warning size={18} aria-hidden="true" />
        <div className="shell-ha-what">
          <p>
            <strong>{t('shell.ha.degradedTitle')}</strong>{' '}
            {ha.nodes !== null ? t('shell.ha.degradedOf', { count: ha.stale, total: ha.nodes }) : t('shell.ha.degraded', { count: ha.stale })}
          </p>
          <ul className="shell-ha-can">
            <li><Check size={13} aria-hidden="true" /><span>{t('shell.ha.canRead')}</span></li>
            <li><Check size={13} aria-hidden="true" /><span>{ha.node ? t('shell.ha.canWriteOn', { node: ha.node }) : t('shell.ha.canWrite')}</span></li>
            <li>
              {ha.leaderless ? <Clock size={13} aria-hidden="true" /> : <Check size={13} aria-hidden="true" />}
              <span>{ha.leaderless ? t('shell.ha.scheduleWaits') : t('shell.ha.scheduleOn', { node: ha.leaderNode })}</span>
            </li>
          </ul>
        </div>
        {onShowNodes && (
          <button type="button" className="shell-btn" onClick={onShowNodes}>
            <HardDrives size={16} aria-hidden="true" />{t('shell.ha.showNodes')}
          </button>
        )}
      </div>
    )
  }
  return null
}
