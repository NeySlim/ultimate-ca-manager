/**
 * "Modules" mega-menu, the mockup's modulesMenu(): the registry's groups filtered by the user's
 * rights, without the pages of the main bar, each module with its one-line description and a pin
 * toggle. A disclosure, not an ARIA menu: items are links. The button closes the main bar's links,
 * the menu follows the bar (the mockup's order); both share the disclosure `menu` (useDisclosure).
 */
import { useEffect, useLayoutEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier/Icon'
import { familyOf, glyphOf, menuGroupsFor, menuLabelKey } from '../../navigation/registry'
import { canPinModule, MAX_PINS, FIXED_IDS } from './pins'
import { moveFocus } from './useDisclosure'

const EDGE = 16
const linksOf = (menu) => [...(menu.partRef.current?.querySelectorAll('a[data-module]') || [])]

function keys(menu) {
  return (e) => {
    menu.partProps.onKeyDown(e)
    if (e.defaultPrevented) return
    if (e.target === menu.buttonRef.current && e.key === 'ArrowDown' && !menu.open) {
      e.preventDefault()
      menu.setOpen(true)
      return
    }
    if (menu.open) moveFocus(e, linksOf(menu))
  }
}

/** The bar's Modules button; lit for a module page that is neither a main page nor pinned. */
export function ModulesButton({ menu, can, pins, activeId }) {
  const { t } = useTranslation()
  const groups = menuGroupsFor(can)
  const lit = !FIXED_IDS.includes(activeId) && !pins.includes(activeId) && groups.some(g => g.modules.some(m => m.id === activeId))
  return (
    <button
      type="button"
      id="modules-button"
      ref={(el) => { menu.buttonRef.current = el; menu.rootRef.current = el }}
      className={lit ? 'active' : undefined}
      data-action="modules"
      aria-expanded={menu.open}
      aria-controls="modules-menu"
      onClick={() => menu.setOpen(!menu.open)}
      onKeyDown={keys(menu)}
      onBlur={menu.rootProps.onBlur}
    >
      <Icon name="layers" />{t('shell.modules')} <Icon name="down" />
    </button>
  )
}

/** onNotice(message): the shell's message, for a refused fourth pin; onOpenHelp: the navigation help. */
export function ModulesMenu({ menu, can, pins, onTogglePin, activeId, onOpenHelp, onNotice }) {
  const { t } = useTranslation()
  const groups = menuGroupsFor(can)
  const pages = groups.reduce((n, g) => n + g.modules.length, 0)
  const full = pins.length >= MAX_PINS

  useEffect(() => {
    if (menu.open) linksOf(menu)[0]?.focus()
  }, [menu.open]) // eslint-disable-line react-hooks/exhaustive-deps

  // The menu opens under its button, kept inside the window with a 16 px margin (the mockup's placeMenu)
  useLayoutEffect(() => {
    const panel = menu.partRef.current
    const button = menu.buttonRef.current
    if (!menu.open || !panel || !button) return undefined
    const place = () => {
      const left = button.getBoundingClientRect().left
      panel.style.left = `${Math.max(EDGE, Math.min(left, window.innerWidth - panel.offsetWidth - EDGE))}px`
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  // No dependency list: the bar may gain a link while the menu is open, and the button moves
  })

  // A refused fourth pin is explained in a message, as the mockup's toast, not by silence
  const pin = (id) => { if (!onTogglePin(id)) onNotice?.(t('shell.pinFull')) }

  return (
    <nav className="modules-menu" id="modules-menu" ref={menu.partRef} aria-label={t('shell.modulesMenuLabel')}
      hidden={!menu.open} onKeyDown={keys(menu)} onBlur={menu.partProps.onBlur}>
      <div className="menu-head">
        <strong>{t('shell.modulesMenuLabel')}</strong>
        <span>{t('shell.modulePages', { count: pages })} · {t('shell.pinCount', { count: pins.length, max: MAX_PINS })}</span>
      </div>
      <div className="menu-groups">
        {groups.map(g => (
          <section key={g.id} className="menu-group">
            <h2 className="menu-group-title" id={`menu-group-${g.id}`}>
              {t(g.labelKey)}<span className="counter">{g.modules.length}</span>
            </h2>
            <ul aria-labelledby={`menu-group-${g.id}`}>
              {g.modules.map(m => {
                const current = m.id === activeId
                const pinned = pins.includes(m.id)
                const label = t(menuLabelKey(m))
                return (
                  <li key={m.id} className={`menu-item${current ? ' current' : ''}`}>
                    <Link to={m.path} id={`menu-${m.id}`} data-module={m.id} data-family={familyOf(m)} aria-current={current ? 'page' : undefined}>
                      <Icon name={glyphOf(m)} />
                      <span>
                        <strong>{label}</strong>
                        {m.descKey && <small>{t(m.descKey)}</small>}
                      </span>
                    </Link>
                    {canPinModule(m) && (
                      <button
                        type="button"
                        className="icon-btn pin-btn"
                        id={`pin-${m.id}`}
                        data-pin={m.id}
                        aria-pressed={pinned}
                        aria-label={t('shell.pinModule', { name: label })}
                        title={pinned ? t('shell.pinRemove') : full ? t('shell.pinFullTitle') : t('shell.pinAdd')}
                        aria-disabled={!pinned && full ? 'true' : undefined}
                        onClick={() => pin(m.id)}
                      >
                        <Icon name="pin" />
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
      <p className="menu-foot">
        <Icon name="pin" />{t('shell.pinHint')}
        {/* The product's addition: how the bar works, in the help panel; the mockup's link form */}
        {onOpenHelp && (
          <> <button type="button" className="text-link" onClick={() => { menu.close(); onOpenHelp('navigation') }}>
            {t('shell.navHelp')}
          </button></>
        )}
      </p>
    </nav>
  )
}
