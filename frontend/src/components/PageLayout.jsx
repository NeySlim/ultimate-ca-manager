/**
 * PageLayout Component - Global layout structure for all pages (except login/dashboard)
 * 
 * Structure: [ContentPanel] → [FocusPanel]
 * - ContentPanel: Main content area (left/center)
 * - FocusPanel: List/selection panel (right) - animated slide-over
 * 
 * The Sidebar is handled by AppShell, this component handles the page content area.
 */
import { useState } from 'react'
import { cn } from '../lib/utils'
import { labels, getHelpTitle } from '../lib/ui'
import { Question, X, ArrowLeft } from '@phosphor-icons/react'
import { HelpModal } from './HelpModal'
import { useMobile } from '../contexts'

export function PageLayout({
  // Page metadata
  title,
  
  // Content panel (main area)
  children,
  
  // Focus panel (right sidebar) - animated slide-over
  focusTitle,
  focusContent,
  focusActions,
  focusFooter,
  focusOpen = true,           // Control panel visibility
  onFocusClose,               // Callback when panel closes
  
  // Help modal
  helpContent,
  helpTitle,
  
  // Options
  className
}) {
  const { isMobile } = useMobile()
  const [helpOpen, setHelpOpen] = useState(false)

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

  // Mobile layout - full screen focus panel
  if (isMobile) {
    return (
      <div className={cn("flex flex-col h-full w-full", className)}>
        {/* Full-screen Focus Panel Overlay */}
        {focusContent && (
          <div 
            className={cn(
              "fixed inset-0 z-50 bg-bg-primary flex flex-col",
              "transition-transform duration-300 ease-out",
              focusOpen ? "translate-x-0" : "translate-x-full"
            )}
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-border bg-bg-secondary flex items-center gap-3 shrink-0">
              <button
                onClick={onFocusClose}
                className="p-1.5 -ml-1.5 rounded-md hover:bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
              >
                <ArrowLeft size={20} />
              </button>
              <h2 className="text-base font-semibold text-text-primary flex-1 truncate">
                {focusTitle || 'Details'}
              </h2>
            </div>
            
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
        )}

        {/* Main Content (behind overlay) */}
        <div className={cn(
          "flex flex-col h-full transition-opacity duration-300",
          focusOpen && focusContent ? "opacity-50" : "opacity-100"
        )}>
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
        </div>

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

  // Desktop layout - animated slide-over panel
  return (
    <div className={cn("flex h-full w-full", className)}>
      {/* Content Panel (main area) */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Page Header */}
        <div className="px-6 py-4 border-b border-border bg-bg-secondary flex items-center justify-between shrink-0">
          <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
          <div className="flex items-center gap-3">
            <HelpButton />
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-auto">
          {children}
        </div>
      </div>

      {/* Animated Slide-over Focus Panel */}
      {focusContent !== undefined && (
        <div 
          className={cn(
            "border-l border-border bg-bg-secondary flex flex-col shrink-0",
            "transition-all duration-300 ease-out overflow-hidden",
            focusOpen && focusContent
              ? "w-80 xl:w-96 2xl:w-[420px] min-[1800px]:w-[500px]" 
              : "w-0 border-l-0"
          )}
        >
          {focusOpen && focusContent && (
            <>
              {/* Focus Header */}
              <div className="px-4 py-3 border-b border-border shrink-0">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-text-primary tracking-wide">
                    {focusTitle || 'Selection'}
                  </h2>
                  {onFocusClose && (
                    <button
                      onClick={onFocusClose}
                      className="p-1 rounded hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary transition-colors"
                    >
                      <X size={14} />
                    </button>
                  )}
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
            </>
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
