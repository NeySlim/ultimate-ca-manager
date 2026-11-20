/**
 * Notification bell: unread count on the button, side panel of the items derived from the
 * work queue and the journal (see notifications.js), grouped by day, newest first. A line
 * offers only the actions that exist: open its page, retry or publish when the API can, mark read.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  Archive, ArrowClockwise, ArrowsClockwise, Bell, CaretRight, Check, CheckCircle, FileX, PaperPlaneTilt, RocketLaunch,
  ShieldWarning, Users, Vault, Warning, X,
} from '@phosphor-icons/react'
import { formatDate } from '../../lib/utils'
import { getAppTimezone } from '../../stores/timezoneStore'
import { acmeService, crlService, settingsService } from '../../services'
import { useDisclosure, moveFocus } from './useDisclosure'
import { useNotifications } from './notifications'
import { guardProps, useWriteGuard } from './health'

const KIND_ICON = {
  acme_order_failed: Warning, acme_client_renewal_failed: Warning, approval_pending: CheckCircle,
  crl_due: FileX, crl_missing: FileX, manual_renewal_due: ArrowsClockwise, auto_renewal_blocked: ArrowsClockwise,
  ca_expiring: ShieldWarning, deploy_binding_left_behind: RocketLaunch, https_binding_left_behind: RocketLaunch,
  truststore_expiring: Vault, system_backup: Archive, system_restore: Archive,
  session_revoke: Users, session_revoke_all: Users,
}
// Tones of the mockup: approvals in the accent, CRLs and sessions a warning, failures and the rest by their tier
const toneOf = (item) => item.kind === 'approval_pending' ? 'accent'
  : item.kind.startsWith('session_') || item.kind.startsWith('crl_') ? 'warn'
    : item.tier === 'critical' ? 'bad' : 'warn'

// A CRL line is named after its authority, as the mockup's "CRL de <autorité>"
const titleOf = (item, t) => (item.kind.startsWith('crl_') && item.title ? t('shell.bell.crlTitle', { name: item.title }) : item.title)

// Behind the full-screen panel of a phone, the rest of the shell leaves the tab order and the reading
const COVERED = '.shell-skip, .shell-brand, .shell-mobile-nav, .shell-main-nav, .shell-tools > :not(.shell-bell-wrap), .shell-main, .shell-statusbar'
const PHONE = '(max-width: 800px)'

// A future due date (a CRL to publish) is shown at the time of reading
const whenOf = (item, now) => {
  const at = Date.parse(item.at)
  return Number.isFinite(at) ? Math.min(at, now) : null
}
// Calendar day in the instance's time zone, as a sortable number (20261108)
const dayKey = (ms, timeZone) => Number(new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' })
  .format(ms).replace(/\D/g, ''))

function useMailState(canSettings) {
  const [enabled, setEnabled] = useState(null)
  useEffect(() => {
    if (!canSettings) return undefined
    let alive = true
    settingsService.getExpiryAlerts()
      .then(res => { if (alive) setEnabled(!!(res?.data ?? res)?.enabled) })
      .catch(() => {})
    return () => { alive = false }
  }, [canSettings])
  return enabled
}

export function NotificationBell({ can }) {
  const { t, i18n } = useTranslation()
  const { items, unread, refresh, markRead, markAllRead } = useNotifications(can)
  // A side panel, not a popover: a click outside or a focus leaving it does not close it
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure({ light: false })
  const guard = useWriteGuard()
  const [busy, setBusy] = useState(null)
  const [said, setSaid] = useState('')
  const panelRef = useRef(null)
  const titleRef = useRef(null)
  const canSettings = !!can?.hasPermission?.('read:settings')
  const mail = useMailState(canSettings && open)
  const focusables = () => [...(panelRef.current?.querySelectorAll('a, button:not([disabled])') || [])]

  useEffect(() => {
    if (open) {
      refresh()
      titleRef.current?.focus()
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Escape closes the panel wherever the focus is, and gives it back to the bell
  useEffect(() => {
    if (!open) return undefined
    const onEscape = (e) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      e.preventDefault()
      close(true)
    }
    document.addEventListener('keydown', onEscape)
    return () => document.removeEventListener('keydown', onEscape)
  }, [open, close])

  // Full screen on a phone: the page behind it is inert while it is open
  useEffect(() => {
    if (!open || !window.matchMedia?.(PHONE).matches) return undefined
    const covered = [...document.querySelectorAll(COVERED)].filter(el => !el.hasAttribute('inert'))
    covered.forEach(el => el.setAttribute('inert', ''))
    return () => covered.forEach(el => el.removeAttribute('inert'))
  }, [open])

  const onKeyDown = (e) => {
    if (open && panelRef.current?.contains(e.target)) moveFocus(e, focusables())
  }

  // After "Mark read" the focus goes to the first action left on the line, else to the title
  const [focusAfter, setFocusAfter] = useState(null)
  useEffect(() => {
    if (!focusAfter) return
    const line = panelRef.current?.querySelector(`[data-notification="${CSS.escape(focusAfter)}"] .shell-notif-actions`)
    ;(line?.querySelector('a, button:not([disabled])') || titleRef.current)?.focus()
    setFocusAfter(null)
  }, [focusAfter])
  const readOne = (key) => { markRead(key); setFocusAfter(key) }
  const readAll = () => { markAllRead(); titleRef.current?.focus() }

  const summary = unread > 0 ? t('shell.bell.unread', { count: unread }) : t('shell.bell.allRead')
  const buttonState = unread > 0 ? t('shell.bell.unread', { count: unread }) : t('shell.bell.noneUnread')
  const kindLabel = (item) => t(`shell.bell.kinds.${item.kind}`, { defaultValue: item.kind })
  const lang = i18n?.language || 'en'
  const timeZone = getAppTimezone()
  const hm = (ms) => new Intl.DateTimeFormat(lang, { hour: '2-digit', minute: '2-digit', timeZone }).format(ms)
  const now = Date.now()
  const today = dayKey(now, timeZone)
  const yesterday = dayKey(now - 86400000, timeZone)
  const dayLabel = (ms) => {
    const d = dayKey(ms, timeZone)
    const date = formatDate(new Date(ms).toISOString(), { time: false })
    return d === today ? t('shell.bell.today', { date }) : d === yesterday ? t('shell.bell.yesterday', { date }) : date
  }

  // Actions the API has for an item, under the user's rights and the write guard
  const actionOf = (item) => {
    if (item.source !== 'queue') return null
    if (item.kind === 'acme_client_renewal_failed' && can?.hasPermission?.('write:acme')) {
      return { icon: ArrowClockwise, label: t('shell.bell.retry'), aria: t('shell.bell.retryLabel', { name: item.title }),
        run: () => acmeService.renewOrder(item.id), done: t('overview.queue.retried') }
    }
    if ((item.kind === 'crl_due' || item.kind === 'crl_missing') && can?.hasPermission?.('write:crl')) {
      return { icon: PaperPlaneTilt, label: t('shell.bell.publish'), aria: t('shell.bell.publishLabel', { name: item.title }),
        run: () => crlService.regenerate(item.id), done: t('notifications.crlRegenerated', { name: item.title }) }
    }
    return null
  }
  const act = async (item, action) => {
    if (busy) return
    setBusy(item.key)
    try {
      await action.run()
      setSaid(action.done)
      markRead(item.key)
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: item.kind.startsWith('crl') ? 'ca' : 'certificate' } }))
      refresh()
    } catch (error) {
      setSaid(error?.message || t('overview.queue.actionFailed'))
    } finally {
      setBusy(null)
    }
  }

  const groups = []
  for (const item of items) {
    const when = whenOf(item, now)
    const label = when === null ? t('shell.bell.undated') : dayLabel(when)
    let g = groups.find(x => x.label === label)
    if (!g) groups.push(g = { label, items: [] })
    g.items.push({ ...item, when })
  }

  return (
    <div className="shell-pop-wrap shell-bell-wrap" ref={rootProps.ref} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="shell-icon-btn shell-bell"
        aria-expanded={open}
        aria-controls="shell-bell-panel"
        aria-label={t('shell.bell.label', { state: buttonState })}
        onClick={() => setOpen(!open)}
      >
        <Bell size={16} aria-hidden="true" />
        {unread > 0 && <span className="shell-bell-count" aria-hidden="true">{unread}</span>}
      </button>
      <aside id="shell-bell-panel" ref={panelRef} className="shell-notif-panel"
        aria-labelledby="shell-bell-title" hidden={!open}>
        <header className="shell-notif-head">
          <div>
            <h2 id="shell-bell-title" ref={titleRef} tabIndex={-1}>{t('shell.bell.title')}</h2>
            <p role="status">{t('shell.bell.summary', { state: summary, count: items.length })}</p>
          </div>
          <button type="button" className="shell-btn is-quiet" disabled={unread === 0} onClick={readAll}>
            <Check size={17} aria-hidden="true" />{t('shell.bell.markAllRead')}
          </button>
          <button type="button" className="shell-icon-btn" aria-label={t('shell.bell.close')} onClick={() => close(true)}>
            <X size={16} aria-hidden="true" />
          </button>
        </header>
        <div className="shell-notif-scroll">
          {items.length === 0 ? (
            <p className="shell-notif-empty"><Check size={16} aria-hidden="true" />{t('shell.bell.empty')}</p>
          ) : groups.map((g, gi) => (
            <section key={g.label} className="shell-notif-group" aria-labelledby={`shell-notif-day-${gi}`}>
              <h3 id={`shell-notif-day-${gi}`}>{g.label}</h3>
              <ul>
                {g.items.map(item => {
                  const tone = toneOf(item)
                  const Icon = KIND_ICON[item.kind] || Warning
                  const title = titleOf(item, t)
                  const name = title || kindLabel(item)
                  const detail = item.detail || t(`overview.cause.${item.kind}`, { defaultValue: '' })
                  const action = actionOf(item)
                  return (
                    <li key={item.key} className={`shell-notif-item${item.unread ? ' is-unread' : ''}`} data-notification={item.key}>
                      <span className={`shell-notif-icon is-${tone}`} aria-hidden="true"><Icon size={18} /></span>
                      <div className="shell-notif-main">
                        <p className="shell-notif-meta">
                          <span className={`shell-notif-kind is-${tone}`}>{kindLabel(item)}</span>
                          {item.unread && <span className="shell-notif-new">{t('shell.bell.new')}</span>}
                          {item.when !== null && <time dateTime={new Date(item.when).toISOString()}>{hm(item.when)}</time>}
                        </p>
                        {title && <p className="shell-notif-title">{title}</p>}
                        {detail && <p className="shell-notif-detail">{detail}</p>}
                        <div className="shell-notif-actions">
                          {action && (
                            <button type="button" className="shell-btn" aria-label={action.aria}
                              aria-busy={busy === item.key || undefined}
                              {...guardProps(guard, !!busy)}
                              onClick={() => act(item, action)}>
                              <action.icon size={17} aria-hidden="true" />{action.label}
                            </button>
                          )}
                          {item.href && (
                            <Link to={item.href} className="shell-btn"
                              aria-label={`${t('shell.bell.open')}: ${name}`}
                              onClick={() => { markRead(item.key); close() }}>
                              <CaretRight size={17} aria-hidden="true" />{t('shell.bell.open')}
                            </Link>
                          )}
                          {item.unread && (
                            <button type="button" className="shell-btn is-quiet"
                              aria-label={`${t('shell.bell.markRead')}: ${name}`}
                              onClick={() => readOne(item.key)}>
                              {t('shell.bell.markRead')}
                            </button>
                          )}
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </div>
        <p className="sr-only" role="status">{said}</p>
        {canSettings && (
          <footer className="shell-notif-foot">
            <PaperPlaneTilt size={14} aria-hidden="true" />
            <p>
              {mail === null ? null : <>{mail ? t('shell.bell.mailOn') : t('shell.bell.mailOff')} </>}
              <Link className="shell-text-link" to="/settings?tab=email" onClick={() => close()}>{t('shell.bell.mailSettings')}</Link>
            </p>
          </footer>
        )}
      </aside>
    </div>
  )
}
