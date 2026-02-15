/**
 * FloatingHelpPanel v3 — Uses shared FloatingWindow shell
 * Desktop: FloatingWindow (drag, resize, minimize, maximize)
 * Mobile: Bottom sheet with swipe-to-close
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  X, ArrowsOutSimple, ArrowsInSimple, BookOpen, Lightbulb,
  Warning, ArrowRight, Sparkle, Info, Link as LinkIcon,
  List, BookBookmark, CaretRight, CaretDown, Code,
  Lightning, CheckCircle, TextAa, Sun, Moon,
  MagnifyingGlass, ArrowsOutLineVertical, ArrowsInLineVertical,
  TextAlignLeft, Rows, Eye
} from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { useMobile } from '../../contexts/MobileContext'
import { useTranslation } from 'react-i18next'
import { helpContent as helpData } from '../../data/helpContent'
import { helpGuides } from '../../data/helpGuides'
import { FloatingWindow } from './FloatingWindow'

const STORAGE_KEY = 'ucm-help-panel'
const READER_KEY = 'ucm-help-reader'

const DEFAULT_READER = { fontSize: 1, contrast: 'normal', spacing: 'compact' }
function loadReaderPrefs() {
  try { return { ...DEFAULT_READER, ...JSON.parse(localStorage.getItem(READER_KEY)) } } catch { return { ...DEFAULT_READER } }
}
function saveReaderPrefs(prefs) {
  try { localStorage.setItem(READER_KEY, JSON.stringify(prefs)) } catch {}
}

const FONT_SIZES = [
  { label: 'S', size: '11px', lineHeight: '1.5' },
  { label: 'M', size: '13px', lineHeight: '1.6' },
  { label: 'L', size: '15px', lineHeight: '1.7' },
]
const CONTRAST_MODES = [
  { key: 'normal', label: 'Normal' },
  { key: 'high', label: 'High' },
  { key: 'sepia', label: 'Sepia' },
]
const SOFT_MAX_W = 600

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
// DESKTOP — Using shared FloatingWindow component
// =============================================================================

function DesktopPanel({ quickContent, guideContent, onClose, t }) {
  const title = quickContent?.title || guideContent?.title || 'Help'
  const subtitle = quickContent?.subtitle || ''

  const defaultPos = {
    x: window.innerWidth - 640 - 24,
    y: window.innerHeight - 580 - 24,
    w: 640, h: 580,
  }

  return (
    <FloatingWindow
      storageKey="ucm-help-panel"
      defaultPos={defaultPos}
      constraints={{ minW: 420, maxW: 1400, minH: 320 }}
      title={title}
      subtitle={subtitle}
      icon={BookOpen}
      iconClass="bg-accent-primary/15 text-accent-primary"
      zIndex={50}
      onClose={onClose}
    >
      <HelpBody quickContent={quickContent} guideContent={guideContent} t={t} isMobileView={false} panelWidth={640} />
    </FloatingWindow>
  )
}

// =============================================================================
// HELP BODY — Tab switching Quick / Guide
// =============================================================================

function HelpBody({ quickContent, guideContent, t, isMobileView, panelWidth }) {
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

      <div className={cn('flex-1 min-h-0', tab === 'quick' ? 'overflow-y-auto' : 'flex flex-col')}>
        {tab === 'quick' && hasQuick && (
          <div className="p-4 space-y-3">
            <QuickHelpContent content={quickContent} t={t} />
          </div>
        )}
        {tab === 'guide' && hasGuide && (
          <GuideContent markdown={guideContent.content} t={t} isMobileView={isMobileView} panelWidth={panelWidth} />
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

function GuideContent({ markdown, t, isMobileView, panelWidth }) {
  const { toc, sections } = useMemo(() => parseMarkdown(markdown), [markdown])
  const [openSections, setOpenSections] = useState(() => new Set(toc.map((_, i) => i)))
  const [readerPrefs, setReaderPrefs] = useState(loadReaderPrefs)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [activeSection, setActiveSection] = useState(0)
  const [tocCollapsed, setTocCollapsed] = useState(false)
  const sectionRefs = useRef({})
  const contentRef = useRef(null)
  const searchRef = useRef(null)

  const updatePref = (key, val) => {
    setReaderPrefs(prev => {
      const next = { ...prev, [key]: val }
      saveReaderPrefs(next)
      return next
    })
  }

  const toggleSection = (idx) => {
    setOpenSections(prev => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  const expandAll = () => setOpenSections(new Set(toc.map((_, i) => i)))
  const collapseAll = () => setOpenSections(new Set())
  const allExpanded = openSections.size === toc.length

  const scrollTo = (idx) => {
    setOpenSections(prev => new Set([...prev, idx]))
    setActiveSection(idx)
    setTimeout(() => {
      sectionRefs.current[idx]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 100)
  }

  // Track active section on scroll
  useEffect(() => {
    const container = contentRef.current
    if (!container) return
    const onScroll = () => {
      const containerTop = container.getBoundingClientRect().top
      let closest = 0
      let closestDist = Infinity
      for (const [idx, el] of Object.entries(sectionRefs.current)) {
        if (!el) continue
        const dist = Math.abs(el.getBoundingClientRect().top - containerTop)
        if (dist < closestDist) { closestDist = dist; closest = parseInt(idx) }
      }
      setActiveSection(closest)
    }
    container.addEventListener('scroll', onScroll, { passive: true })
    return () => container.removeEventListener('scroll', onScroll)
  }, [])

  // Ctrl+F to open search
  useEffect(() => {
    const h = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault()
        setSearchOpen(true)
        setTimeout(() => searchRef.current?.focus(), 50)
      }
      if (e.key === 'Escape' && searchOpen) {
        setSearchOpen(false)
        setSearchQuery('')
      }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [searchOpen])

  // Search highlight via CSS Custom Highlight API (or fallback)
  useEffect(() => {
    const container = contentRef.current
    if (!container) return
    if (!searchQuery || searchQuery.length < 2) {
      // Clear highlights
      if (CSS.highlights) CSS.highlights.delete('search-results')
      return
    }
    if (!CSS.highlights) return // Fallback: no highlight API
    const ranges = []
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
    const query = searchQuery.toLowerCase()
    while (walker.nextNode()) {
      const node = walker.currentNode
      const text = node.textContent.toLowerCase()
      let idx = 0
      while ((idx = text.indexOf(query, idx)) !== -1) {
        const range = new Range()
        range.setStart(node, idx)
        range.setEnd(node, idx + query.length)
        ranges.push(range)
        idx += query.length
      }
    }
    const highlight = new Highlight(...ranges)
    CSS.highlights.set('search-results', highlight)
    // Scroll to first result
    if (ranges.length > 0) {
      const rect = ranges[0].getBoundingClientRect()
      const containerRect = container.getBoundingClientRect()
      if (rect.top < containerRect.top || rect.bottom > containerRect.bottom) {
        const el = ranges[0].startContainer.parentElement
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }
    return () => { if (CSS.highlights) CSS.highlights.delete('search-results') }
  }, [searchQuery])

  const fs = FONT_SIZES[readerPrefs.fontSize]
  // Dynamic font boost: beyond SOFT_MAX_W, each extra 100px = +1px font
  const widthBoost = panelWidth > SOFT_MAX_W ? (panelWidth - SOFT_MAX_W) / 100 : 0
  const baseFontPx = parseFloat(fs.size)
  const effectiveFont = `${(baseFontPx + widthBoost).toFixed(1)}px`
  const effectiveLine = `${(parseFloat(fs.lineHeight) + widthBoost * 0.02).toFixed(2)}`

  const contrastStyles = readerPrefs.contrast === 'high'
    ? { background: 'var(--bg-primary)', color: 'var(--text-primary)', filter: 'contrast(1.2)' }
    : readerPrefs.contrast === 'sepia'
    ? { background: '#f4ecd8', color: '#5b4636' }
    : {}

  const showSidebar = !isMobileView && toc.length > 2 && !tocCollapsed

  return (
    <div className="flex flex-col min-h-0 flex-1">
      {/* Reader Toolbar */}
      <ReaderToolbar
        readerPrefs={readerPrefs}
        updatePref={updatePref}
        allExpanded={allExpanded}
        expandAll={expandAll}
        collapseAll={collapseAll}
        searchOpen={searchOpen}
        setSearchOpen={setSearchOpen}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        searchRef={searchRef}
        tocCollapsed={tocCollapsed}
        setTocCollapsed={setTocCollapsed}
        showSidebarToggle={!isMobileView && toc.length > 2}
        t={t}
      />

      {/* Mobile TOC dropdown */}
      {isMobileView && toc.length > 2 && (
        <MobileTocDropdown toc={toc} activeSection={activeSection} scrollTo={scrollTo} t={t} />
      )}

      {/* Main content area */}
      <div className="flex-1 flex min-h-0">
        {/* Desktop Sidebar TOC */}
        {showSidebar && (
          <div className="w-[150px] shrink-0 border-r border-border overflow-y-auto bg-bg-secondary/30">
            <div className="py-2">
              {toc.map((item, idx) => (
                <button
                  key={idx}
                  onClick={() => scrollTo(idx)}
                  className={cn(
                    'w-full text-left px-3 py-1.5 text-[11px] leading-snug transition-colors border-l-2',
                    activeSection === idx
                      ? 'border-accent-primary text-accent-primary bg-accent-primary/5 font-medium'
                      : 'border-transparent text-text-tertiary hover:text-text-secondary hover:bg-bg-tertiary/50'
                  )}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Scrollable content */}
        <div
          ref={contentRef}
          className="flex-1 overflow-y-auto"
          style={{
            ...contrastStyles,
            fontSize: effectiveFont,
            lineHeight: effectiveLine,
          }}
        >
          {sections.map((section, idx) => (
            <div
              key={idx}
              ref={el => sectionRefs.current[idx] = el}
              className="border-b border-border last:border-b-0"
              style={readerPrefs.contrast === 'sepia' ? { borderColor: '#d4c5a9' } : undefined}
            >
              <button
                onClick={() => toggleSection(idx)}
                className={cn(
                  'w-full flex items-center gap-2 px-4 py-2.5 text-left transition-colors',
                  readerPrefs.contrast === 'sepia' ? 'hover:bg-[#ebe0c8]' : 'hover:bg-bg-tertiary/50'
                )}
              >
                {openSections.has(idx)
                  ? <CaretDown size={12} weight="bold" className={readerPrefs.contrast === 'sepia' ? 'text-[#8b6914] shrink-0' : 'text-accent-primary shrink-0'} />
                  : <CaretRight size={12} weight="bold" className="text-text-tertiary shrink-0" />}
                <span className={cn(
                  'font-semibold',
                  openSections.has(idx)
                    ? (readerPrefs.contrast === 'sepia' ? 'text-[#3d2b1f]' : 'text-text-primary')
                    : 'text-text-secondary'
                )} style={{ fontSize: `calc(${effectiveFont} + 1px)` }}>
                  {section.title}
                </span>
              </button>
              {openSections.has(idx) && (
                <div className={cn('px-4 pb-3', readerPrefs.spacing === 'comfortable' ? 'space-y-3' : '')}>
                  <MarkdownBlock lines={section.lines} searchQuery={searchQuery} contrast={readerPrefs.contrast} />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// READER TOOLBAR — Font size, contrast, spacing, search, expand/collapse
// =============================================================================

function ReaderToolbar({
  readerPrefs, updatePref, allExpanded, expandAll, collapseAll,
  searchOpen, setSearchOpen, searchQuery, setSearchQuery, searchRef,
  tocCollapsed, setTocCollapsed, showSidebarToggle, t
}) {
  return (
    <div className="shrink-0 border-b border-border bg-bg-secondary/40">
      <div className="flex items-center gap-1 px-2 py-1.5 flex-wrap">
        {/* Sidebar toggle */}
        {showSidebarToggle && (
          <ToolbarBtn
            icon={tocCollapsed ? <Rows size={13} /> : <TextAlignLeft size={13} />}
            title={tocCollapsed ? 'Show index' : 'Hide index'}
            active={!tocCollapsed}
            onClick={() => setTocCollapsed(!tocCollapsed)}
          />
        )}

        {showSidebarToggle && <div className="w-px h-4 bg-border mx-0.5" />}

        {/* Font size */}
        <div className="flex items-center gap-0.5 rounded-md border border-border bg-bg-primary">
          {FONT_SIZES.map((f, idx) => (
            <button
              key={idx}
              onClick={() => updatePref('fontSize', idx)}
              className={cn(
                'px-1.5 py-0.5 text-[10px] font-bold transition-colors rounded-sm',
                readerPrefs.fontSize === idx
                  ? 'bg-accent-primary text-white'
                  : 'text-text-tertiary hover:text-text-primary'
              )}
              style={{ fontSize: idx === 0 ? '9px' : idx === 2 ? '12px' : '10px' }}
            >
              A
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-border mx-0.5" />

        {/* Contrast modes */}
        {CONTRAST_MODES.map(mode => (
          <ToolbarBtn
            key={mode.key}
            icon={mode.key === 'normal' ? <Sun size={13} /> : mode.key === 'high' ? <Eye size={13} /> : <Moon size={13} />}
            title={mode.label}
            active={readerPrefs.contrast === mode.key}
            onClick={() => updatePref('contrast', mode.key)}
          />
        ))}

        <div className="w-px h-4 bg-border mx-0.5" />

        {/* Spacing */}
        <ToolbarBtn
          icon={readerPrefs.spacing === 'compact' ? <ArrowsOutLineVertical size={13} /> : <ArrowsInLineVertical size={13} />}
          title={readerPrefs.spacing === 'compact' ? 'Comfortable' : 'Compact'}
          onClick={() => updatePref('spacing', readerPrefs.spacing === 'compact' ? 'comfortable' : 'compact')}
        />

        {/* Expand/Collapse all */}
        <ToolbarBtn
          icon={allExpanded ? <ArrowsInSimple size={13} /> : <ArrowsOutSimple size={13} />}
          title={allExpanded ? 'Collapse all' : 'Expand all'}
          onClick={allExpanded ? collapseAll : expandAll}
        />

        <div className="flex-1" />

        {/* Search */}
        {searchOpen ? (
          <div className="flex items-center gap-1 bg-bg-primary border border-border rounded-md px-1.5">
            <MagnifyingGlass size={12} className="text-text-tertiary shrink-0" />
            <input
              ref={searchRef}
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder={t('common.search', 'Search...')}
              className="bg-transparent text-xs text-text-primary outline-none w-[100px] py-0.5"
            />
            <button onClick={() => { setSearchOpen(false); setSearchQuery('') }}
              className="text-text-tertiary hover:text-text-primary">
              <X size={11} />
            </button>
          </div>
        ) : (
          <ToolbarBtn
            icon={<MagnifyingGlass size={13} />}
            title="Search (Ctrl+F)"
            onClick={() => { setSearchOpen(true); setTimeout(() => searchRef.current?.focus(), 50) }}
          />
        )}
      </div>
    </div>
  )
}

function ToolbarBtn({ icon, title, active, onClick }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn(
        'w-6 h-6 rounded-md flex items-center justify-center transition-colors',
        active
          ? 'bg-accent-primary/15 text-accent-primary'
          : 'text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary'
      )}
    >
      {icon}
    </button>
  )
}

// =============================================================================
// MOBILE TOC DROPDOWN
// =============================================================================

function MobileTocDropdown({ toc, activeSection, scrollTo, t }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="shrink-0 border-b border-border">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-bg-tertiary/50 transition-colors"
      >
        <List size={13} className="text-text-tertiary shrink-0" />
        <span className="text-[11px] font-medium text-text-secondary flex-1 truncate">
          {toc[activeSection] || t('help.tableOfContents', 'Contents')}
        </span>
        {open ? <CaretDown size={11} className="text-text-tertiary" /> : <CaretRight size={11} className="text-text-tertiary" />}
      </button>
      {open && (
        <div className="px-2 pb-2 space-y-0.5">
          {toc.map((item, idx) => (
            <button
              key={idx}
              onClick={() => { scrollTo(idx); setOpen(false) }}
              className={cn(
                'w-full text-left px-3 py-1.5 rounded-md text-[11px] transition-colors',
                activeSection === idx
                  ? 'bg-accent-primary/10 text-accent-primary font-medium'
                  : 'text-text-tertiary hover:bg-bg-tertiary'
              )}
            >
              {item}
            </button>
          ))}
        </div>
      )}
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

function MarkdownBlock({ lines, searchQuery, contrast }) {
  const elements = useMemo(() => renderLines(lines, contrast), [lines, contrast])
  
  // Search highlighting wrapper
  if (searchQuery && searchQuery.length >= 2) {
    return <div className="space-y-2 reader-search-highlight" data-search={searchQuery}>{elements}</div>
  }
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

        <HelpBody quickContent={quickContent} guideContent={guideContent} t={t} isMobileView={true} />
      </div>
    </div>
  )
}

export default FloatingHelpPanel
