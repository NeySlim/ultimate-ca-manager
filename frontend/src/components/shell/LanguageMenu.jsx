/**
 * Language menu of the bar and of the sign-in pages, beside the theme menu and in the grammar of
 * the mockup's themeMenu(): `.pop-wrap`, a quiet icon button, `ul.pop-menu.theme-menu` of radio
 * items, the current one checked, arrows on the button. A choice takes the account preferences'
 * path (chooseLanguage): this browser, and the account once signed in.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
import { languages } from '../../i18n'
import { chooseLanguage } from '../../lib/chooseLanguage'
import { useDisclosure, moveFocus } from './useDisclosure'

export function LanguageMenu() {
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
    chooseLanguage(i18n, code)
    close(true)
  }

  return (
    <div className="pop-wrap language-wrap" {...rootProps} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={buttonRef}
        className="icon-btn quiet"
        id="language-button"
        data-action="language-menu"
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
