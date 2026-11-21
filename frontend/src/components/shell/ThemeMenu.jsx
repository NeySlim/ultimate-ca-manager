/**
 * Theme menu, the mockup's themeMenu(): a menu button and its radio items (System, Dark, Light,
 * Aurore dark, Aurore light), the current one checked; a choice closes the menu and gives the
 * focus back to the button. These five are the product's themes. Shared with the sign-in pages.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
import { useTheme } from '../../contexts/ThemeContext'
import { useDisclosure, moveFocus } from './useDisclosure'

const CHOICES = [
  { id: 'system', family: 'atelier', mode: 'system', labelKey: 'shell.theme.system', icon: 'monitor' },
  { id: 'dark', family: 'atelier', mode: 'dark', labelKey: 'shell.theme.dark', icon: 'moon' },
  { id: 'light', family: 'atelier', mode: 'light', labelKey: 'shell.theme.light', icon: 'sun' },
  { id: 'aurore', family: 'aurore', mode: 'dark', labelKey: 'shell.theme.aurore', icon: 'sparkles' },
  { id: 'aurore-light', family: 'aurore', mode: 'light', labelKey: 'shell.theme.auroreLight', icon: 'sparkles' },
]

export function ThemeMenu() {
  const { t } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, resolvedMode } = useTheme()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  // Up arrow on the button opens on the last choice, down arrow on the current one
  const openOnLast = useRef(false)
  const items = () => [...(panelRef.current?.querySelectorAll('[role="menuitemradio"]') || [])]

  const modeName = t(resolvedMode === 'light' ? 'shell.theme.light' : 'shell.theme.dark')
  const current = CHOICES.find(c => c.family === themeFamily && c.mode === mode)
  const currentName = current?.id === 'system'
    ? `${t('shell.theme.system')} (${modeName.toLowerCase()})`
    : t(current?.labelKey || 'shell.theme.menu')
  // The button shows the applied theme: sparkles for Aurore, otherwise the resolved mode
  const buttonIcon = themeFamily === 'aurore' ? 'sparkles' : resolvedMode === 'light' ? 'sun' : 'moon'

  useEffect(() => {
    if (open) {
      const all = items()
      const target = openOnLast.current ? all[all.length - 1] : all.find(b => b.getAttribute('aria-checked') === 'true') || all[0]
      openOnLast.current = false
      target?.focus()
    }
  }, [open])

  const choose = (apply) => {
    apply()
    close(true)
  }

  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (e.defaultPrevented) return
    // Down or up arrow on the button opens the menu, as in the mockup
    if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && e.target === buttonRef.current) {
      e.preventDefault()
      openOnLast.current = e.key === 'ArrowUp'
      setOpen(true)
      return
    }
    if (!open || !panelRef.current?.contains(e.target)) return
    if (e.key === 'Tab') {
      e.preventDefault()
      close(true)
      return
    }
    moveFocus(e, items())
  }

  const label = t('shell.theme.label', { theme: currentName })
  return (
    <div className="pop-wrap theme-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="icon-btn quiet"
        id="theme-button"
        data-action="theme-menu"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="theme-menu"
        aria-label={label}
        title={label}
        data-mode={resolvedMode}
        onClick={() => setOpen(!open)}
      >
        <Icon name={buttonIcon} />
      </button>
      <ul className="pop-menu theme-menu" id="theme-menu" ref={panelRef} role="menu" aria-label={t('shell.theme.menu')} hidden={!open}>
        {CHOICES.map(({ id, family, mode: choiceMode, labelKey, icon }) => {
          const checked = themeFamily === family && mode === choiceMode
          return (
            <li key={id} role="none">
              <button type="button" role="menuitemradio" tabIndex={-1} aria-checked={checked} data-theme-choice={id}
                onClick={() => choose(() => { setThemeFamily(family); setMode(choiceMode) })}>
                <Icon name={icon} />
                <span className="pop-label">
                  {t(labelKey)}
                  {id === 'system' && <small>{t('shell.theme.systemNow', { mode: modeName.toLowerCase() })}</small>}
                </span>
                <span className="pop-check"><Icon name="check" /></span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
