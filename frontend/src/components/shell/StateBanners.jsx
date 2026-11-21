/**
 * Banners at the top of the workspace, the mockup's stateBanners(): offline (reading continues, writes wait for the network),
 * then, in HA mode, a cluster maintenance (every write suspended, as the server refuses them)
 * or a degraded cluster (silent nodes, what still works). Nothing in the nominal state.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
import { formatDate } from '../../lib/utils'
import { haState, useHealth, useOnline, OFFLINE_NOTE_ID, WRITES_NOTE_ID } from './health'

/** Says the network change once: offline to assistive technology, back online in a message. */
function useNetworkNotice(online, onNotice) {
  const { t } = useTranslation()
  const [said, setSaid] = useState('')
  const previous = useRef(online)
  useEffect(() => {
    if (previous.current === online) return
    previous.current = online
    if (online) {
      setSaid('')
      onNotice?.(t('shell.offline.back'))
    } else setSaid(t('shell.offline.said'))
  }, [online]) // eslint-disable-line react-hooks/exhaustive-deps
  return said
}

/**
 * onShowNodes: opens the node list (read:settings); omitted, the banner has no button.
 * onNotice(message): the shell's message, for the network coming back.
 */
export function StateBanners({ onShowNodes, onNotice }) {
  const { t } = useTranslation()
  const online = useOnline()
  const said = useNetworkNotice(online, onNotice)
  const ha = haState(useHealth())

  const offline = !online && (
    <div className="state-banner" id="offline-banner">
      <Icon name="plug" />
      <p id={OFFLINE_NOTE_ID}>
        <strong>{t('shell.offline.title')}</strong>{' '}{t('shell.offline.text')}
      </p>
    </div>
  )

  // A cluster maintenance suspends every write, as the mockup's failover does: its banner
  let cluster = null
  if (ha?.maintenance) {
    const m = ha.maintenance
    const reason = t(`shell.ha.reasons.${m.reason}`, { defaultValue: m.reason || '' })
    cluster = (
      <div className="state-banner tone-warn" id="failover-banner">
        <Icon name="refresh" />
        <p id={WRITES_NOTE_ID}>
          <strong>{t('shell.ha.maintenanceTitle', { reason })}</strong>{' '}
          {m.expires_at ? t('shell.ha.maintenanceUntil', { date: formatDate(m.expires_at) }) : t('shell.ha.maintenanceOpen')}
        </p>
      </div>
    )
  } else if (ha && ha.stale > 0) {
    cluster = (
      <div className="state-banner tone-warn" id="ha-banner">
        <Icon name="warning" />
        <div className="ha-what">
          <p>
            <strong>{t('shell.ha.degradedTitle')}</strong>{' '}
            {ha.nodes !== null ? t('shell.ha.degradedOf', { count: ha.stale, total: ha.nodes }) : t('shell.ha.degraded', { count: ha.stale })}
          </p>
          <ul className="ha-can">
            <li><Icon name="check" /><span>{t('shell.ha.canRead')}</span></li>
            <li><Icon name="check" /><span>{ha.node ? t('shell.ha.canWriteOn', { node: ha.node }) : t('shell.ha.canWrite')}</span></li>
            <li>
              <Icon name={ha.leaderless ? 'clock' : 'check'} />
              <span>{ha.leaderless ? t('shell.ha.scheduleWaits') : t('shell.ha.scheduleOn', { node: ha.leaderNode })}</span>
            </li>
          </ul>
        </div>
        {onShowNodes && (
          <button type="button" className="btn" id="ha-banner-nodes" data-action="nodes" onClick={onShowNodes}>
            <Icon name="server" />{t('shell.ha.showNodes')}
          </button>
        )}
      </div>
    )
  }

  return (
    <>
      <p className="sr-only" role="status">{said}</p>
      {offline}
      {cluster}
    </>
  )
}
