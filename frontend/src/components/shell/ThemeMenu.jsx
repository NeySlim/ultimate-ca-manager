/**
 * Theme menu, the mockup's themeMenu(): a menu button and its radio items, the current ones checked; a
 * choice closes the menu and gives the focus back to the button. Deviation: the family (Atelier, Aurore)
 * and the mode (System, Dark, Light) are two independent groups, so System follows the OS in either
 * family. Shared with the sign-in pages.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
import { useTheme } from '../../contexts/ThemeContext'
import { useDisclosure, moveFocus } from './useDisclosure'

// The two families, each shown by its accent's swatch, as the account preferences show them
const FAMILIES = [
  { id: 'atelier', labelKey: 'settings.themeFamilies.atelier' },
  { id: 'aurore', labelKey: 'settings.themeFamilies.aurore' },
]
const MODES = [
  { id: 'system', labelKey: 'shell.theme.system', icon: 'monitor' },
  { id: 'dark', labelKey: 'shell.theme.dark', icon: 'moon' },
  { id: 'light', labelKey: 'shell.theme.light', icon: 'sun' },
]

export function ThemeMenu() {
  const { t } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, resolvedMode, themes = [] } = useTheme()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  // Up arrow on the button opens on the last choice, down arrow on the current one
  const openOnLast = useRef(false)
  const items = () => [...(panelRef.current?.querySelectorAll('[role="menuitemradio"]') || [])]

  const modeName = t(resolvedMode === 'light' ? 'shell.theme.light' : 'shell.theme.dark')
  const family = FAMILIES.find(f => f.id === themeFamily) || FAMILIES[0]
  const modeLabel = mode === 'system' ? `${t('shell.theme.system')} (${modeName.toLowerCase()})` : modeName
  const currentName = `${t(family.labelKey)}, ${modeLabel}`
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
        {/* Two radio groups, each named by its visible title; a separator between them */}
        <li role="none">
          <span className="pop-group-title" id="theme-family-title" aria-hidden="true">{t('shell.theme.family')}</span>
          <ul role="group" aria-labelledby="theme-family-title">
            {FAMILIES.map(({ id, labelKey }) => (
              <li key={id} role="none">
                <button type="button" role="menuitemradio" tabIndex={-1} aria-checked={themeFamily === id} data-theme-family={id}
                  onClick={() => choose(() => setThemeFamily(id))}>
                  <span className="swatch" style={{ background: themes.find(th => th.id === id)?.accent }} aria-hidden="true" />
                  <span className="pop-label">{t(labelKey)}</span>
                  <span className="pop-check"><Icon name="check" /></span>
                </button>
              </li>
            ))}
          </ul>
        </li>
        <li role="separator" className="pop-sep" />
        <li role="none">
          <span className="pop-group-title" id="theme-mode-title" aria-hidden="true">{t('shell.theme.mode')}</span>
          <ul role="group" aria-labelledby="theme-mode-title">
            {MODES.map(({ id, labelKey, icon }) => (
              <li key={id} role="none">
                <button type="button" role="menuitemradio" tabIndex={-1} aria-checked={mode === id} data-theme-mode={id}
                  onClick={() => choose(() => setMode(id))}>
                  <Icon name={icon} />
                  <span className="pop-label">
                    {t(labelKey)}
                    {id === 'system' && <small>{t('shell.theme.systemNow', { mode: modeName.toLowerCase() })}</small>}
                  </span>
                  <span className="pop-check"><Icon name="check" /></span>
                </button>
              </li>
            ))}
          </ul>
        </li>
      </ul>
    </div>
  )
}
