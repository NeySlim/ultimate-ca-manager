/**
 * FloatingHelpPanel — Draggable, resizable help panel
 * Desktop: Floating window, no backdrop, draggable header, resizable edges
 * Mobile: Bottom sheet drawer with swipe-to-close
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { X, ArrowsOutSimple, ArrowsInSimple, BookOpen, Lightbulb, Warning, ArrowRight, Sparkle, Info, Link as LinkIcon } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { useMobile } from '../../contexts/MobileContext'
import { useTranslation } from 'react-i18next'
import { helpContent as helpData } from '../../data/helpContent'

const STORAGE_KEY = 'ucm-help-panel'
const MIN_WIDTH = 360
const MAX_WIDTH = 700
const MIN_HEIGHT = 300
const DEFAULT_WIDTH = 460
const DEFAULT_HEIGHT = 520

function loadPosition() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) return JSON.parse(saved)
  } catch {}
  return null
}

function savePosition(pos) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pos))
  } catch {}
}

export function FloatingHelpPanel({ isOpen, onClose, pageKey, content: contentProp }) {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  
  const content = contentProp || (pageKey ? helpData[pageKey] : null)
  
  if (!isOpen || !content) return null
  
  return isMobile
    ? <MobileSheet content={content} onClose={onClose} t={t} />
    : <DesktopFloating content={content} onClose={onClose} t={t} />
}

// =============================================================================
// DESKTOP — Draggable & Resizable floating panel
// =============================================================================

function DesktopFloating({ content, onClose, t }) {
  const panelRef = useRef(null)
  const [minimized, setMinimized] = useState(false)
  
  // Position & size state
  const [pos, setPos] = useState(() => {
    const saved = loadPosition()
    if (saved) return saved
    return {
      x: window.innerWidth - DEFAULT_WIDTH - 24,
      y: window.innerHeight - DEFAULT_HEIGHT - 24,
      w: DEFAULT_WIDTH,
      h: DEFAULT_HEIGHT,
    }
  })
  
  // Save on change
  useEffect(() => {
    savePosition(pos)
  }, [pos])
  
  // Escape to close
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])
  
  // Clamp to viewport
  const clamp = useCallback((nextPos) => {
    const vw = window.innerWidth
    const vh = window.innerHeight
    return {
      x: Math.max(0, Math.min(nextPos.x, vw - 100)),
      y: Math.max(0, Math.min(nextPos.y, vh - 48)),
      w: Math.max(MIN_WIDTH, Math.min(nextPos.w, MAX_WIDTH)),
      h: Math.max(MIN_HEIGHT, Math.min(nextPos.h, vh - 40)),
    }
  }, [])
  
  // --- DRAG ---
  const dragRef = useRef(null)
  
  const onDragStart = useCallback((e) => {
    e.preventDefault()
    const startX = e.clientX
    const startY = e.clientY
    const startPos = { ...pos }
    
    const onMove = (e) => {
      setPos(clamp({
        ...startPos,
        x: startPos.x + (e.clientX - startX),
        y: startPos.y + (e.clientY - startY),
      }))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [pos, clamp])
  
  // --- RESIZE ---
  const onResizeStart = useCallback((edge, e) => {
    e.preventDefault()
    e.stopPropagation()
    const startX = e.clientX
    const startY = e.clientY
    const startPos = { ...pos }
    
    const onMove = (e) => {
      let next = { ...startPos }
      const dx = e.clientX - startX
      const dy = e.clientY - startY
      
      if (edge.includes('e')) next.w = startPos.w + dx
      if (edge.includes('w')) { next.x = startPos.x + dx; next.w = startPos.w - dx }
      if (edge.includes('s')) next.h = startPos.h + dy
      if (edge.includes('n')) { next.y = startPos.y + dy; next.h = startPos.h - dy }
      
      setPos(clamp(next))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [pos, clamp])
  
  const resizeEdges = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
  const edgeCursors = { n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize', ne: 'nesw-resize', nw: 'nwse-resize', se: 'nwse-resize', sw: 'nesw-resize' }
  const edgeStyles = {
    n:  { top: -3, left: 8, right: 8, height: 6 },
    s:  { bottom: -3, left: 8, right: 8, height: 6 },
    e:  { top: 8, right: -3, bottom: 8, width: 6 },
    w:  { top: 8, left: -3, bottom: 8, width: 6 },
    ne: { top: -3, right: -3, width: 12, height: 12 },
    nw: { top: -3, left: -3, width: 12, height: 12 },
    se: { bottom: -3, right: -3, width: 12, height: 12 },
    sw: { bottom: -3, left: -3, width: 12, height: 12 },
  }

  return (
    <div
      ref={panelRef}
      className={cn(
        'fixed z-50 flex flex-col',
        'bg-bg-primary border border-border rounded-xl',
        'shadow-2xl',
        'animate-in fade-in-0 zoom-in-95 duration-200'
      )}
      style={{
        left: pos.x,
        top: pos.y,
        width: pos.w,
        height: minimized ? 48 : pos.h,
        transition: minimized ? 'height 0.2s ease' : undefined,
      }}
    >
      {/* Resize handles */}
      {!minimized && resizeEdges.map(edge => (
        <div
          key={edge}
          className="absolute z-10"
          style={{ ...edgeStyles[edge], cursor: edgeCursors[edge] }}
          onMouseDown={(e) => onResizeStart(edge, e)}
        />
      ))}
      
      {/* Header — draggable */}
      <div
        className={cn(
          'shrink-0 flex items-center justify-between gap-2 px-3 py-2.5',
          'border-b border-border cursor-grab active:cursor-grabbing select-none',
          'rounded-t-xl bg-bg-secondary/50'
        )}
        onMouseDown={onDragStart}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-accent-primary/15 flex items-center justify-center shrink-0">
            <BookOpen size={14} weight="duotone" className="text-accent-primary" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-text-primary truncate">
              {content.title}
            </h3>
            {!minimized && content.subtitle && (
              <p className="text-[11px] text-text-tertiary truncate">{content.subtitle}</p>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-0.5 shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); setMinimized(!minimized) }}
            className="w-7 h-7 rounded-md flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
            title={minimized ? t('help.expand') : t('help.minimize')}
          >
            {minimized ? <ArrowsOutSimple size={14} /> : <ArrowsInSimple size={14} />}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onClose() }}
            className="w-7 h-7 rounded-md flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>
      
      {/* Content — scrollable */}
      {!minimized && (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <HelpContent content={content} t={t} />
        </div>
      )}
    </div>
  )
}

