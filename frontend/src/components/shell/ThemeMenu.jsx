/**
 * Theme menu of the top bar, as the mockup's: 220 px, one choice per line with its icon
 * (System, Dark, Light, Aurore dark, Aurore light), the current one checked; a choice closes
 * the menu and gives the focus back to the button. The product's other families follow.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Desktop, Moon, Sun, Sparkle, Palette, Check } from '@phosphor-icons/react'
import { useTheme } from '../../contexts/ThemeContext'
import { useDisclosure, moveFocus } from './useDisclosure'

const CHOICES = [
  { id: 'system', family: 'atelier', mode: 'system', labelKey: 'shell.theme.system', Icon: Desktop },
  { id: 'dark', family: 'atelier', mode: 'dark', labelKey: 'shell.theme.dark', Icon: Moon },
  { id: 'light', family: 'atelier', mode: 'light', labelKey: 'shell.theme.light', Icon: Sun },
  { id: 'aurore', family: 'aurore', mode: 'dark', labelKey: 'shell.theme.aurore', Icon: Sparkle },
  { id: 'aurore-light', family: 'aurore', mode: 'light', labelKey: 'shell.theme.auroreLight', Icon: Sparkle },
]
const MAIN_FAMILIES = new Set(['atelier', 'aurore'])

export function ThemeMenu() {
  const { t } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, resolvedMode, themes } = useTheme()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  const items = () => [...(panelRef.current?.querySelectorAll('[role="menuitemradio"]') || [])]

  const modeName = t(resolvedMode === 'light' ? 'shell.theme.light' : 'shell.theme.dark')
  const current = CHOICES.find(c => c.family === themeFamily && c.mode === mode)
  const currentName = current?.id === 'system'
    ? `${t('shell.theme.system')} (${modeName.toLowerCase()})`
    : current ? t(current.labelKey) : t((themes.find(th => th.id === themeFamily) || {}).nameKey || 'shell.theme.menu')
  // The button shows the applied theme: sparkles for Aurore, otherwise the resolved mode
  const ButtonIcon = themeFamily === 'aurore' ? Sparkle : resolvedMode === 'light' ? Sun : Moon

  useEffect(() => {
    if (open) {
      const all = items()
      ;(all.find(b => b.getAttribute('aria-checked') === 'true') || all[0])?.focus()
    }
  }, [open])

  const choose = (apply) => {
    apply()
    close(true)
  }

  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (e.defaultPrevented) return
    // Down arrow on the button opens the menu, as in the mockup
    if (!open && e.key === 'ArrowDown' && e.target === buttonRef.current) {
      e.preventDefault()
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

  const others = themes.filter(th => !MAIN_FAMILIES.has(th.id))

  return (
    <div className="shell-pop-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="shell-icon-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="shell-theme-menu"
        aria-label={t('shell.theme.menu')}
        title={t('shell.theme.current', { name: currentName })}
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
        {others.length > 0 && (
          <div role="group" aria-label={t('shell.theme.more')}>
            <div className="ui-pop-sep" role="separator" />
            {others.map(theme => {
              const checked = themeFamily === theme.id
              return (
                <button key={theme.id} type="button" role="menuitemradio" tabIndex={-1} aria-checked={checked}
                  className="ui-pop-item" onClick={() => choose(() => setThemeFamily(theme.id))}>
                  <Palette aria-hidden="true" />
                  <span className="ui-pop-label">{t(theme.nameKey)}</span>
                  <span className="ui-pop-check" aria-hidden="true"><Check /></span>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
