/**
 * Language choice of the pages shown before sign-in, beside the theme menu and in the grammar
 * of the mockup's themeMenu(): `.pop-wrap`, a quiet icon button, `ul.pop-menu.theme-menu` of
 * radio items, the current one checked, arrows on the button. The choice is kept in this browser.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
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
    <div className="pop-wrap language-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="icon-btn quiet"
        id="language-button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="language-menu"
        aria-label={t('settings.language')}
        title={t('settings.language')}
        onClick={() => setOpen(!open)}
      >
        <Icon name="globe" />
      </button>
      <ul id="language-menu" ref={panelRef} className="pop-menu theme-menu" role="menu"
        aria-label={t('settings.language')} hidden={!open}>
        {languages.map(l => (
          <li key={l.code} role="none">
            <button type="button" role="menuitemradio" tabIndex={-1} aria-checked={current === l.code}
              lang={l.code} onClick={() => pick(l.code)}>
              <span className="lang-flag" aria-hidden="true">{l.flag}</span>
              <span className="pop-label">{l.name}</span>
              <span className="pop-check"><Icon name="check" /></span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