// =============================================================================
// MOBILE — Bottom sheet
// =============================================================================

function MobileSheet({ content, onClose, t }) {
  const [translateY, setTranslateY] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const startYRef = useRef(0)
  
  const handleTouchStart = useCallback((e) => {
    startYRef.current = e.touches[0].clientY
    setIsDragging(true)
  }, [])
  
  const handleTouchMove = useCallback((e) => {
    if (!isDragging) return
    const diff = e.touches[0].clientY - startYRef.current
    if (diff > 0) setTranslateY(diff)
  }, [isDragging])
  
  const handleTouchEnd = useCallback(() => {
    setIsDragging(false)
    if (translateY > 80) onClose()
    setTranslateY(0)
  }, [translateY, onClose])
  
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])
  
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/40 animate-fade-in" onClick={onClose} />
      <div
        className={cn(
          'absolute inset-x-0 bottom-0 bg-bg-primary rounded-t-2xl',
          'max-h-[75vh] flex flex-col animate-slide-up',
          !isDragging && 'transition-transform'
        )}
        style={{ transform: `translateY(${translateY}px)` }}
      >
        <div
          className="shrink-0 pt-3 pb-2 px-4 cursor-grab"
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
        >
          <div className="w-10 h-1 rounded-full bg-border mx-auto mb-3" />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-accent-primary/15 flex items-center justify-center">
                <BookOpen size={16} weight="duotone" className="text-accent-primary" />
              </div>
              <div>
                <h3 className="font-semibold text-base text-text-primary">{content.title}</h3>
                {content.subtitle && (
                  <p className="text-xs text-text-tertiary">{content.subtitle}</p>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              className="w-9 h-9 rounded-lg flex items-center justify-center text-text-secondary hover:bg-bg-tertiary"
            >
              <X size={18} />
            </button>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto px-4 pb-6 space-y-3">
          <HelpContent content={content} t={t} />
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Shared help content renderer
// =============================================================================

function HelpContent({ content, t }) {
  return (
    <>
      {/* Overview */}
      {content.overview && (
        <div className="p-3 rounded-xl bg-bg-tertiary/50 border border-border">
          <div className="flex items-start gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-accent-25 flex items-center justify-center shrink-0 mt-0.5">
              <Info size={14} weight="duotone" className="text-accent-primary" />
            </div>
            <p className="text-sm text-text-secondary leading-relaxed">
              {content.overview}
            </p>
          </div>
        </div>
      )}

      {/* Sections */}
      {content.sections?.map((section, idx) => (
        <HelpSection key={idx} section={section} />
      ))}

      {/* Tips */}
      {content.tips?.length > 0 && (
        <div className="rounded-xl overflow-hidden border border-border">
          <div className="visual-section-header !py-2">
            <div className="w-6 h-6 rounded-md icon-bg-amber flex items-center justify-center">
              <Lightbulb size={12} weight="fill" />
            </div>
            <span className="text-xs font-semibold">{t('help.proTips')}</span>
          </div>
          <div className="p-3">
            <ul className="space-y-2">
              {content.tips.map((tip, idx) => (
                <li key={idx} className="flex items-start gap-2 text-xs text-text-secondary">
                  <Sparkle size={12} weight="fill" className="text-status-warning mt-0.5 shrink-0" />
                  <span>{tip}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Warnings */}
      {content.warnings?.length > 0 && (
        <div className="rounded-xl overflow-hidden border border-status-danger/30">
          <div className="visual-section-header !py-2" style={{ background: 'color-mix(in srgb, var(--status-danger) 10%, var(--bg-tertiary))' }}>
            <div className="w-6 h-6 rounded-md icon-bg-red flex items-center justify-center">
              <Warning size={12} weight="fill" />
            </div>
            <span className="text-xs font-semibold text-status-danger">{t('common.warnings')}</span>
          </div>
          <div className="p-3">
            <ul className="space-y-2">
              {content.warnings.map((w, idx) => (
                <li key={idx} className="flex items-start gap-2 text-xs text-text-secondary">
                  <span className="w-1.5 h-1.5 rounded-full bg-status-danger mt-1.5 shrink-0" />
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Related */}
      {content.related?.length > 0 && (
        <div className="pt-3 border-t border-border">
          <h4 className="text-[11px] font-semibold text-text-tertiary uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <LinkIcon size={10} weight="bold" />
            {t('help.seeAlso')}
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {content.related.map((item, idx) => (
              <span key={idx} className="px-2.5 py-1 rounded-md bg-bg-tertiary text-[11px] font-medium text-text-secondary border border-border">
                {item}
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  )
}

function HelpSection({ section }) {
  const IconComponent = section.icon
  
  return (
    <div className="rounded-xl overflow-hidden border border-border">
      <div className="visual-section-header !py-2">
        {IconComponent && (
          <span className="w-6 h-6 rounded-md bg-accent-25 flex items-center justify-center">
            <IconComponent size={12} weight="duotone" className="text-accent-primary" />
          </span>
        )}
        <span className="text-xs font-semibold">{section.title}</span>
      </div>

      <div className="p-3">
        {section.content && (
          <p className="text-xs text-text-secondary leading-relaxed mb-2">
            {section.content}
          </p>
        )}

        {section.items && (
          <ul className="space-y-1.5">
            {section.items.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2 text-xs">
                <ArrowRight size={11} weight="bold" className="text-accent-primary mt-0.5 shrink-0" />
                <div>
                  {typeof item === 'object' && item.label && (
                    <span className="font-semibold text-text-primary">{item.label}: </span>
                  )}
                  <span className="text-text-secondary">{typeof item === 'object' ? item.text : item}</span>
                </div>
              </li>
            ))}
          </ul>
        )}

        {section.definitions && (
          <dl className="space-y-1.5">
            {section.definitions.map((def, idx) => (
              <div key={idx} className="flex items-baseline gap-2 text-xs">
                <dt className="font-semibold text-text-primary min-w-[90px] shrink-0">{def.term}</dt>
                <dd className="text-text-secondary">{def.description}</dd>
              </div>
            ))}
          </dl>
        )}

        {section.example && (
          <div className="mt-2 p-2 rounded-lg bg-bg-tertiary border border-border font-mono text-[11px] text-text-secondary overflow-x-auto whitespace-pre-wrap break-all">
            {section.example}
          </div>
        )}
      </div>
    </div>
  )
}

export default FloatingHelpPanel
