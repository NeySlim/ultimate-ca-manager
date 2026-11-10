/**
 * Theme menu of the top bar: family and mode, from the same ThemeContext (and
 * server preference) as the Appearance settings. The icon shows the applied mode.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Sun, Moon, Check } from '@phosphor-icons/react'
import { useTheme } from '../../contexts/ThemeContext'
import { useDisclosure, moveFocus } from './useDisclosure'

const MODES = [
  { id: 'system', labelKey: 'settings.followSystem' },
  { id: 'dark', labelKey: 'settings.dark' },
  { id: 'light', labelKey: 'settings.light' },
]

export function ThemeMenu() {
  const { t } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, resolvedMode, themes } = useTheme()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  const items = () => [...(panelRef.current?.querySelectorAll('button') || [])]
  const Icon = resolvedMode === 'light' ? Sun : Moon

  useEffect(() => {
    if (open) {
      const all = items()
      ;(all.find(b => b.getAttribute('aria-checked') === 'true') || all[0])?.focus()
    }
  }, [open])

  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (e.defaultPrevented || !open || !panelRef.current?.contains(e.target)) return
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
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="shell-theme-menu"
        aria-label={t('shell.theme.menu')}
        title={t('shell.theme.menu')}
        onClick={() => setOpen(!open)}
      >
        <Icon size={18} aria-hidden="true" data-mode={resolvedMode} />
      </button>
      <div id="shell-theme-menu" ref={panelRef} className="shell-pop" hidden={!open}>
        <div role="radiogroup" aria-label={t('settings.colorTheme')} className="shell-pop-group shell-pop-first">
          <span className="shell-pop-label" aria-hidden="true">{t('settings.colorTheme')}</span>
          {themes.map(theme => (
            <button key={theme.id} type="button" role="radio" aria-checked={themeFamily === theme.id}
              className="shell-pop-item" onClick={() => setThemeFamily(theme.id)}>
              <span className="shell-swatch" style={{ background: theme.accent }} aria-hidden="true" />
              <span className="shell-grow">{t(theme.nameKey)}</span>
              {themeFamily === theme.id && <Check size={14} weight="bold" aria-hidden="true" />}
            </button>
          ))}
        </div>
        <div role="radiogroup" aria-label={t('settings.appearanceMode')} className="shell-pop-group">
          <span className="shell-pop-label" aria-hidden="true">{t('settings.appearanceMode')}</span>
          {MODES.map(opt => (
            <button key={opt.id} type="button" role="radio" aria-checked={mode === opt.id}
              className="shell-pop-item" onClick={() => setMode(opt.id)}>
              <span className="shell-grow">{t(opt.labelKey)}</span>
              {mode === opt.id && <Check size={14} weight="bold" aria-hidden="true" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
