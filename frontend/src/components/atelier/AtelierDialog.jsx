/**
 * The mockup's modal(): a native <dialog> opened with showModal() (the browser holds the focus
 * inside and answers Escape), a head with the title and Fermer la fenêtre, then the body.
 * On close the focus goes back to the control that opened it (or the element that replaced it,
 * same id), else to `returnTo` (an id, the mockup's returnFallback), else to the page title.
 * size: 'narrow' (520 px), 'wide' (920 px) or none (760 px).
 */
import { useEffect, useLayoutEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { escapeYielded } from '../list/dialogEscape'

export function AtelierDialog({ title, subtitle, size = '', onClose, children, testId, returnTo }) {
  const { t } = useTranslation()
  const ref = useRef(null)
  const opener = useRef(null)
  const close = useRef(onClose)
  close.current = onClose
  const fallback = useRef(returnTo)
  fallback.current = returnTo

  useLayoutEffect(() => {
    const dialog = ref.current
    opener.current = document.activeElement
    if (typeof dialog.showModal === 'function') {
      try { dialog.showModal() } catch { dialog.setAttribute('open', '') }
    } else dialog.setAttribute('open', '')
    if (!dialog.contains(document.activeElement)) dialog.querySelector('input,button')?.focus()
    return () => {
      if (dialog.open && typeof dialog.close === 'function') dialog.close()
      const back = opener.current
      // after React has committed: the opener may be replaced by an element with the same id
      requestAnimationFrame(() => {
        const candidates = [back, back?.id && document.getElementById(back.id), fallback.current && document.getElementById(fallback.current)]
        for (const el of candidates) {
          if (!el?.isConnected || el === document.body) continue
          el.focus()
          if (document.activeElement === el) return
        }
        document.getElementById('main-title')?.focus()
      })
    }
  }, [])

  // Escape: the browser fires cancel; the page decides (it unmounts the dialog)
  useEffect(() => {
    const dialog = ref.current
    const onCancel = (e) => { e.preventDefault(); close.current?.() }
    dialog.addEventListener('cancel', onCancel)
    return () => dialog.removeEventListener('cancel', onCancel)
  }, [])

  return (
    <dialog ref={ref} className={size} aria-labelledby="modal-title" role="dialog" aria-modal="true" data-testid={testId}
      onKeyDown={(e) => {
        // A toast above the dialog yields an Escape typed here (marked, already prevented)
        if (e.key === 'Escape' && (!e.defaultPrevented || escapeYielded(e.nativeEvent))) { e.preventDefault(); close.current?.() }
      }}>
      <header className="modal-head">
        <div>
          <h2 id="modal-title">{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button type="button" className="icon-btn quiet" data-action="close-modal" aria-label={t('common.closeWindow')} onClick={() => close.current?.()}>
          <Icon name="close" />
        </button>
      </header>
      <div className="modal-body">{children}</div>
    </dialog>
  )
}

export default AtelierDialog
