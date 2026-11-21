/**
 * The mockup's modal(): a native <dialog> opened with showModal() (the browser holds the focus
 * inside and answers Escape), a head with the title and Fermer la fenêtre, then the body.
 * On close the focus goes back to the control that opened it (or the element that replaced it,
 * same id), else to `returnTo` (an id, the mockup's returnFallback), else to the page title.
 * size: 'narrow' (520 px), 'wide' (920 px) or none (760 px). skipReturn(): true when what the dialog
 * opened took the focus itself (the inspector), which then stays there.
 */
import { useContext, useEffect, useLayoutEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { AtlScopeContext } from './scope'
import { escapeYielded } from '../list/dialogEscape'

// Outside a zone the stylesheets come on demand: imported statically here they would join the
// shell's own sheet, ahead of its global rules, and lose to them (scope.css reverts at zero weight)
const loadSheets = () => Promise.all([
  import('../../styles/atelier/scope.css'), import('../../styles/atelier/maquette.css'), import('../../styles/atelier/extensions.css'),
])

export function AtelierDialog(props) {
  // Outside a zone (a dialog a page or the shell opens there), the dialog carries the zone's scope itself
  const inZone = useContext(AtlScopeContext)
  useEffect(() => { if (!inZone) loadSheets().catch(() => {}) }, [inZone])
  if (inZone) return <ModalDialog {...props} />
  return <div className="atl atl-island"><AtlScopeContext.Provider value><ModalDialog {...props} /></AtlScopeContext.Provider></div>
}

function ModalDialog({ title, subtitle, size = '', onClose, children, testId, returnTo, skipReturn }) {
  const { t } = useTranslation()
  const ref = useRef(null)
  const opener = useRef(null)
  const close = useRef(onClose)
  close.current = onClose
  const fallback = useRef(returnTo)
  fallback.current = returnTo
  const skip = useRef(skipReturn)
  skip.current = skipReturn

  useLayoutEffect(() => {
    const dialog = ref.current
    opener.current = document.activeElement
    if (typeof dialog.showModal === 'function') {
      try { dialog.showModal() } catch { dialog.setAttribute('open', '') }
    } else dialog.setAttribute('open', '')
    // A dialog may name its first field (data-autofocus), as the mockup's dialogs focus one after opening
    const named = dialog.querySelector('[data-autofocus]')
    if (named) named.focus()
    else if (!dialog.contains(document.activeElement)) dialog.querySelector('input,button')?.focus()
    return () => {
      if (dialog.open && typeof dialog.close === 'function') dialog.close()
      const back = opener.current
      if (skip.current?.()) return
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
