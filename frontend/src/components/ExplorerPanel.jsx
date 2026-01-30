/**
 * Explorer Panel Component - Left panel with search and content
 * Responsive: Always visible peek bar on mobile, slides up on tap/drag
 */
import { SearchBar } from './SearchBar'
import { BottomSheet } from './BottomSheet'
import { useMobile } from '../contexts'
import { cn } from '../lib/utils'

export function ExplorerPanel({ 
  title, 
  children, 
  actions,
  searchable = false,
  searchValue,
  onSearch,
  searchPlaceholder = 'Search...',
  footer,
  className
}) {
  const { isMobile, explorerOpen, openExplorer, closeExplorer } = useMobile()

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
      <div className="flex-1 overflow-auto p-4 min-h-0">
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

  // On mobile, always render bottom sheet (with peek bar visible)
  if (isMobile) {
    return (
      <BottomSheet
        open={explorerOpen}
        onOpenChange={(open) => open ? openExplorer() : closeExplorer()}
        title={title}
        snapPoints={['35%', '60%', '85%']}
        defaultSnap={1}
      >
        <div className="flex flex-col h-full">
          {explorerContent}
        </div>
      </BottomSheet>
    )
  }

  // Desktop: normal sidebar
  return (
    <div className={cn("w-80 lg:w-96 border-r border-border bg-bg-secondary flex flex-col min-h-0", className)}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center justify-between">
          <h1 className="text-sm font-semibold text-text-primary uppercase tracking-wide">
            {title}
          </h1>
        </div>
      </div>

      {explorerContent}
    </div>
  )
}
