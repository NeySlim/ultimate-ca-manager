/**
 * "Modules" mega-menu: the registry's groups filtered by the user's rights,
 * with a pin toggle per module. A disclosure, not an ARIA menu: items are links.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { PushPin, Stack, CaretDown, Question } from '@phosphor-icons/react'
import { groupsFor } from '../../navigation/registry'
import { canPinModule, MAX_PINS } from './pins'
import { useDisclosure, moveFocus } from './useDisclosure'

export function ModulesMenu({ can, pins, onTogglePin, activeId, onOpenHelp }) {
  const { t } = useTranslation()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const menuRef = useRef(null)
  const [notice, setNotice] = useState('')
  const groups = groupsFor(can)
  const full = pins.length >= MAX_PINS
  const activeInMenu = groups.some(g => g.modules.some(m => m.id === activeId))
  const activeIsPinned = pins.includes(activeId)
  const links = () => [...(menuRef.current?.querySelectorAll('a[data-module]') || [])]

  useEffect(() => {
    if (open) links()[0]?.focus()
    else setNotice('')
  }, [open])

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

  // A refused fourth pin is explained in the menu, not by silence
  const pin = (id) => setNotice(onTogglePin(id) ? '' : t('shell.pinFull'))

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
        <CaretDown size={12} aria-hidden="true" />
      </button>
      <nav id="shell-modules-menu" ref={menuRef} className="shell-menu" aria-label={t('shell.modulesMenuLabel')} hidden={!open}>
        <div className="shell-menu-head">
          <strong>{t('shell.modulesMenuLabel')}</strong>
          <span>{t('shell.pinCount', { count: pins.length, max: MAX_PINS })}</span>
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
                  const label = t(m.labelKey)
                  return (
                    <li key={m.id} className={`shell-menu-item${current ? ' is-current' : ''}`}>
                      <Link to={m.path} data-module={m.id} aria-current={current ? 'page' : undefined}>
                        <Icon size={16} weight={current ? 'fill' : 'regular'} aria-hidden="true" />
                        <span>{label}</span>
                      </Link>
                      {canPinModule(m) && (
                        <button
                          type="button"
                          className="shell-pin"
                          aria-pressed={pinned}
                          aria-disabled={!pinned && full ? 'true' : undefined}
                          aria-label={t('shell.pinModule', { name: label })}
                          title={pinned ? t('shell.pinRemove') : full ? t('shell.pinFull') : t('shell.pinAdd')}
                          onClick={() => pin(m.id)}
                        >
                          <PushPin size={14} weight={pinned ? 'fill' : 'regular'} aria-hidden="true" />
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
          <p>{t('shell.pinHint')}</p>
          <p role="status" className="shell-menu-notice">{notice}</p>
          {onOpenHelp && (
            <button type="button" className="shell-link-button" onClick={() => { close(); onOpenHelp('navigation') }}>
              <Question size={14} aria-hidden="true" />{t('shell.navHelp')}
            </button>
          )}
        </div>
      </nav>
    </div>
  )
}
