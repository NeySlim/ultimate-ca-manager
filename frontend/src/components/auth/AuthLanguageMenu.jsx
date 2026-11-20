/**
 * Language choice of the pages shown before sign-in, beside the theme menu and in its grammar
 * (220 px panel, menu items with a radio state, the current one checked, arrows on the button):
 * the choice is kept in this browser and applies at once.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Translate, Check } from '@phosphor-icons/react'
import { languages } from '../../i18n'
import { useDisclosure, moveFocus } from '../shell/useDisclosure'

export function AuthLanguageMenu() {
  const { t, i18n } = useTranslation()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const panelRef = useRef(null)
  // Up arrow on the button opens on the last choice, down arrow on the current one
  const openOnLast = useRef(false)
  const current = i18n.language?.split('-')[0] || 'en'
  const items = () => [...(panelRef.current?.querySelectorAll('[role="menuitemradio"]') || [])]

  useEffect(() => {
    if (open) {
      const all = items()
      const target = openOnLast.current ? all[all.length - 1] : all.find(b => b.getAttribute('aria-checked') === 'true') || all[0]
      openOnLast.current = false
      target?.focus()
    }
  }, [open])

  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (e.defaultPrevented) return
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

  const pick = (code) => {
    i18n.changeLanguage(code)
    try { localStorage.setItem('i18nextLng', code) } catch { /* storage is optional */ }
    close(true)
  }

  return (
    <div className="shell-pop-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="shell-icon-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="auth-language-menu"
        aria-label={t('settings.language')}
        title={t('settings.language')}
        onClick={() => setOpen(!open)}
      >
        <Translate size={18} aria-hidden="true" />
      </button>
      <div id="auth-language-menu" ref={panelRef} className="shell-pop ui-theme-menu" role="menu"
        aria-label={t('settings.language')} hidden={!open}>
        {languages.map(l => (
          <button key={l.code} type="button" role="menuitemradio" tabIndex={-1} aria-checked={current === l.code}
            className="ui-pop-item" lang={l.code} onClick={() => pick(l.code)}>
            <span className="auth-lang-flag" aria-hidden="true">{l.flag}</span>
            <span className="ui-pop-label">{l.name}</span>
            <span className="ui-pop-check" aria-hidden="true"><Check /></span>
          </button>
        ))}
      </div>
    </div>
  )
}
