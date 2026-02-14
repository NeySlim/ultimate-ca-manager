/**
 * FloatingWindow — Shared draggable/resizable window shell
 * 
 * Used by:
 * - FloatingHelpPanel (help system)
 * - FloatingDetailWindow (detail panels)
 * 
 * Features:
 * - RAF-based drag/resize via useFloatingWindow hook
 * - 8-directional resize handles
 * - Minimize/maximize/close buttons
 * - Double-click header to maximize/restore
 * - Focus management (onClick → onFocus callback)
 */
import { useRef, useEffect } from 'react'
import { X, ArrowsOutSimple, ArrowsInSimple, CornersOut, CornersIn } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import {
  useFloatingWindow,
  EDGES,
  EDGE_CURSORS,
  EDGE_STYLES,
} from '../../hooks/useFloatingWindow'

export function FloatingWindow({
  storageKey,
  defaultPos,
  constraints,
  minimized = false,
  onMinimizeToggle,
  onClose,
  onFocus,
  zIndex = 50,
  title,
  subtitle,
  icon: Icon,
  iconClass = 'bg-accent-primary/15 text-accent-primary',
  headerActions,
  children,
  className,
}) {
  const panelRef = useRef(null)
  const bodyRef = useRef(null)

  const {
    posRef,
    onDragStart,
    onResizeStart,
    toggleMaximize,
    isMaximized,
  } = useFloatingWindow({
    storageKey,
    defaultPos,
    constraints,
    panelRef,
    bodyRef,
    minimized,
  })

  // Escape to close
  useEffect(() => {
    const h = (e) => {
      if (e.key === 'Escape' && onClose) onClose()
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const p = posRef.current

  return (
    <div
      ref={panelRef}
      className={cn(
        'fixed flex flex-col',
        'bg-bg-primary border border-border rounded-xl',
        className,
      )}
      style={{
        left: 0, top: 0,
        zIndex,
        transform: `translate3d(${p.x}px, ${p.y}px, 0)`,
        width: p.w,
        height: minimized ? 48 : p.h,
        transition: minimized ? 'height 0.2s ease' : undefined,
        boxShadow: '0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08)',
      }}
      onMouseDown={onFocus}
    >
      {/* Resize handles */}
      {!minimized && EDGES.map(edge => (
        <div
          key={edge}
          className="absolute z-10"
          style={{ ...EDGE_STYLES[edge], cursor: EDGE_CURSORS[edge] }}
          onMouseDown={(e) => onResizeStart(edge, e)}
        />
      ))}

      {/* Header — draggable */}
      <div
        className={cn(
          'shrink-0 flex items-center justify-between gap-2 px-3 py-2',
          'border-b border-border cursor-grab active:cursor-grabbing select-none',
          'rounded-t-xl bg-bg-secondary/50'
        )}
        onMouseDown={onDragStart}
        onDoubleClick={toggleMaximize}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          {Icon && (
            <div className={cn('w-7 h-7 rounded-lg flex items-center justify-center shrink-0', iconClass.includes('bg-') ? iconClass : `bg-accent-primary/15`)}>
              <Icon size={14} weight="duotone" className={iconClass.includes('text-') ? iconClass.split(' ').find(c => c.startsWith('text-')) : 'text-accent-primary'} />
            </div>
          )}
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-text-primary truncate">{title}</h3>
            {!minimized && subtitle && (
              <p className="text-[11px] text-text-tertiary truncate">{subtitle}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          {headerActions}
          {onMinimizeToggle && (
            <button
              onClick={(e) => { e.stopPropagation(); onMinimizeToggle() }}
              className="w-7 h-7 rounded-md flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
              title={minimized ? 'Expand' : 'Minimize'}
            >
              {minimized ? <ArrowsOutSimple size={14} /> : <ArrowsInSimple size={14} />}
            </button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); toggleMaximize() }}
            className="w-7 h-7 rounded-md flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
            title={isMaximized ? 'Restore' : 'Maximize'}
          >
            {isMaximized ? <CornersIn size={14} /> : <CornersOut size={14} />}
          </button>
          {onClose && (
            <button
              onClick={(e) => { e.stopPropagation(); onClose() }}
              className="w-7 h-7 rounded-md flex items-center justify-center text-text-tertiary hover:text-status-danger hover:bg-status-danger/10 transition-colors"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      {!minimized && (
        <div ref={bodyRef} className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {children}
        </div>
      )}
    </div>
  )
}
