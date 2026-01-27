/**
 * Explorer Panel Component - Left panel with search and content
 */
import { SearchBar } from './SearchBar'
import { cn } from '../lib/utils'

export function ExplorerPanel({ 
  title, 
  children, 
  searchable = false,
  searchValue,
  onSearch,
  searchPlaceholder = 'Search...',
  footer,
  className 
}) {
  return (
    <div className={cn("w-80 border-r border-border bg-bg-secondary flex flex-col", className)}>
      {/* Header */}
      <div className="px-3 py-2 border-b border-border">
        <h1 className="text-sm font-semibold text-text-primary uppercase tracking-wide">
          {title}
        </h1>
      </div>

      {/* Search */}
      {searchable && (
        <div className="px-2 py-1.5 border-b border-border">
          <SearchBar
            value={searchValue}
            onChange={onSearch}
            placeholder={searchPlaceholder}
          />
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {children}
      </div>

      {/* Footer */}
      {footer && (
        <div className="px-3 py-2 border-t border-border bg-bg-tertiary">
          {footer}
        </div>
      )}
    </div>
  )
}
