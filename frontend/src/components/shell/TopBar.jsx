/** Horizontal bar: brand, main pages (Activity included), pinned modules, Modules menu, search, theme, bell, help, account. */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { MagnifyingGlass, Question, SquaresFour, Pulse } from '@phosphor-icons/react'
import { isVisible, moduleById } from '../../navigation/registry'
import { Logo } from '../Logo'
import { FIXED_IDS } from './pins'
import { ModulesMenu } from './ModulesMenu'
import { PinnedModules } from './PinnedModules'
import { ThemeMenu } from './ThemeMenu'
import { NotificationBell } from './NotificationBell'
import { UserMenu } from './UserMenu'
import { MobileModulePicker } from './MobileModulePicker'
import { useExpiringBadge } from './useExpiringBadge'
import './shell.css'

// Icons of the main bar where they differ from the module's own
const BAR_ICONS = { dashboard: SquaresFour, audit: Pulse }

export function TopBar({ can, pins, onTogglePin, activeId, onOpenSearch, onOpenHelp, hasHelp }) {
  const { t } = useTranslation()
  const { count: expiring, dismiss } = useExpiringBadge()
  const fixed = FIXED_IDS.map(moduleById).filter(m => m && isVisible(m, can))
  const current = activeId === '' ? 'dashboard' : activeId

  return (
    <header className="shell-topbar">
      <Link to="/" className="shell-brand" title={t('common.dashboard')}>
        <Logo variant="icon" withText={false} size="sm" className="shell-brand-mark" />
        <strong>UCM</strong>
      </Link>

      <nav className="shell-main-nav" aria-label={t('shell.mainNav')}>
        {fixed.map(m => {
          const Icon = BAR_ICONS[m.id] || m.icon
          const active = current === m.id
          const badged = m.id === 'certificates' && expiring > 0
          return (
            <span key={m.id} className={`shell-fixed${badged ? ' has-badge' : ''}`}>
              <Link
                to={m.path}
                data-module={m.id}
                className={`shell-navlink${active ? ' is-active' : ''}`}
                aria-current={active ? 'page' : undefined}
              >
                <Icon size={16} aria-hidden="true" />
                <span>{t(m.barKey)}</span>
              </Link>
              {badged && (
                <button type="button" className="shell-badge" onClick={dismiss}
                  aria-label={t('shell.expiringBadge', { count: expiring })}
                  title={t('common.dismiss')}>
                  {expiring > 9 ? '9+' : expiring}
                </button>
              )}
            </span>
          )
        })}
        <PinnedModules pins={pins} activeId={current} />
        <ModulesMenu can={can} pins={pins} onTogglePin={onTogglePin} activeId={current} onOpenHelp={onOpenHelp} />
      </nav>

      <MobileModulePicker can={can} activeId={activeId} />

      <div className="shell-tools">
        <button type="button" className="shell-search" onClick={onOpenSearch} aria-label={t('shell.search')}>
          <MagnifyingGlass size={16} aria-hidden="true" />
          <span>{t('shell.searchPlaceholder')}</span>
          <kbd>Ctrl K</kbd>
        </button>
        <ThemeMenu />
        <NotificationBell can={can} />
        {hasHelp && (
          <button type="button" className="shell-icon-btn" onClick={() => onOpenHelp()} aria-label={t('common.help')}>
            <Question size={16} aria-hidden="true" />
          </button>
        )}
        <UserMenu can={can} />
      </div>
    </header>
  )
}
