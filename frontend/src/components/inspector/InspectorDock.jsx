/**
 * InspectorDock: the frame, in the flow of the page, that shows the objects opened through
 * the inspector context: under the page, or beside it when docked on the right; full
 * screen on mobile. InspectorStage is the area it shares with the page.
 * Escape closes the active object; the focus moves to the dock on opening and returns to
 * the opening control when the last object closes.
 */
import { useContext, useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { X, CornersOut, CornersIn, SquareSplitHorizontal, SquareSplitVertical, Minus, CaretUp, Signpost } from '@phosphor-icons/react'
import { InspectorContext, useInspector, SIZE_LIMITS } from '../../contexts/InspectorContext'
import { useMobile } from '../../contexts/MobileContext'
import { cn } from '../../lib/utils'
import { ObjectTabs } from './InspectorTabs'
import { InspectorObject } from './InspectorObject'
import { entityState } from './entityState'
import { StatusPill } from '../list/StatusPill'
import './inspector.css'

const STEP = 20
// The right dock needs room for the page beside it: narrower windows fall back to the bottom
export const RIGHT_MIN_VIEWPORT = 1400
// Bottom dock: never above 60 % of the window, as its max-height says
const HEIGHT_CAP = 450
const HEIGHT_FLOOR = 210
// Sizes the size button switches between
const HEIGHT_SMALL = 278
const HEIGHT_LARGE = 420
const WIDTH_SMALL = 460
const WIDTH_LARGE = 640
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

function useViewport() {
  const [viewport, setViewport] = useState({ w: window.innerWidth, h: window.innerHeight })
  useEffect(() => {
    const onResize = () => setViewport({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return viewport
}

/** The page and the inspector side by side or one above the other; the status bar stays outside. */
export function InspectorStage({ children }) {
  // A shell mounted without the provider has nothing to dock
  const ins = useContext(InspectorContext)
  if (!ins) return <div className="insp-stage">{children}</div>
  return <DockedStage ins={ins}>{children}</DockedStage>
}

function DockedStage({ ins, children }) {
  const { isMobile } = useMobile()
  const viewport = useViewport()
  const right = !isMobile && ins.opened.length > 0 && ins.position === 'right' && viewport.w >= RIGHT_MIN_VIEWPORT
  return (
    <div className={cn('insp-stage', right && 'is-right')}>
      {children}
      <InspectorDock />
    </div>
  )
}

export function InspectorDock() {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const ins = useInspector()
  const { opened, activeKey, setActiveKey, closeEntity, closeAll, focusToken, position, height, width, setGeometry, closeOnNav, toggleCloseOnNav } = ins
  const [titles, setTitles] = useState({})
  const [collapsed, setCollapsed] = useState(false)
  const viewport = useViewport()
  const dock = useRef(null)
  const drag = useRef(null)

  // A new opening unfolds the dock and moves the focus to the active object's tab
  useEffect(() => {
    if (!focusToken) return
    setCollapsed(false)
    requestAnimationFrame(() => dock.current?.querySelector('[data-testid="inspector-object-tabs"] [aria-selected="true"]')?.focus())
  }, [focusToken])

  const onTitle = useCallback((key, title) => setTitles((prev) => (prev[key] === title ? prev : { ...prev, [key]: title })), [])

  if (!opened.length) return null
  const entry = opened.find((o) => o.key === activeKey) || opened[0]

  const right = !isMobile && position === 'right' && viewport.w >= RIGHT_MIN_VIEWPORT
  const maxH = Math.min(HEIGHT_CAP, Math.floor(viewport.h * 0.6))
  const minH = Math.min(HEIGHT_FLOOR, maxH)
  const [minW, maxW] = SIZE_LIMITS.width
  const shownH = clamp(height, minH, maxH)
  const shownW = clamp(width, minW, maxW)
  const grown = right ? shownW >= 600 : shownH >= 360
  const folded = collapsed && !isMobile && !right

  const resizeTo = (v, opts) => setGeometry(right ? { width: Math.round(clamp(v, minW, maxW)) } : { height: Math.round(clamp(v, minH, maxH)) }, opts)
  const startDrag = (e) => {
    e.preventDefault()
    drag.current = { from: right ? e.clientX : e.clientY, size: right ? shownW : shownH }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  const sizeAt = (e) => drag.current.size + drag.current.from - (right ? e.clientX : e.clientY)
  const moveDrag = (e) => { if (drag.current) resizeTo(sizeAt(e), { persist: false }) }
  const endDrag = (e) => {
    if (!drag.current) return
    resizeTo(sizeAt(e))
    drag.current = null
  }
  const onGripKey = (e) => {
    const cur = right ? shownW : shownH
    const to = {
      [right ? 'ArrowLeft' : 'ArrowUp']: cur + STEP,
      [right ? 'ArrowRight' : 'ArrowDown']: cur - STEP,
      Home: right ? minW : minH,
      End: right ? maxW : maxH,
    }[e.key]
    if (to === undefined) return
    e.preventDefault()
    setCollapsed(false)
    resizeTo(to)
  }

  // Escape closes the active object; an action modal keeps its own Escape
  const onKeyDown = (e) => {
    if (e.key !== 'Escape' || e.defaultPrevented || !dock.current?.contains(e.target)) return
    const inner = e.target.closest?.('[role="dialog"],[role="alertdialog"]')
    if (inner && inner !== dock.current) return
    e.stopPropagation()
    closeEntity(entry.key)
  }

  const select = (key) => { setCollapsed(false); setActiveKey(key) }
  const badge = (o) => {
    const state = entityState(o.type, o.data, t)
    return state ? <StatusPill {...state} /> : null
  }
  const sideLabel = t(right ? 'inspector.dockBottom' : 'inspector.dockRight')
  const sizeLabel = t(grown ? 'inspector.shrink' : 'inspector.grow')
  const foldLabel = t(folded ? 'inspector.unfold' : 'inspector.fold')

  return (
    <aside ref={dock} data-testid="inspector-dock" aria-label={t('inspector.region')}
      {...(isMobile ? { role: 'dialog', 'aria-modal': 'true' } : { role: 'region' })}
      onKeyDown={onKeyDown}
      style={isMobile ? undefined : { '--insp-h': `${shownH}px`, '--insp-w': `${shownW}px` }}
      className={cn('insp', isMobile ? 'is-mobile' : right ? 'is-right' : 'is-bottom', folded && 'is-collapsed')}>
      {!isMobile && (
        <div role="separator" tabIndex={0} data-testid="inspector-grip" className="insp-grip"
          aria-label={t(right ? 'inspector.resizeWidth' : 'inspector.resizeHeight')}
          aria-orientation={right ? 'vertical' : 'horizontal'}
          aria-valuemin={right ? minW : minH} aria-valuemax={right ? maxW : maxH} aria-valuenow={right ? shownW : shownH}
          onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}
          onKeyDown={onGripKey} />
      )}
      <div className="insp-strip">
        <ObjectTabs opened={opened} activeKey={entry.key} titles={titles} onSelect={select} onClose={closeEntity} badge={badge} />
        <div className="insp-tools">
          <button type="button" className="insp-tool" onClick={toggleCloseOnNav}
            aria-pressed={closeOnNav} aria-label={t('inspector.closeOnNav')} title={t('inspector.closeOnNav')}>
            <Signpost weight={closeOnNav ? 'fill' : 'regular'} aria-hidden="true" />
          </button>
          {!isMobile && viewport.w >= RIGHT_MIN_VIEWPORT && (
            <button type="button" className="insp-tool" aria-label={sideLabel} title={sideLabel}
              onClick={() => { setCollapsed(false); setGeometry({ position: right ? 'bottom' : 'right' }) }}>
              {right ? <SquareSplitVertical aria-hidden="true" /> : <SquareSplitHorizontal aria-hidden="true" />}
            </button>
          )}
          {!isMobile && (
            <button type="button" className="insp-tool" aria-label={sizeLabel} title={sizeLabel}
              onClick={() => {
                setCollapsed(false)
                resizeTo(right ? (grown ? WIDTH_SMALL : WIDTH_LARGE) : (grown ? HEIGHT_SMALL : Math.min(HEIGHT_LARGE, maxH)))
              }}>
              {grown ? <CornersIn aria-hidden="true" /> : <CornersOut aria-hidden="true" />}
            </button>
          )}
          {!isMobile && !right && (
            <button type="button" className="insp-tool" aria-expanded={!folded} aria-label={foldLabel} title={foldLabel}
              onClick={() => setCollapsed((v) => !v)}>
              {folded ? <CaretUp aria-hidden="true" /> : <Minus aria-hidden="true" />}
            </button>
          )}
          <button type="button" className="insp-tool" onClick={closeAll} aria-label={t('inspector.close')} title={t('inspector.close')}>
            <X aria-hidden="true" />
          </button>
        </div>
      </div>
      {!folded && <InspectorObject key={entry.key} entry={entry} onTitle={onTitle} layout={right || isMobile ? 'column' : 'columns'} />}
    </aside>
  )
}
