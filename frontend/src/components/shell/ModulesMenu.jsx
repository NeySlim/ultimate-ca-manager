/**
 * "Modules" mega-menu: the registry's groups filtered by the user's rights, without the
 * pages of the main bar, each module with its one-line description and a pin toggle.
 * A disclosure, not an ARIA menu: items are links.
 */
import { useEffect, useLayoutEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { PushPinSimple, Stack, CaretDown, Question } from '@phosphor-icons/react'
import { menuGroupsFor, menuLabelKey } from '../../navigation/registry'
import { canPinModule, MAX_PINS, FIXED_IDS } from './pins'
import { useDisclosure, moveFocus } from './useDisclosure'

const EDGE = 16

/** onNotice(message): the shell's message, for a refused fourth pin. */
export function ModulesMenu({ can, pins, onTogglePin, activeId, onOpenHelp, onNotice }) {
  const { t } = useTranslation()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const menuRef = useRef(null)
  const groups = menuGroupsFor(can)
  const pages = groups.reduce((n, g) => n + g.modules.length, 0)
  const full = pins.length >= MAX_PINS
  // The fixed links carry their own highlight: Modules lights up for a module view only
  const activeInMenu = !FIXED_IDS.includes(activeId) && groups.some(g => g.modules.some(m => m.id === activeId))
  const activeIsPinned = pins.includes(activeId)
  const links = () => [...(menuRef.current?.querySelectorAll('a[data-module]') || [])]

  useEffect(() => {
    if (open) links()[0]?.focus()
  }, [open])

  // The menu opens under its button, kept inside the window with a 16 px margin
  useLayoutEffect(() => {
    const menu = menuRef.current
    const button = buttonRef.current
    if (!open || !menu || !button) return undefined
    const place = () => {
      const left = button.getBoundingClientRect().left
      menu.style.left = `${Math.max(EDGE, Math.min(left, window.innerWidth - menu.offsetWidth - EDGE))}px`
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [open, buttonRef])

  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (e.defaultPrevented) return
    if (e.target === buttonRef.current && e.key === 'ArrowDown' && !open) {
      e.preventDefault()
      setOpen(true)
      return
    }
    if (open && (menuRef.current?.contains(e.target) || e.target === buttonRef.current)) moveFocus(e, links())
  }

  // A refused fourth pin is explained in a message, as the mockup's toast, not by silence
  const pin = (id) => { if (!onTogglePin(id)) onNotice?.(t('shell.pinFull')) }

  return (
    <div className="shell-modules" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className={`shell-navlink${activeInMenu && !activeIsPinned ? ' is-active' : ''}`}
        aria-expanded={open}
        aria-controls="shell-modules-menu"
        onClick={() => setOpen(!open)}
      >
        <Stack size={16} aria-hidden="true" />
        <span>{t('shell.modules')}</span>
        <CaretDown size={16} aria-hidden="true" />
      </button>
      <nav id="shell-modules-menu" ref={menuRef} className="shell-menu" aria-label={t('shell.modulesMenuLabel')} hidden={!open}>
        <div className="shell-menu-head">
          <strong>{t('shell.modulesMenuLabel')}</strong>
          <span>{t('shell.modulePages', { count: pages })} · {t('shell.pinCount', { count: pins.length, max: MAX_PINS })}</span>
        </div>
        <div className="shell-menu-groups">
          {groups.map(g => (
            <section key={g.id} className="shell-menu-group">
              <h2 id={`shell-menu-group-${g.id}`} className="shell-menu-title">
                {t(g.labelKey)}<span className="shell-count">{g.modules.length}</span>
              </h2>
              <ul aria-labelledby={`shell-menu-group-${g.id}`}>
                {g.modules.map(m => {
                  const Icon = m.icon
                  const current = m.id === activeId
                  const pinned = pins.includes(m.id)
                  const label = t(menuLabelKey(m))
                  return (
                    <li key={m.id} className={`shell-menu-item${current ? ' is-current' : ''}`}>
                      <Link to={m.path} data-module={m.id} aria-current={current ? 'page' : undefined}>
                        <Icon size={16} aria-hidden="true" />
                        <span>
                          <strong>{label}</strong>
                          {m.descKey && <small>{t(m.descKey)}</small>}
                        </span>
                      </Link>
                      {canPinModule(m) && (
                        <button
                          type="button"
                          className="shell-pin"
                          aria-pressed={pinned}
                          aria-disabled={!pinned && full ? 'true' : undefined}
                          aria-label={t('shell.pinModule', { name: label })}
                          title={pinned ? t('shell.pinRemove') : full ? t('shell.pinFullTitle') : t('shell.pinAdd')}
                          onClick={() => pin(m.id)}
                        >
                          <PushPinSimple size={14} aria-hidden="true" />
                        </button>
                      )}
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </div>
        <div className="shell-menu-foot">
          <PushPinSimple size={13} aria-hidden="true" />
          <p>{t('shell.pinHint')}</p>
          {onOpenHelp && (
            <button type="button" className="shell-link-button" onClick={() => { close(); onOpenHelp('navigation') }}>
              <Question size={13} aria-hidden="true" />{t('shell.navHelp')}
            </button>
          )}
        </div>
      </nav>
    </div>
  )
}
