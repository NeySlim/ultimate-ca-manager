/**
 * Language choice of the pages shown before sign-in, beside the theme menu:
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
  const current = i18n.language?.split('-')[0] || 'en'
  const items = () => [...(panelRef.current?.querySelectorAll('button') || [])]

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
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="auth-language-menu"
        aria-label={t('settings.language')}
        title={t('settings.language')}
        onClick={() => setOpen(!open)}
      >
        <Translate size={18} aria-hidden="true" />
      </button>
      <div id="auth-language-menu" ref={panelRef} className="shell-pop" hidden={!open}>
        <div role="radiogroup" aria-label={t('settings.language')}>
          {languages.map(l => (
            <button key={l.code} type="button" role="radio" aria-checked={current === l.code}
              className="shell-pop-item" lang={l.code} onClick={() => pick(l.code)}>
              <span aria-hidden="true">{l.flag}</span>
              <span className="shell-grow">{l.name}</span>
              {current === l.code && <Check size={14} weight="bold" aria-hidden="true" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
