/**
 * One detached window: a non-modal dialog over the page, moved by its title bar, resized by its
 * edges and corners, brought in front when touched, closed by its cross or Escape while it holds
 * the focus. Its move handle, at the start of the bar, answers the keyboard: arrows move it, Shift
 * and arrows resize it. Its maximize button, or a double-click on the bar, fills the work area and
 * gives back the place it had; maximized, it neither moves nor resizes.
 */
import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
import { keyRect, resizeRect, clampRect, viewport } from './geometry'

const EDGES = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
// A layer of its own inside the window (a menu, a dialog) answers Escape before the window does
const OWN_LAYER = 'dialog, [role="dialog"]:not([data-detached]), [role="alertdialog"], [role="menu"], [role="listbox"]'

export function DetachedWindow({ wkey, icon, kindLabel, title, rect, z, front, maximized = false, onPlace, onFront, onToggleMax, onClose, takeFocus, onFocused, children }) {
  const { t } = useTranslation()
  const ref = useRef(null)
  const titleId = `detached-title-${useId().replace(/:/g, '')}`
  // While a drag runs the window follows the pointer; the rect is stored when it ends
  const [live, setLive] = useState(null)
  const shown = live || rect

  useEffect(() => {
    if (!takeFocus) return
    ref.current?.querySelector('.float-handle:not(:disabled), [data-action="float-max"]')?.focus()
    onFocused?.()
  }, [takeFocus]) // eslint-disable-line react-hooks/exhaustive-deps

  // Maximized, the window holds still: no drag by its bar, its handle or an edge
  const drag = (e, step) => {
    if (maximized || (e.button !== undefined && e.button !== 0)) return
    e.preventDefault()
    onFront()
    const start = { x: e.clientX, y: e.clientY }
    let last = rect
    e.currentTarget.setPointerCapture?.(e.pointerId)
    const move = (ev) => {
      last = step(rect, ev.clientX - start.x, ev.clientY - start.y, viewport())
      setLive(last)
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      setLive(null)
      onPlace(last)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  const moveBy = (r, dx, dy, view) => clampRect({ ...r, x: r.x + dx, y: r.y + dy }, view)

  const onHandleKey = (e) => {
    const next = keyRect(rect, e.key, e.shiftKey, viewport())
    if (!next) return
    e.preventDefault()
    onPlace(next)
  }
  // The handle sleeps while maximized: the focus it held goes to the button that restores
  const toggleMax = () => {
    const held = !maximized && document.activeElement?.closest?.('.float-handle')
    onToggleMax?.()
    if (held) requestAnimationFrame(() => ref.current?.querySelector('[data-action="float-max"]')?.focus())
  }
  const onKeyDown = (e) => {
    if (e.key !== 'Escape' || e.defaultPrevented) return
    if (e.target.closest?.(OWN_LAYER)) return
    // Handled here: the dock under the window keeps its own Escape for the next press
    e.preventDefault()
    onClose()
  }

  return (
    <section ref={ref} className={['float-window', front && 'front', maximized && 'maximized'].filter(Boolean).join(' ')} role="dialog" aria-modal="false" aria-labelledby={titleId}
      data-detached={wkey} style={{ left: shown.x, top: shown.y, width: shown.w, height: shown.h, zIndex: z }}
      onPointerDownCapture={onFront} onFocusCapture={onFront} onKeyDown={onKeyDown}>
      <header className="float-head" onPointerDown={(e) => { if (!e.target.closest('button')) drag(e, moveBy) }}
        onDoubleClick={(e) => { if (!e.target.closest('button')) toggleMax() }}>
        <button type="button" className="icon-btn float-handle" data-action="float-move" disabled={maximized}
          aria-label={t('detached.moveHandle')} title={t('detached.moveHint')} aria-describedby={`${titleId}-hint`}
          onKeyDown={onHandleKey} onPointerDown={(e) => drag(e, moveBy)}>
          <Icon name="move" />
        </button>
        <span id={`${titleId}-hint`} className="sr-only">{t('detached.moveHint')}</span>
        {/* The bar names the type, the body under it the object: the window's name stays the object's for assistive technology */}
        <div className="float-title"><Icon name={icon} />
          <h2 id={titleId}>{kindLabel ? <><span aria-hidden="true">{kindLabel}</span><span className="sr-only">{title}</span></> : title}</h2>
        </div>
        <div className="float-tools">
          <button type="button" className="icon-btn" data-action="float-max" aria-label={t(maximized ? 'detached.restore' : 'detached.maximize')}
            title={t(maximized ? 'detached.restore' : 'detached.maximize')} onClick={toggleMax}>
            <Icon name={maximized ? 'restore' : 'expand'} />
          </button>
          <button type="button" className="icon-btn" data-action="float-close" aria-label={t('detached.close', { name: title })} onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
      </header>
      <div className="float-body">{children}</div>
      {!maximized && EDGES.map((edge) => (
        <div key={edge} className={`float-edge float-edge-${edge}`} data-edge={edge} aria-hidden="true"
          onPointerDown={(e) => drag(e, (r, dx, dy, view) => resizeRect(r, edge, dx, dy, view))} />
      ))}
    </section>
  )
}

export default DetachedWindow
