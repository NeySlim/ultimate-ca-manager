/**
 * InspectorDock: the bordered frame, in the page flow, that shows the objects
 * opened through the inspector context: under the list at the page margins, or
 * beside it on the right; full screen on mobile. Escape closes the inspector from
 * anywhere on the page, unless a dialog or menu is open; the focus moves to the dock
 * on opening and returns to the opening control when it closes.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { X, SidebarSimple, Rows, Minus, CaretUp } from '@phosphor-icons/react'
import { useInspector, SIZE_LIMITS, DOCK_HEIGHT } from '../../contexts/InspectorContext'
import { ExpandIcon } from '../list/atelierIcons'
import { cn } from '../../lib/utils'
import { ObjectTabs } from './InspectorTabs'
import { InspectorObject } from './InspectorObject'
import { DockPlacementContext, RIGHT_MIN_VIEWPORT, useDockPlacement, useViewport } from './placement'
import './inspector.css'

// Arrow keys on the grip move the edge by 20 px, as the mockup does
const STEP = 20
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
// Another layer that answers Escape itself: a modal, a menu, a listbox, a popover
const OWN_ESCAPE = '[role="dialog"][aria-modal="true"]:not([data-testid="inspector-dock"]), [role="alertdialog"], [role="menu"], [role="listbox"], [data-radix-popper-content-wrapper]'

// A closed menu of the shell stays mounted under [hidden]: only a shown layer counts
const ownLayerOpen = () => [...document.querySelectorAll(OWN_ESCAPE)].some((el) => !el.closest('[hidden]'))

export function InspectorDock() {
  const { t } = useTranslation()
  const ins = useInspector()
  const { opened, activeKey, setActiveKey, closeEntity, closeAll, focusToken, height, width, setGeometry, collapsed, setCollapsed } = ins
  const placement = useDockPlacement()
  const viewport = useViewport()
  const [titles, setTitles] = useState({})
  const dock = useRef(null)

  // A new opening moves the focus to the active object's tab
  useEffect(() => {
    if (!focusToken) return
    requestAnimationFrame(() => dock.current?.querySelector('[data-testid="inspector-object-tabs"] [aria-selected="true"]')?.focus())
  }, [focusToken])

  const onTitle = useCallback((key, title) => setTitles((prev) => (prev[key] === title ? prev : { ...prev, [key]: title })), [])

  // Escape closes the whole inspector wherever the focus is; a layer that answers Escape itself keeps it
  const shown = opened.length > 0 && !!placement
  useEffect(() => {
    if (!shown) return undefined
    const onKey = (e) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      if (ownLayerOpen()) return
      if (e.target.closest?.(OWN_ESCAPE)) return
      closeAll({ refocus: true })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [shown, closeAll])

  if (!shown) return null
  const entry = opened.find((o) => o.key === activeKey) || opened[0]

  const mobile = placement === 'mobile'
  const right = placement === 'right'
  // The bottom dock keeps 210 to 450 px, and never more than 60 % of the window height
  const maxH = Math.min(DOCK_HEIGHT.max, Math.floor(viewport.h * 0.6))
  const minH = Math.min(DOCK_HEIGHT.min, maxH)
  const shownH = clamp(height, minH, maxH)
  const shownW = clamp(width, SIZE_LIMITS.width[0], SIZE_LIMITS.width[1])
  const folded = collapsed && !mobile && !right
  const grown = right ? shownW >= 600 : shownH >= 360

  const resizeTo = (v, opts) => setGeometry(right
    ? { width: Math.round(clamp(v, ...SIZE_LIMITS.width)) }
    : { height: Math.round(clamp(v, minH, maxH)) }, opts)
  // The dock edge follows the pointer: its distance to the window edge, less the margins of the frame
  const edge = (ev) => (right ? window.innerWidth - ev.clientX - 24 : dock.current.getBoundingClientRect().bottom - ev.clientY)
  const startDrag = (e) => {
    e.preventDefault()
    const move = (ev) => resizeTo(edge(ev), { persist: false })
    const up = (ev) => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      resizeTo(edge(ev))
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  const onGripKey = (e) => {
    const grow = right ? 'ArrowLeft' : 'ArrowUp'
    const shrink = right ? 'ArrowRight' : 'ArrowDown'
    const cur = right ? shownW : shownH
    if (e.key === grow) resizeTo(cur + STEP)
    else if (e.key === shrink) resizeTo(cur - STEP)
    else if (e.key === 'Home') resizeTo(right ? SIZE_LIMITS.width[0] : minH)
    else if (e.key === 'End') resizeTo(right ? SIZE_LIMITS.width[1] : maxH)
    else return
    e.preventDefault()
  }

  const selectObject = (key) => {
    setActiveKey(key)
    setCollapsed(false)
  }

  const style = mobile ? undefined : right ? { width: shownW } : folded ? undefined : { height: shownH }
  const grip = mobile || folded ? null : (
    <div role="separator" tabIndex={0} data-testid="inspector-grip" className="ins-grip"
      aria-label={t(right ? 'inspector.resizeWidth' : 'inspector.resizeHeight')}
      aria-orientation={right ? 'vertical' : 'horizontal'}
      aria-valuemin={right ? SIZE_LIMITS.width[0] : minH}
      aria-valuemax={right ? SIZE_LIMITS.width[1] : maxH}
      aria-valuenow={right ? shownW : shownH}
      onPointerDown={startDrag} onKeyDown={onGripKey} />
  )

  // All certificates: the names say so (« Inspecteur de certificat », « Certificats ouverts »)
  const certs = opened.every((o) => o.type === 'certificate')
  return (
    <aside ref={dock} data-testid="inspector-dock" aria-label={t(certs ? 'inspector.regionCertificate' : 'inspector.region')}
      {...(mobile ? { role: 'dialog', 'aria-modal': 'true' } : { role: 'region' })}
      style={style}
      className={cn('ins-dock', `is-${placement}`, folded && 'is-collapsed')}>
      {grip}
      <div className="ins-bar">
        <ObjectTabs opened={opened} activeKey={entry.key} titles={titles} onSelect={selectObject}
          onClose={closeEntity} tabMin={right ? 96 : 120} certificates={certs} />
        <div className="ins-tools">
          {!mobile && viewport.w >= RIGHT_MIN_VIEWPORT && (
            <button type="button" className="ins-icon-btn" onClick={() => { setGeometry({ position: right ? 'bottom' : 'right' }); setCollapsed(false) }}
              aria-label={t(right ? 'inspector.dockBottom' : 'inspector.dockRight')} title={t(right ? 'inspector.dockBottom' : 'inspector.dockRight')}>
              {right ? <Rows size={16} aria-hidden="true" /> : <SidebarSimple size={16} weight="bold" aria-hidden="true" mirrored />}
            </button>
          )}
          {!mobile && (
            <button type="button" className="ins-icon-btn"
              onClick={() => { resizeTo(right ? (grown ? 460 : 640) : (grown ? 278 : DOCK_HEIGHT.grown)); setCollapsed(false) }}
              aria-label={t(grown ? 'inspector.shrink' : 'inspector.grow')} title={t(right ? 'inspector.changeWidth' : 'inspector.changeHeight')}>
              <ExpandIcon size={16} />
            </button>
          )}
          {!mobile && !right && (
            <button type="button" className="ins-icon-btn" onClick={() => setCollapsed(!collapsed)} aria-expanded={!folded}
              aria-label={t(folded ? 'inspector.expand' : 'inspector.collapse')} title={t(folded ? 'inspector.expand' : 'inspector.collapse')}>
              {folded ? <CaretUp size={16} aria-hidden="true" /> : <Minus size={16} aria-hidden="true" />}
            </button>
          )}
          <button type="button" className="ins-icon-btn" onClick={() => closeAll({ refocus: true })} aria-label={t('inspector.close')} title={t('inspector.close')}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      </div>
      <DockPlacementContext.Provider value={placement}>
        <div className="ins-body" hidden={folded}>
          <InspectorObject key={entry.key} entry={entry} onTitle={onTitle} />
        </div>
      </DockPlacementContext.Provider>
    </aside>
  )
}
