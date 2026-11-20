/**
 * Banners at the top of the workspace: offline (reading continues, writes wait for the network),
 * then, in HA mode, a cluster maintenance (every write suspended, as the server refuses them)
 * or a degraded cluster (silent nodes, what still works). Nothing in the nominal state.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, Check, Clock, HardDrives, Plug, Warning } from '@phosphor-icons/react'
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
    <div className="shell-state-banner" id="shell-offline-banner">
      <Plug size={18} aria-hidden="true" />
      <p id={OFFLINE_NOTE_ID}>
        <strong>{t('shell.offline.title')}</strong>{' '}{t('shell.offline.text')}
      </p>
    </div>
  )

  let cluster = null
  if (ha?.maintenance) {
    const m = ha.maintenance
    const reason = t(`shell.ha.reasons.${m.reason}`, { defaultValue: m.reason || '' })
    cluster = (
      <div className="shell-state-banner is-warn" id="shell-maintenance-banner">
        <ArrowsClockwise size={18} aria-hidden="true" />
        <p id={WRITES_NOTE_ID}>
          <strong>{t('shell.ha.maintenanceTitle', { reason })}</strong>{' '}
          {m.expires_at ? t('shell.ha.maintenanceUntil', { date: formatDate(m.expires_at) }) : t('shell.ha.maintenanceOpen')}
        </p>
      </div>
    )
  } else if (ha && ha.stale > 0) {
    cluster = (
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

  return (
    <>
      <p className="sr-only" role="status">{said}</p>
      {offline}
      {cluster}
    </>
  )
}
