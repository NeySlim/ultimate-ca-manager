/**
 * InspectorDock: the bordered frame, in the page flow, that shows the objects
 * opened through the inspector context: under the list at the page margins, or
 * beside it on the right; full screen on mobile. Escape closes the active object;
 * the focus moves to the dock on opening and returns to the opening control when
 * the last object closes.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { X, CornersOut, CornersIn, SidebarSimple, Rows, Signpost, Minus, CaretUp } from '@phosphor-icons/react'
import { useInspector, SIZE_LIMITS } from '../../contexts/InspectorContext'
import { cn } from '../../lib/utils'
import { ObjectTabs } from './InspectorTabs'
import { InspectorObject } from './InspectorObject'
import { DockPlacementContext, RIGHT_MIN_VIEWPORT, useDockPlacement, useViewport } from './placement'
import './inspector.css'

const STEP = 24
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

export function InspectorDock() {
  const { t } = useTranslation()
  const ins = useInspector()
  const { opened, activeKey, setActiveKey, closeEntity, closeAll, focusToken, height, width, setGeometry, closeOnNav, toggleCloseOnNav, collapsed, setCollapsed } = ins
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

  if (!opened.length || !placement) return null
  const entry = opened.find((o) => o.key === activeKey) || opened[0]

  const mobile = placement === 'mobile'
  const right = placement === 'right'
  // The bottom dock never takes more than 60 % of the window height
  const maxH = Math.max(SIZE_LIMITS.height[0], Math.floor(viewport.h * 0.6))
  const shownH = clamp(height, SIZE_LIMITS.height[0], maxH)
  const shownW = clamp(width, SIZE_LIMITS.width[0], SIZE_LIMITS.width[1])
  const folded = collapsed && !mobile && !right
  const grown = right ? shownW >= 600 : shownH >= Math.min(maxH, 360)

  const resizeTo = (v, opts) => setGeometry(right
    ? { width: Math.round(clamp(v, ...SIZE_LIMITS.width)) }
    : { height: Math.round(clamp(v, SIZE_LIMITS.height[0], maxH)) }, opts)
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
    else if (e.key === 'Home') resizeTo(right ? SIZE_LIMITS.width[0] : SIZE_LIMITS.height[0])
    else if (e.key === 'End') resizeTo(right ? SIZE_LIMITS.width[1] : maxH)
    else return
    e.preventDefault()
  }

  // Escape closes the active object; an action modal keeps its own Escape
  const onKeyDown = (e) => {
    if (e.key !== 'Escape' || e.defaultPrevented || !dock.current?.contains(e.target)) return
    const inner = e.target.closest?.('[role="dialog"],[role="alertdialog"],[role="menu"]')
    if (inner && inner !== dock.current) return
    e.stopPropagation()
    closeEntity(entry.key)
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
      aria-valuemin={right ? SIZE_LIMITS.width[0] : SIZE_LIMITS.height[0]}
      aria-valuemax={right ? SIZE_LIMITS.width[1] : maxH}
      aria-valuenow={right ? shownW : shownH}
      onPointerDown={startDrag} onKeyDown={onGripKey} />
  )

  return (
    <aside ref={dock} data-testid="inspector-dock" aria-label={t('inspector.region')}
      {...(mobile ? { role: 'dialog', 'aria-modal': 'true' } : { role: 'region' })}
      onKeyDown={onKeyDown} style={style}
      className={cn('ins-dock', `is-${placement}`, folded && 'is-collapsed')}>
      {grip}
      <div className="ins-bar">
        <ObjectTabs opened={opened} activeKey={entry.key} titles={titles} onSelect={selectObject}
          onClose={closeEntity} tabMin={right ? 96 : 120} />
        <div className="ins-tools">
          <button type="button" className={cn('ins-icon-btn', closeOnNav && 'is-on')} onClick={toggleCloseOnNav}
            aria-pressed={closeOnNav} aria-label={t('inspector.closeOnNav')} title={t('inspector.closeOnNav')}>
            <Signpost size={15} weight={closeOnNav ? 'fill' : 'regular'} aria-hidden="true" />
          </button>
          {!mobile && viewport.w >= RIGHT_MIN_VIEWPORT && (
            <button type="button" className="ins-icon-btn" onClick={() => { setGeometry({ position: right ? 'bottom' : 'right' }); setCollapsed(false) }}
              aria-label={t(right ? 'inspector.dockBottom' : 'inspector.dockRight')} title={t(right ? 'inspector.dockBottom' : 'inspector.dockRight')}>
              {right ? <Rows size={15} aria-hidden="true" /> : <SidebarSimple size={15} weight="bold" aria-hidden="true" mirrored />}
            </button>
          )}
          {!mobile && (
            <button type="button" className="ins-icon-btn"
              onClick={() => { resizeTo(right ? (grown ? 460 : 640) : (grown ? 278 : maxH)); setCollapsed(false) }}
              aria-label={t(grown ? 'inspector.shrink' : 'inspector.grow')} title={t(grown ? 'inspector.shrink' : 'inspector.grow')}>
              {grown ? <CornersIn size={15} aria-hidden="true" /> : <CornersOut size={15} aria-hidden="true" />}
            </button>
          )}
          {!mobile && !right && (
            <button type="button" className="ins-icon-btn" onClick={() => setCollapsed(!collapsed)} aria-expanded={!folded}
              aria-label={t(folded ? 'inspector.expand' : 'inspector.collapse')} title={t(folded ? 'inspector.expand' : 'inspector.collapse')}>
              {folded ? <CaretUp size={15} aria-hidden="true" /> : <Minus size={15} aria-hidden="true" />}
            </button>
          )}
          <button type="button" className="ins-icon-btn" onClick={closeAll} aria-label={t('inspector.close')} title={t('inspector.close')}>
            <X size={15} aria-hidden="true" />
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
