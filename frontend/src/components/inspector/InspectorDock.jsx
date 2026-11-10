/**
 * InspectorDock: the region anchored at the bottom or on the right that shows
 * the objects opened through the inspector context. Full screen on mobile.
 * Escape closes the active object; the focus moves to the dock on opening and
 * returns to the opening control when the last object closes.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { X, ArrowsOutSimple, ArrowsInSimple, SidebarSimple, Rows } from '@phosphor-icons/react'
import { useInspector, SIZE_LIMITS } from '../../contexts/InspectorContext'
import { useMobile } from '../../contexts/MobileContext'
import { cn } from '../../lib/utils'
import { ObjectTabs } from './InspectorTabs'
import { InspectorObject } from './InspectorObject'

const STEP = 24
const RIGHT_MIN_VIEWPORT = 1400
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

export function InspectorDock() {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const ins = useInspector()
  const { opened, activeKey, setActiveKey, closeEntity, closeAll, focusToken, position, height, width, setGeometry } = ins
  const [titles, setTitles] = useState({})
  const [viewport, setViewport] = useState({ w: window.innerWidth, h: window.innerHeight })
  const dock = useRef(null)

  useEffect(() => {
    const onResize = () => setViewport({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  // A new opening moves the focus to the active object's tab
  useEffect(() => {
    if (!focusToken) return
    requestAnimationFrame(() => dock.current?.querySelector('[data-testid="inspector-object-tabs"] [aria-selected="true"]')?.focus())
  }, [focusToken])

  const onTitle = useCallback((key, title) => setTitles((prev) => (prev[key] === title ? prev : { ...prev, [key]: title })), [])

  if (!opened.length) return null
  const entry = opened.find((o) => o.key === activeKey) || opened[0]

  // The right dock needs room for the page beside it: narrower windows fall back to the bottom
  const right = !isMobile && position === 'right' && viewport.w >= RIGHT_MIN_VIEWPORT
  const maxH = Math.floor(viewport.h * 0.6)
  const shownH = clamp(height, SIZE_LIMITS.height[0], Math.max(SIZE_LIMITS.height[0], maxH))
  const shownW = clamp(width, SIZE_LIMITS.width[0], SIZE_LIMITS.width[1])
  const grown = right ? shownW >= 600 : shownH >= 360

  const resizeTo = (v, opts) => setGeometry(right ? { width: Math.round(clamp(v, ...SIZE_LIMITS.width)) } : { height: Math.round(clamp(v, SIZE_LIMITS.height[0], Math.max(SIZE_LIMITS.height[0], maxH))) }, opts)
  const startDrag = (e) => {
    e.preventDefault()
    const move = (ev) => resizeTo(right ? window.innerWidth - ev.clientX : window.innerHeight - ev.clientY, { persist: false })
    const up = (ev) => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      resizeTo(right ? window.innerWidth - ev.clientX : window.innerHeight - ev.clientY)
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
    else return
    e.preventDefault()
  }

  // Escape closes the active object; an action modal keeps its own Escape
  const onKeyDown = (e) => {
    if (e.key !== 'Escape' || e.defaultPrevented || !dock.current?.contains(e.target)) return
    const inner = e.target.closest?.('[role="dialog"],[role="alertdialog"]')
    if (inner && inner !== dock.current) return
    e.stopPropagation()
    closeEntity(entry.key)
  }

  const style = isMobile ? undefined : right ? { width: shownW } : { height: shownH }
  const grip = isMobile ? null : (
    <div role="separator" tabIndex={0} data-testid="inspector-grip"
      aria-label={t(right ? 'inspector.resizeWidth' : 'inspector.resizeHeight')}
      aria-orientation={right ? 'vertical' : 'horizontal'}
      aria-valuemin={right ? SIZE_LIMITS.width[0] : SIZE_LIMITS.height[0]}
      aria-valuemax={right ? SIZE_LIMITS.width[1] : Math.max(SIZE_LIMITS.height[0], maxH)}
      aria-valuenow={right ? shownW : shownH}
      onPointerDown={startDrag} onKeyDown={onGripKey}
      className={cn('shrink-0 bg-border-op50 hover:bg-accent-primary focus-visible:bg-accent-primary',
        right ? 'w-1 cursor-col-resize' : 'h-1 cursor-row-resize')} />
  )
  const tool = 'p-1.5 rounded text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary'

  return (
    <>
      <aside ref={dock} data-testid="inspector-dock" aria-label={t('inspector.region')}
        {...(isMobile ? { role: 'dialog', 'aria-modal': 'true' } : { role: 'region' })}
        onKeyDown={onKeyDown} style={style}
        className={cn('fixed z-40 flex bg-bg-secondary border-border shadow-xl',
          isMobile ? 'inset-0 flex-col' : right ? 'top-0 right-0 bottom-0 flex-row border-l' : 'left-0 right-0 bottom-0 flex-col border-t')}>
        {grip}
        <div className="flex-1 min-w-0 min-h-0 flex flex-col">
          <div className="shrink-0 flex items-stretch border-b border-border-op50">
            <ObjectTabs opened={opened} activeKey={entry.key} titles={titles} onSelect={setActiveKey} onClose={closeEntity} />
            <div className="shrink-0 flex items-center gap-0.5 px-1">
              {!isMobile && viewport.w >= RIGHT_MIN_VIEWPORT && (
                <button type="button" className={tool} onClick={() => setGeometry({ position: right ? 'bottom' : 'right' })}
                  aria-label={t(right ? 'inspector.dockBottom' : 'inspector.dockRight')} title={t(right ? 'inspector.dockBottom' : 'inspector.dockRight')}>
                  {right ? <Rows size={14} /> : <SidebarSimple size={14} weight="bold" />}
                </button>
              )}
              {!isMobile && (
                <button type="button" className={tool}
                  onClick={() => resizeTo(right ? (grown ? 520 : 720) : (grown ? 380 : Math.min(maxH, 520)))}
                  aria-label={t(grown ? 'inspector.shrink' : 'inspector.grow')} title={t(grown ? 'inspector.shrink' : 'inspector.grow')}>
                  {grown ? <ArrowsInSimple size={14} /> : <ArrowsOutSimple size={14} />}
                </button>
              )}
              <button type="button" className={tool} onClick={closeAll} aria-label={t('inspector.close')} title={t('inspector.close')}>
                <X size={14} />
              </button>
            </div>
          </div>
          <InspectorObject key={entry.key} entry={entry} onTitle={onTitle} />
        </div>
      </aside>
    </>
  )
}
