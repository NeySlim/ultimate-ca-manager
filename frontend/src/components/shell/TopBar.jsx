/**
 * The masthead, the mockup's nav(): brand, main pages (Activity included), pinned modules and the
 * Modules button, the Modules menu, the phone's page picker, then search, language, theme, bell, help and account.
 */
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier/Icon'
import { markSrc } from '../atelier/icons'
import { glyphOf, isVisible, moduleById } from '../../navigation/registry'
import { FIXED_IDS } from './pins'
import { ModulesButton, ModulesMenu } from './ModulesMenu'
import { PinnedModules } from './PinnedModules'
import { LanguageMenu } from './LanguageMenu'
import { ThemeMenu } from './ThemeMenu'
import { NotificationBell } from './NotificationBell'
import { UserMenu } from './UserMenu'
import { MobileModulePicker } from './MobileModulePicker'
import { useExpiringBadge } from './useExpiringBadge'
import { useDisclosure } from './useDisclosure'
import { useNavRoom } from './useNavRoom'
import './shell.css'

export function TopBar({ can, pins, onTogglePin, activeId, onOpenSearch, onOpenHelp, hasHelp, onNotice }) {
  const { t, i18n } = useTranslation()
  const { count: expiring, dismiss } = useExpiringBadge()
  const navRef = useRef(null)
  useNavRoom(navRef, [pins.join(), i18n?.language])
  const menu = useDisclosure()
  const fixed = FIXED_IDS.map(moduleById).filter(m => m && isVisible(m, can))
  const current = activeId === '' ? 'dashboard' : activeId

  return (
    <header className="masthead">
      <Link to="/" className="brand" data-nav="dashboard">
        <img src={markSrc} width="28" height="32" alt="" /><strong>UCM</strong>
      </Link>
      <nav className="main-nav" ref={navRef} aria-label={t('shell.mainNav')}>
        {fixed.map(m => {
          const active = current === m.id
          const badged = m.id === 'certificates' && expiring > 0
          // The product's expiry count sits on the link, out of its layout (shell.css); following the link dismisses it
          return (
            <Link
              key={m.id}
              to={m.path}
              data-nav={m.id}
              data-module={m.id}
              className={active ? 'active' : undefined}
              aria-current={active ? 'page' : undefined}
              onClick={badged ? dismiss : undefined}
            >
              <Icon name={glyphOf(m)} />{t(m.barKey)}
              {badged && <span className="notif-count nav-count" aria-hidden="true">{expiring > 99 ? '99+' : expiring}</span>}
              {badged && <span className="sr-only">{t('shell.expiringCount', { count: expiring })}</span>}
            </Link>
          )
        })}
        <PinnedModules pins={pins} activeId={current} />
        <ModulesButton menu={menu} can={can} pins={pins} activeId={current} />
      </nav>
      <ModulesMenu menu={menu} can={can} pins={pins} onTogglePin={onTogglePin} activeId={current} onOpenHelp={onOpenHelp} onNotice={onNotice} />
      <MobileModulePicker can={can} activeId={activeId} />
      <div className="global-tools">
        <button type="button" className="btn search-command" id="shell-search" data-action="command" aria-label={t('shell.search')} onClick={onOpenSearch}>
          <Icon name="search" /><span>{t('shell.searchPlaceholder')}</span><kbd>Ctrl K</kbd>
        </button>
        <LanguageMenu />
        <ThemeMenu />
        <NotificationBell can={can} />
        {hasHelp && (
          <button type="button" className="icon-btn quiet help-button" data-action="help" aria-label={t('common.help')} onClick={() => onOpenHelp()}>
            <Icon name="help" />
          </button>
        )}
        <UserMenu can={can} />
      </div>
    </header>
  )
}
