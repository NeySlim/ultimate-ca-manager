/**
 * PageLayout Component - Global layout structure for all pages (except login/dashboard)
 * 
 * Structure: [ContentPanel] → [FocusPanel]
 * - ContentPanel: Main content area (left/center)
 * - FocusPanel: List/selection panel (right) with optional help button
 * 
 * The Sidebar is handled by AppShell, this component handles the page content area.
 */
import { useState } from 'react'
import { cn } from '../lib/utils'
import { labels, getHelpTitle } from '../lib/ui'
import { Question, CaretLeft, CaretRight } from '@phosphor-icons/react'
import { HelpModal } from './HelpModal'
import { useMobile } from '../contexts'
import { BottomSheet } from './BottomSheet'

export function PageLayout({
  // Page metadata
  title,
  
  // Content panel (main area)
  children,
  
  // Focus panel (right sidebar)
  focusTitle,
  focusContent,
  focusActions,
  focusFooter,
  
  // Help modal
  helpContent,
  helpTitle,
  
  // Options
  focusCollapsible = false,
  focusDefaultOpen = true,
  className
}) {
  const { isMobile, explorerOpen, openExplorer, closeExplorer } = useMobile()
  const [helpOpen, setHelpOpen] = useState(false)
  const [focusOpen, setFocusOpen] = useState(focusDefaultOpen)

  // Help button component
  const HelpButton = () => helpContent ? (
    <button
      onClick={() => setHelpOpen(true)}
      className={cn(
        "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md transition-all duration-200",
        "bg-accent-primary/10 border border-accent-primary/30",
        "text-accent-primary hover:bg-accent-primary/20 hover:border-accent-primary/50",
        "text-xs font-medium"
      )}
      title={labels.helpAndInfo}
    >
      <Question size={14} weight="bold" />
      <span>{labels.help}</span>
    </button>
  ) : null

  // Mobile layout
  if (isMobile) {
    return (
      <div className={cn("flex flex-col h-full w-full", className)}>
        {/* Page Header */}
        <div className="px-4 py-3 border-b border-border bg-bg-secondary flex items-center justify-between shrink-0">
          <h1 className="text-base font-semibold text-text-primary">{title}</h1>
          <div className="flex items-center gap-2">
            <HelpButton />
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-auto">
          {children}
        </div>

        {/* Focus Panel as BottomSheet */}
        {focusContent && (
          <BottomSheet
            open={explorerOpen}
            onOpenChange={(open) => open ? openExplorer() : closeExplorer()}
            title={focusTitle || title}
            snapPoints={['35%', '60%', '85%']}
            defaultSnap={1}
          >
            <div className="flex flex-col h-full">
              {/* Actions */}
              {focusActions && (
                <div className="px-4 py-2 border-b border-border flex items-center gap-2 shrink-0">
                  {focusActions}
                </div>
              )}
              
              {/* Content */}
              <div className="flex-1 overflow-auto">
                {focusContent}
              </div>
              
              {/* Footer */}
              {focusFooter && (
                <div className="px-3 py-2 border-t border-border bg-bg-tertiary shrink-0">
                  {focusFooter}
                </div>
              )}
            </div>
          </BottomSheet>
        )}

        {/* Help Modal */}
        <HelpModal 
          open={helpOpen} 
          onClose={() => setHelpOpen(false)}
          title={helpTitle || getHelpTitle(title)}
        >
          {helpContent}
        </HelpModal>
      </div>
    )
  }

  // Desktop layout
  return (
    <div className={cn("flex h-full w-full", className)}>
      {/* Content Panel (main area) */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Page Header */}
        <div className="px-6 py-4 border-b border-border bg-bg-secondary flex items-center justify-between shrink-0">
          <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
          <div className="flex items-center gap-3">
            <HelpButton />
            {focusCollapsible && focusContent && (
              <button
                onClick={() => setFocusOpen(!focusOpen)}
                className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
                title={focusOpen ? "Masquer le panneau" : "Afficher le panneau"}
              >
                {focusOpen ? <CaretRight size={16} /> : <CaretLeft size={16} />}
              </button>
            )}
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-auto">
          {children}
        </div>
      </div>

      {/* Focus Panel (right sidebar) */}
      {focusContent && focusOpen && (
        <div className="w-80 xl:w-96 2xl:w-[420px] min-[1800px]:w-[500px] border-l border-border bg-bg-secondary flex flex-col min-h-0 shrink-0">
          {/* Focus Header */}
          <div className="px-4 py-3 border-b border-border shrink-0">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-primary tracking-wide">
                {focusTitle || 'Selection'}
              </h2>
            </div>
          </div>

          {/* Actions */}
          {focusActions && (
            <div className="px-3 py-2 border-b border-border flex items-center gap-2 shrink-0">
              {focusActions}
            </div>
          )}

          {/* Content */}
          <div className="flex-1 overflow-auto">
            {focusContent}
          </div>

          {/* Footer */}
          {focusFooter && (
            <div className="px-3 py-2 border-t border-border bg-bg-tertiary shrink-0 text-xs text-text-secondary">
              {focusFooter}
            </div>
          )}
        </div>
      )}

      {/* Help Modal */}
      <HelpModal 
        open={helpOpen} 
        onClose={() => setHelpOpen(false)}
        title={helpTitle || getHelpTitle(title)}
      >
        {helpContent}
      </HelpModal>
    </div>
  )
}

/**
 * ContentSection - Styled section within ContentPanel
 */
export function ContentSection({ title, children, className }) {
  return (
    <div className={cn("p-6", className)}>
      {title && (
        <h3 className="text-sm font-semibold text-text-primary mb-4 tracking-wide">
          {title}
        </h3>
      )}
      {children}
    </div>
  )
}

/**
 * FocusItem - Styled item in FocusPanel list
 */
export function FocusItem({ 
  icon: Icon,
  title, 
  subtitle, 
  badge,
  selected, 
  onClick,
  className 
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "p-3 rounded-lg cursor-pointer transition-all duration-200",
        selected 
          ? "bg-accent-primary/10 border border-accent-primary/40 shadow-sm" 
          : "hover:bg-bg-tertiary border border-transparent hover:border-border",
        className
      )}
    >
      <div className="flex items-start gap-2.5">
        {Icon && (
          <div className={cn(
            "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
            selected ? "bg-accent-primary/20" : "bg-bg-tertiary"
          )}>
            <Icon size={16} className={selected ? "text-accent-primary" : "text-text-tertiary"} />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-text-primary truncate">
              {title}
            </span>
            {badge}
          </div>
          {subtitle && (
            <p className="text-[11px] text-text-tertiary mt-0.5 truncate">
              {subtitle}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
