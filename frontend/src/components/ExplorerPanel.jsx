/**
 * Explorer Panel Component (aka FocusPanel) - Right panel with list/selection
 * Responsive: Always visible peek bar on mobile, slides up on tap/drag
 */
import { useState } from 'react'
import { SearchBar } from './SearchBar'
import { BottomSheet } from './BottomSheet'
import { HelpModal } from './HelpModal'
import { useMobile } from '../contexts'
import { cn } from '../lib/utils'
import { labels, getHelpTitle } from '../lib/ui'
import { Question } from '@phosphor-icons/react'

export function ExplorerPanel({ 
  title, 
  children, 
  actions,
  searchable = false,
  searchValue,
  onSearch,
  searchPlaceholder = 'Search...',
  footer,
  helpContent,
  helpTitle,
  className
}) {
  const { isMobile, explorerOpen, openExplorer, closeExplorer } = useMobile()
  const [helpOpen, setHelpOpen] = useState(false)

  // Content to render (shared between desktop and mobile)
  const explorerContent = (
    <>
      {/* Actions */}
      {actions && (
        <div className="px-4 py-2 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            {actions}
          </div>
        </div>
      )}

      {/* Search */}
      {searchable && (
        <div className="px-2 py-1.5 border-b border-border flex-shrink-0">
          <SearchBar
            value={searchValue}
            onChange={onSearch}
            placeholder={searchPlaceholder}
          />
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto min-h-0">
        {children}
      </div>

      {/* Footer */}
      {footer && (
        <div className="px-3 py-2 border-t border-border bg-bg-tertiary flex-shrink-0">
          {footer}
        </div>
      )}
    </>
  )

  // Help button component
  const HelpButton = () => helpContent ? (
    <button
      onClick={() => setHelpOpen(true)}
      className={cn(
        "flex items-center gap-1.5 px-2 py-1 rounded-md transition-all duration-200",
        "bg-accent-primary/10 border border-accent-primary/30",
        "text-accent-primary hover:bg-accent-primary/20 hover:border-accent-primary/50",
        "text-xs font-medium"
      )}
      title={labels.helpAndInfo}
    >
      <Question size={14} weight="bold" />
      <span className="hidden sm:inline">{labels.help}</span>
    </button>
  ) : null

  // On mobile, always render bottom sheet (with peek bar visible)
  if (isMobile) {
    return (
      <>
        <BottomSheet
          open={explorerOpen}
          onOpenChange={(open) => open ? openExplorer() : closeExplorer()}
          title={title}
          snapPoints={['35%', '60%', '85%']}
          defaultSnap={1}
          headerAction={<HelpButton />}
        >
          <div className="flex flex-col h-full">
            {explorerContent}
          </div>
        </BottomSheet>
        
        {/* Help Modal */}
        <HelpModal 
          open={helpOpen} 
          onClose={() => setHelpOpen(false)}
          title={helpTitle || getHelpTitle(title)}
        >
          {helpContent}
        </HelpModal>
      </>
    )
  }

  // Desktop: fixed width sidebar
  return (
    <>
      <div className={cn("w-72 border-r border-border bg-bg-secondary flex flex-col min-h-0", className)}>
        {/* Header */}
        <div className="px-4 py-3 border-b border-border flex-shrink-0">
          <div className="flex items-center justify-between">
            <h1 className="text-sm font-semibold text-text-primary tracking-wide">
              {title}
            </h1>
            <HelpButton />
          </div>
        </div>

        {explorerContent}
      </div>
      
      {/* Help Modal */}
      <HelpModal 
        open={helpOpen} 
        onClose={() => setHelpOpen(false)}
        title={helpTitle || getHelpTitle(title)}
      >
        {helpContent}
      </HelpModal>
    </>
  )
}
