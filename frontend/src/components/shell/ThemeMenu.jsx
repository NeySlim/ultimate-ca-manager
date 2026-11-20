/**
 * Theme menu of the top bar, as the mockup's: 220 px, one choice per line with its icon
 * (System, Dark, Light, Aurore dark, Aurore light), the current one checked; a choice closes
 * the menu and gives the focus back to the button. Nothing else: these five are the product's themes.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Desktop, Moon, Sun, Sparkle, Check } from '@phosphor-icons/react'
import { useTheme } from '../../contexts/ThemeContext'
import { useDisclosure, moveFocus } from './useDisclosure'

const CHOICES = [
  { id: 'system', family: 'atelier', mode: 'system', labelKey: 'shell.theme.system', Icon: Desktop },
  { id: 'dark', family: 'atelier', mode: 'dark', labelKey: 'shell.theme.dark', Icon: Moon },
  { id: 'light', family: 'atelier', mode: 'light', labelKey: 'shell.theme.light', Icon: Sun },
  { id: 'aurore', family: 'aurore', mode: 'dark', labelKey: 'shell.theme.aurore', Icon: Sparkle },
  { id: 'aurore-light', family: 'aurore', mode: 'light', labelKey: 'shell.theme.auroreLight', Icon: Sparkle },
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
  const ButtonIcon = themeFamily === 'aurore' ? Sparkle : resolvedMode === 'light' ? Sun : Moon

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

  return (
    <div className="shell-pop-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="shell-icon-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="shell-theme-menu"
        aria-label={t('shell.theme.label', { theme: currentName })}
        title={t('shell.theme.label', { theme: currentName })}
        onClick={() => setOpen(!open)}
      >
        <ButtonIcon size={16} aria-hidden="true" data-mode={resolvedMode} />
      </button>
      <div id="shell-theme-menu" ref={panelRef} className="shell-pop ui-theme-menu" role="menu"
        aria-label={t('shell.theme.menu')} hidden={!open}>
        {CHOICES.map(({ id, family, mode: choiceMode, labelKey, Icon }) => {
          const checked = themeFamily === family && mode === choiceMode
          return (
            <button key={id} type="button" role="menuitemradio" tabIndex={-1} aria-checked={checked}
              className="ui-pop-item" onClick={() => choose(() => { setThemeFamily(family); setMode(choiceMode) })}>
              <Icon aria-hidden="true" />
              <span className="ui-pop-label">
                {t(labelKey)}
                {id === 'system' && <small>{t('shell.theme.systemNow', { mode: modeName.toLowerCase() })}</small>}
              </span>
              <span className="ui-pop-check" aria-hidden="true"><Check /></span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
