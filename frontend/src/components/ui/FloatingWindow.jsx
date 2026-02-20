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
import { useTranslation } from 'react-i18next'
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
  forcePosition = false,
  constraints,
  minimized = false,
  onMinimizeToggle,
  onClose,
  onFocus,
  zIndex = 50,
  title,
  subtitle,
  icon: Icon,
  iconClass = 'bg-accent-primary-op15 text-accent-primary',
  headerActions,
  children,
  className,
}) {
  const { t } = useTranslation()
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
    forcePosition,
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
        'bg-bg-secondary rounded-xl',
        className,
      )}
      style={{
        left: 0, top: 0,
        zIndex,
        transform: `translate3d(${p.x}px, ${p.y}px, 0)`,
        width: p.w,
        height: minimized ? 48 : p.h,
        transition: minimized ? 'height 0.2s ease' : undefined,
        border: '1px solid var(--border-strong)',
        boxShadow: 'var(--floating-window-shadow)',
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
          'shrink-0 flex items-center justify-between gap-2 px-3 py-1.5',
          'border-b border-border-op60 cursor-grab active:cursor-grabbing select-none',
          'rounded-t-xl',
        )}
        style={{ background: 'linear-gradient(135deg, var(--bg-tertiary), var(--bg-secondary))' }}
        onMouseDown={onDragStart}
        onDoubleClick={toggleMaximize}
      >
        <div className="flex items-center gap-2 min-w-0">
          {Icon && (
            <div className={cn('w-6 h-6 rounded-md flex items-center justify-center shrink-0', iconClass.split(' ').find(c => c.startsWith('bg-')) || 'bg-accent-primary-op15')}>
              <Icon size={13} weight="duotone" className={iconClass.split(' ').find(c => c.startsWith('text-')) || 'text-accent-primary'} />
            </div>
          )}
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-text-primary truncate">{title}</h3>
            {!minimized && subtitle && (
              <p className="text-[10px] text-text-tertiary truncate leading-tight">{subtitle}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          {headerActions}
          {onMinimizeToggle && (
            <button
              onClick={(e) => { e.stopPropagation(); onMinimizeToggle() }}
              className="w-6 h-6 rounded flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors"
              title={minimized ? t('windows.expand') : t('windows.minimize')}
            >
              {minimized ? <ArrowsOutSimple size={13} /> : <ArrowsInSimple size={13} />}
            </button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); toggleMaximize() }}
            className="w-6 h-6 rounded flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors"
            title={isMaximized ? t('windows.restore') : t('windows.maximize')}
          >
            {isMaximized ? <CornersIn size={13} /> : <CornersOut size={13} />}
          </button>
          {onClose && (
            <button
              onClick={(e) => { e.stopPropagation(); onClose() }}
              className="w-6 h-6 rounded flex items-center justify-center text-text-tertiary hover:text-status-danger hover:bg-status-danger-op10 transition-colors"
            >
              <X size={13} />
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
