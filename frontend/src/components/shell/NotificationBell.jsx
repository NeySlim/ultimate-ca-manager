/**
 * Notification bell: unread count on the button, panel of the items derived from the
 * work queue and the journal (see notifications.js). Actions are links to the page.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Bell, Check, X } from '@phosphor-icons/react'
import { formatDate } from '../../lib/utils'
import { useDisclosure, moveFocus } from './useDisclosure'
import { useNotifications } from './notifications'

export function NotificationBell({ can }) {
  const { t } = useTranslation()
  const { items, unread, refresh, markRead, markAllRead } = useNotifications(can)
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  const titleRef = useRef(null)
  const focusables = () => [...(panelRef.current?.querySelectorAll('a, button:not([disabled])') || [])]

  useEffect(() => {
    if (open) {
      refresh()
      titleRef.current?.focus()
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (e.defaultPrevented) return
    if (open && panelRef.current?.contains(e.target)) moveFocus(e, focusables())
  }

  const summary = unread > 0 ? t('shell.bell.unread', { count: unread }) : t('shell.bell.allRead')
  const kindLabel = (item) => t(`shell.bell.kinds.${item.kind}`, { defaultValue: item.kind })

  return (
    <div className="shell-pop-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="shell-icon-btn shell-bell"
        aria-expanded={open}
        aria-controls="shell-bell-panel"
        aria-label={`${t('shell.bell.title')}: ${summary}`}
        onClick={() => setOpen(!open)}
      >
        <Bell size={18} aria-hidden="true" />
        {unread > 0 && <span className="shell-bell-count" aria-hidden="true">{unread > 9 ? '9+' : unread}</span>}
      </button>
      <section id="shell-bell-panel" ref={panelRef} className="shell-pop shell-bell-panel"
        aria-labelledby="shell-bell-title" hidden={!open}>
        <header className="shell-bell-head">
          <div className="shell-grow">
            <h2 id="shell-bell-title" ref={titleRef} tabIndex={-1}>{t('shell.bell.title')}</h2>
            <p role="status">{summary}</p>
          </div>
          <button type="button" className="shell-pop-item shell-bell-all" disabled={unread === 0} onClick={markAllRead}>
            <Check size={14} aria-hidden="true" />{t('shell.bell.markAllRead')}
          </button>
          <button type="button" className="shell-icon-btn" aria-label={t('common.close')} onClick={() => close(true)}>
            <X size={16} aria-hidden="true" />
          </button>
        </header>
        {items.length === 0 ? (
          <p className="shell-muted shell-bell-empty">{t('shell.bell.empty')}</p>
        ) : (
          <ul className="shell-bell-list">
            {items.map(item => (
              <li key={item.key} className={`shell-bell-item${item.unread ? ' is-unread' : ''}`} data-notification={item.key}>
                <p className="shell-bell-meta">
                  <span className={`shell-bell-kind tier-${item.tier}`}>{kindLabel(item)}</span>
                  {item.unread && <span className="shell-bell-new">{t('shell.bell.new')}</span>}
                  {item.at && <time dateTime={item.at}>{formatDate(item.at)}</time>}
                </p>
                {item.title && <p className="shell-bell-text">{item.title}</p>}
                <div className="shell-bell-actions">
                  {item.href && (
                    <Link to={item.href} className="shell-pop-item shell-bell-act"
                      aria-label={`${t('shell.bell.open')}: ${item.title || kindLabel(item)}`}
                      onClick={() => { markRead(item.key); close() }}>
                      {t('shell.bell.open')}
                    </Link>
                  )}
                  {item.unread && (
                    <button type="button" className="shell-pop-item shell-bell-act"
                      aria-label={`${t('shell.bell.markRead')}: ${item.title || kindLabel(item)}`}
                      onClick={() => markRead(item.key)}>
                      {t('shell.bell.markRead')}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
