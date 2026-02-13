/**
 * FloatingHelpPanel v2 — Help system with Quick Help + Guide tabs
 * Desktop: Draggable (RAF-based, no React re-renders), resizable, localStorage
 * Mobile: Bottom sheet with swipe-to-close
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  X, ArrowsOutSimple, ArrowsInSimple, BookOpen, Lightbulb,
  Warning, ArrowRight, Sparkle, Info, Link as LinkIcon,
  List, BookBookmark, CaretRight, CaretDown, Code,
  Lightning, CheckCircle
} from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { useMobile } from '../../contexts/MobileContext'
import { useTranslation } from 'react-i18next'
import { helpContent as helpData } from '../../data/helpContent'
import { helpGuides } from '../../data/helpGuides'

const STORAGE_KEY = 'ucm-help-panel'
const MIN_W = 380
const MAX_W = 720
const MIN_H = 320
const DEF_W = 500
const DEF_H = 560

function loadSaved() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) } catch { return null }
}

export function FloatingHelpPanel({ isOpen, onClose, pageKey }) {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const quickContent = pageKey ? helpData[pageKey] : null
  const guideContent = pageKey ? helpGuides[pageKey] : null

  if (!isOpen || (!quickContent && !guideContent)) return null

  return isMobile
    ? <MobileSheet quickContent={quickContent} guideContent={guideContent} onClose={onClose} t={t} />
    : <DesktopPanel quickContent={quickContent} guideContent={guideContent} onClose={onClose} t={t} />
}

// =============================================================================
// DESKTOP — RAF-based drag & resize (no re-renders during drag)
// =============================================================================

function DesktopPanel({ quickContent, guideContent, onClose, t }) {
  const panelRef = useRef(null)
  const [minimized, setMinimized] = useState(false)
  const posRef = useRef(null)

  // Init position once
  if (!posRef.current) {
    const saved = loadSaved()
    posRef.current = saved || {
      x: window.innerWidth - DEF_W - 24,
      y: window.innerHeight - DEF_H - 24,
      w: DEF_W, h: DEF_H,
    }
  }
  // Force initial render with saved pos
  const [, forceUpdate] = useState(0)

  const applyPos = useCallback(() => {
    const el = panelRef.current
    if (!el) return
    const p = posRef.current
    el.style.left = p.x + 'px'
    el.style.top = p.y + 'px'
    el.style.width = p.w + 'px'
    if (!minimized) el.style.height = p.h + 'px'
  }, [minimized])

  // Apply on mount
  useEffect(() => { applyPos() }, [applyPos])

  // Save to localStorage on close or unmount
  useEffect(() => {
    return () => {
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(posRef.current)) } catch {}
    }
  }, [])

  // Escape to close
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const clamp = useCallback((p) => {
    const vw = window.innerWidth, vh = window.innerHeight
    return {
      x: Math.max(0, Math.min(p.x, vw - 100)),
      y: Math.max(0, Math.min(p.y, vh - 48)),
      w: Math.max(MIN_W, Math.min(p.w, MAX_W)),
      h: Math.max(MIN_H, Math.min(p.h, vh - 40)),
    }
  }, [])

  // --- DRAG (RAF, no setState) ---
  const onDragStart = useCallback((e) => {
    if (e.button !== 0) return
    e.preventDefault()
    const sx = e.clientX, sy = e.clientY
    const sp = { ...posRef.current }
    let raf = 0

    const onMove = (e) => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        posRef.current = clamp({ ...sp, x: sp.x + e.clientX - sx, y: sp.y + e.clientY - sy })
        applyPos()
      })
    }
    const onUp = () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(posRef.current)) } catch {}
      forceUpdate(n => n + 1) // sync React state
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [clamp, applyPos])

  // --- RESIZE (RAF, no setState) ---
  const onResizeStart = useCallback((edge, e) => {
    e.preventDefault()
    e.stopPropagation()
    const sx = e.clientX, sy = e.clientY
    const sp = { ...posRef.current }
    let raf = 0

    const onMove = (e) => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const dx = e.clientX - sx, dy = e.clientY - sy
        let next = { ...sp }
        if (edge.includes('e')) next.w = sp.w + dx
        if (edge.includes('w')) { next.x = sp.x + dx; next.w = sp.w - dx }
        if (edge.includes('s')) next.h = sp.h + dy
        if (edge.includes('n')) { next.y = sp.y + dy; next.h = sp.h - dy }
        posRef.current = clamp(next)
        applyPos()
      })
    }
    const onUp = () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(posRef.current)) } catch {}
      forceUpdate(n => n + 1)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [clamp, applyPos])

  const edges = ['n','s','e','w','ne','nw','se','sw']
  const cursors = { n:'ns-resize', s:'ns-resize', e:'ew-resize', w:'ew-resize', ne:'nesw-resize', nw:'nwse-resize', se:'nwse-resize', sw:'nesw-resize' }
  const eStyles = {
    n:{top:-3,left:8,right:8,height:6}, s:{bottom:-3,left:8,right:8,height:6},
    e:{top:8,right:-3,bottom:8,width:6}, w:{top:8,left:-3,bottom:8,width:6},
    ne:{top:-3,right:-3,width:14,height:14}, nw:{top:-3,left:-3,width:14,height:14},
    se:{bottom:-3,right:-3,width:14,height:14}, sw:{bottom:-3,left:-3,width:14,height:14},
  }

  const p = posRef.current
  const title = quickContent?.title || guideContent?.title || 'Help'
  const subtitle = quickContent?.subtitle || ''

  return (
    <div
      ref={panelRef}
      className={cn(
        'fixed z-50 flex flex-col',
        'bg-bg-primary border border-border rounded-xl shadow-2xl',
        'animate-in fade-in-0 zoom-in-95 duration-200'
      )}
      style={{
        left: p.x, top: p.y, width: p.w,
        height: minimized ? 48 : p.h,
        transition: minimized ? 'height 0.2s ease' : undefined,
        willChange: 'left, top, width, height',
      }}
    >
      {/* Resize handles */}
      {!minimized && edges.map(edge => (
        <div key={edge} className="absolute z-10" style={{ ...eStyles[edge], cursor: cursors[edge] }}
          onMouseDown={(e) => onResizeStart(edge, e)} />
      ))}

      {/* Header — draggable */}
      <div
        className={cn(
          'shrink-0 flex items-center justify-between gap-2 px-3 py-2',
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
            <h3 className="text-sm font-semibold text-text-primary truncate">{title}</h3>
            {!minimized && subtitle && (
              <p className="text-[11px] text-text-tertiary truncate">{subtitle}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          <button onClick={(e) => { e.stopPropagation(); setMinimized(!minimized) }}
            className="w-7 h-7 rounded-md flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
            title={minimized ? t('help.expand') : t('help.minimize')}>
            {minimized ? <ArrowsOutSimple size={14} /> : <ArrowsInSimple size={14} />}
          </button>
          <button onClick={(e) => { e.stopPropagation(); onClose() }}
            className="w-7 h-7 rounded-md flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Body — tabs + content */}
      {!minimized && (
        <HelpBody quickContent={quickContent} guideContent={guideContent} t={t} />
      )}
    </div>
  )
}

// =============================================================================
// HELP BODY — Tab switching Quick / Guide
// =============================================================================

function HelpBody({ quickContent, guideContent, t }) {
  const hasQuick = !!quickContent
  const hasGuide = !!guideContent
  const defaultTab = hasGuide ? 'guide' : 'quick'
  const [tab, setTab] = useState(defaultTab)

  // Only show tabs if both exist
  const showTabs = hasQuick && hasGuide

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {showTabs && (
        <div className="shrink-0 flex border-b border-border bg-bg-secondary/30">
          <button
            onClick={() => setTab('quick')}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors',
              tab === 'quick'
                ? 'text-accent-primary border-b-2 border-accent-primary bg-accent-primary/5'
                : 'text-text-tertiary hover:text-text-secondary'
            )}
          >
            <Lightning size={13} weight={tab === 'quick' ? 'fill' : 'regular'} />
            {t('help.quickHelp', 'Quick Help')}
          </button>
          <button
            onClick={() => setTab('guide')}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors',
              tab === 'guide'
                ? 'text-accent-primary border-b-2 border-accent-primary bg-accent-primary/5'
                : 'text-text-tertiary hover:text-text-secondary'
            )}
          >
            <BookBookmark size={13} weight={tab === 'guide' ? 'fill' : 'regular'} />
            {t('help.guide', 'Guide')}
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {tab === 'quick' && hasQuick && (
          <div className="p-4 space-y-3">
            <QuickHelpContent content={quickContent} t={t} />
          </div>
        )}
        {tab === 'guide' && hasGuide && (
          <GuideContent markdown={guideContent.content} t={t} />
        )}
        {tab === 'guide' && !hasGuide && (
          <div className="p-6 text-center text-xs text-text-tertiary">
            {t('help.guideComingSoon', 'Detailed guide coming soon.')}
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// QUICK HELP — Structured content (same as before, refined)
// =============================================================================

function QuickHelpContent({ content, t }) {
  return (
    <>
      {content.overview && (
        <div className="p-3 rounded-xl bg-bg-tertiary/50 border border-border">
          <div className="flex items-start gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-accent-25 flex items-center justify-center shrink-0 mt-0.5">
              <Info size={14} weight="duotone" className="text-accent-primary" />
            </div>
            <p className="text-sm text-text-secondary leading-relaxed">{content.overview}</p>
          </div>
        </div>
      )}

      {content.sections?.map((section, idx) => (
        <QuickSection key={idx} section={section} />
      ))}

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

function QuickSection({ section }) {
  const Icon = section.icon
  return (
    <div className="rounded-xl overflow-hidden border border-border">
      <div className="visual-section-header !py-2">
        {Icon && (
          <span className="w-6 h-6 rounded-md bg-accent-25 flex items-center justify-center">
            <Icon size={12} weight="duotone" className="text-accent-primary" />
          </span>
        )}
        <span className="text-xs font-semibold">{section.title}</span>
      </div>
      <div className="p-3">
        {section.content && <p className="text-xs text-text-secondary leading-relaxed mb-2">{section.content}</p>}
        {section.items && (
          <ul className="space-y-1.5">
            {section.items.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2 text-xs">
                <ArrowRight size={11} weight="bold" className="text-accent-primary mt-0.5 shrink-0" />
                <div>
                  {typeof item === 'object' && item.label && <span className="font-semibold text-text-primary">{item.label}: </span>}
                  <span className="text-text-secondary">{typeof item === 'object' ? item.text : item}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
        {section.definitions && (
          <dl className="space-y-1.5">
            {section.definitions.map((d, idx) => (
              <div key={idx} className="flex items-baseline gap-2 text-xs">
                <dt className="font-semibold text-text-primary min-w-[90px] shrink-0">{d.term}</dt>
                <dd className="text-text-secondary">{d.description}</dd>
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

// =============================================================================
// GUIDE CONTENT — Markdown renderer with TOC
// =============================================================================

function GuideContent({ markdown, t }) {
  const { toc, sections } = useMemo(() => parseMarkdown(markdown), [markdown])
  const [openSections, setOpenSections] = useState(() => new Set(toc.map((_, i) => i)))
  const sectionRefs = useRef({})

  const toggleSection = (idx) => {
    setOpenSections(prev => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  const scrollTo = (idx) => {
    setOpenSections(prev => new Set([...prev, idx]))
    setTimeout(() => {
      sectionRefs.current[idx]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 100)
  }

  return (
    <div className="flex flex-col min-h-0">
      {/* TOC */}
      {toc.length > 2 && (
        <div className="shrink-0 px-3 py-2 border-b border-border bg-bg-tertiary/30">
          <div className="flex items-center gap-1.5 mb-1.5">
            <List size={12} className="text-text-tertiary" />
            <span className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider">
              {t('help.tableOfContents', 'Contents')}
            </span>
          </div>
          <div className="flex flex-wrap gap-1">
            {toc.map((item, idx) => (
              <button key={idx} onClick={() => scrollTo(idx)}
                className="px-2 py-0.5 rounded text-[10px] text-text-secondary hover:text-accent-primary hover:bg-accent-primary/10 transition-colors truncate max-w-[180px]">
                {item}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Sections */}
      <div className="flex-1 overflow-y-auto">
        {sections.map((section, idx) => (
          <div key={idx} ref={el => sectionRefs.current[idx] = el} className="border-b border-border last:border-b-0">
            <button
              onClick={() => toggleSection(idx)}
              className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-bg-tertiary/50 transition-colors"
            >
              {openSections.has(idx)
                ? <CaretDown size={12} weight="bold" className="text-accent-primary shrink-0" />
                : <CaretRight size={12} weight="bold" className="text-text-tertiary shrink-0" />}
              <span className={cn('text-xs font-semibold', openSections.has(idx) ? 'text-text-primary' : 'text-text-secondary')}>
                {section.title}
              </span>
            </button>
            {openSections.has(idx) && (
              <div className="px-4 pb-3">
                <MarkdownBlock lines={section.lines} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// =============================================================================
// MARKDOWN PARSER — Lightweight, no external deps
// =============================================================================

function parseMarkdown(md) {
  const lines = md.split('\n')
  const toc = []
  const sections = []
  let current = null

  for (const line of lines) {
    const h2 = line.match(/^## (.+)/)
    if (h2) {
      if (current) sections.push(current)
      const title = h2[1].trim()
      toc.push(title)
      current = { title, lines: [] }
      continue
    }
    if (current) {
      current.lines.push(line)
    }
  }
  if (current) sections.push(current)

  // If no h2 sections found, treat entire content as single section
  if (sections.length === 0) {
    sections.push({ title: 'Overview', lines })
    toc.push('Overview')
  }

  return { toc, sections }
}

function MarkdownBlock({ lines }) {
  const elements = useMemo(() => renderLines(lines), [lines])
  return <div className="space-y-2">{elements}</div>
}

function renderLines(lines) {
  const elements = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Empty line
    if (line.trim() === '') { i++; continue }

    // H3 subheading
    const h3 = line.match(/^### (.+)/)
    if (h3) {
      elements.push(
        <h4 key={i} className="text-xs font-semibold text-text-primary mt-3 mb-1 flex items-center gap-1.5">
          <span className="w-1 h-3 rounded-full bg-accent-primary" />
          {formatInline(h3[1].trim())}
        </h4>
      )
      i++; continue
    }

    // H4 subheading
    const h4 = line.match(/^#### (.+)/)
    if (h4) {
      elements.push(
        <h5 key={i} className="text-[11px] font-semibold text-text-secondary mt-2 mb-0.5">
          {formatInline(h4[1].trim())}
        </h5>
      )
      i++; continue
    }

    // Code block
    if (line.trim().startsWith('```')) {
      const codeLines = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      i++ // skip closing ```
      elements.push(
        <pre key={`code-${i}`} className="p-2.5 rounded-lg bg-bg-tertiary border border-border font-mono text-[11px] text-text-secondary overflow-x-auto whitespace-pre leading-relaxed">
          {codeLines.join('\n')}
        </pre>
      )
      continue
    }

    // Blockquote / tip / warning
    if (line.trim().startsWith('> ')) {
      const quoteLines = []
      while (i < lines.length && lines[i].trim().startsWith('> ')) {
        quoteLines.push(lines[i].replace(/^>\s?/, ''))
        i++
      }
      const text = quoteLines.join(' ')
      const isWarning = text.startsWith('⚠') || text.toLowerCase().startsWith('warning')
      const isTip = text.startsWith('💡') || text.toLowerCase().startsWith('tip')
      elements.push(
        <div key={`q-${i}`} className={cn(
          'p-2.5 rounded-lg border text-xs leading-relaxed',
          isWarning ? 'bg-status-danger/5 border-status-danger/20 text-status-danger'
            : isTip ? 'bg-status-warning/5 border-status-warning/20 text-text-secondary'
            : 'bg-accent-primary/5 border-accent-primary/20 text-text-secondary'
        )}>
          {formatInline(text)}
        </div>
      )
      continue
    }

    // Unordered list
    if (line.match(/^[\s]*[-*]\s/)) {
      const listItems = []
      while (i < lines.length && lines[i].match(/^[\s]*[-*]\s/)) {
        listItems.push(lines[i].replace(/^[\s]*[-*]\s/, ''))
        i++
      }
      elements.push(
        <ul key={`ul-${i}`} className="space-y-1">
          {listItems.map((item, j) => (
            <li key={j} className="flex items-start gap-2 text-xs text-text-secondary">
              <span className="w-1 h-1 rounded-full bg-text-tertiary mt-1.5 shrink-0" />
              <span className="leading-relaxed">{formatInline(item)}</span>
            </li>
          ))}
        </ul>
      )
      continue
    }

    // Numbered list
    if (line.match(/^\d+\.\s/)) {
      const listItems = []
      while (i < lines.length && lines[i].match(/^\d+\.\s/)) {
        listItems.push(lines[i].replace(/^\d+\.\s/, ''))
        i++
      }
      elements.push(
        <ol key={`ol-${i}`} className="space-y-1">
          {listItems.map((item, j) => (
            <li key={j} className="flex items-start gap-2 text-xs text-text-secondary">
              <span className="text-[10px] font-semibold text-text-tertiary mt-0.5 min-w-[14px] shrink-0">{j + 1}.</span>
              <span className="leading-relaxed">{formatInline(item)}</span>
            </li>
          ))}
        </ol>
      )
      continue
    }

    // Regular paragraph
    elements.push(
      <p key={i} className="text-xs text-text-secondary leading-relaxed">
        {formatInline(line)}
      </p>
    )
    i++
  }

  return elements
}

// Inline formatting: **bold**, `code`, *italic*
function formatInline(text) {
  if (!text) return text
  const parts = []
  let remaining = text
  let key = 0

  while (remaining.length > 0) {
    // Bold
    const boldMatch = remaining.match(/\*\*(.+?)\*\*/)
    // Code
    const codeMatch = remaining.match(/`([^`]+)`/)
    // Italic
    const italicMatch = remaining.match(/(?<!\*)\*([^*]+)\*(?!\*)/)

    // Find earliest match
    let earliest = null
    let type = null
    for (const [m, t] of [[boldMatch, 'bold'], [codeMatch, 'code'], [italicMatch, 'italic']]) {
      if (m && (earliest === null || m.index < earliest.index)) {
        earliest = m
        type = t
      }
    }

    if (!earliest) {
      parts.push(remaining)
      break
    }

    // Text before match
    if (earliest.index > 0) {
      parts.push(remaining.substring(0, earliest.index))
    }

    if (type === 'bold') {
      parts.push(<strong key={key++} className="font-semibold text-text-primary">{earliest[1]}</strong>)
    } else if (type === 'code') {
      parts.push(<code key={key++} className="px-1 py-0.5 rounded bg-bg-tertiary border border-border font-mono text-[10px]">{earliest[1]}</code>)
    } else if (type === 'italic') {
      parts.push(<em key={key++} className="italic">{earliest[1]}</em>)
    }

    remaining = remaining.substring(earliest.index + earliest[0].length)
  }

  return parts.length === 1 && typeof parts[0] === 'string' ? parts[0] : parts
}

// =============================================================================
// MOBILE — Bottom sheet
// =============================================================================

function MobileSheet({ quickContent, guideContent, onClose, t }) {
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

  const title = quickContent?.title || guideContent?.title || 'Help'
  const subtitle = quickContent?.subtitle || ''

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/40 animate-fade-in" onClick={onClose} />
      <div
        className={cn(
          'absolute inset-x-0 bottom-0 bg-bg-primary rounded-t-2xl',
          'max-h-[80vh] flex flex-col animate-slide-up',
          !isDragging && 'transition-transform'
        )}
        style={{ transform: `translateY(${translateY}px)` }}
      >
        <div className="shrink-0 pt-3 pb-2 px-4 cursor-grab"
          onTouchStart={handleTouchStart} onTouchMove={handleTouchMove} onTouchEnd={handleTouchEnd}>
          <div className="w-10 h-1 rounded-full bg-border mx-auto mb-3" />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-accent-primary/15 flex items-center justify-center">
                <BookOpen size={16} weight="duotone" className="text-accent-primary" />
              </div>
              <div>
                <h3 className="font-semibold text-base text-text-primary">{title}</h3>
                {subtitle && <p className="text-xs text-text-tertiary">{subtitle}</p>}
              </div>
            </div>
            <button onClick={onClose}
              className="w-9 h-9 rounded-lg flex items-center justify-center text-text-secondary hover:bg-bg-tertiary">
              <X size={18} />
            </button>
          </div>
        </div>

        <HelpBody quickContent={quickContent} guideContent={guideContent} t={t} />
      </div>
    </div>
  )
}

export default FloatingHelpPanel
