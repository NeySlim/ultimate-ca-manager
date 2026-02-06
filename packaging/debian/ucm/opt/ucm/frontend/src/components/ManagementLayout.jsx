/**
 * ManagementLayout - Layout for admin/management pages
 * 
 * Desktop: Content panel (left/center) + Item list (right)
 * Mobile: Item cards list, details in BottomSheet or full screen
 * 
 * Use for: Groups, RBAC, SSO, HSM, Users (small lists with management focus)
 */
import { useState } from 'react'
import { cn } from '../lib/utils'
import { labels, getHelpTitle, pluralize } from '../lib/ui'
import { useMobile } from '../contexts'
import { HelpModal } from './HelpModal'
import { EmptyState } from './EmptyState'
import { Button } from './Button'
import { Badge } from './Badge'
import { SearchBar } from './SearchBar'
import { BottomSheet } from './BottomSheet'
import { 
  Question, Plus, CaretRight, CaretLeft, MagnifyingGlass,
  DotsThreeVertical, Trash, PencilSimple
} from '@phosphor-icons/react'

export function ManagementLayout({
  // Page metadata
  title,
  
  // Tabs (optional)
  tabs,
  activeTab,
  onTabChange,
  
  // Data
  items = [],
  loading = false,
  
  // Selection
  selectedItem,
  onSelectItem,
  idKey = 'id',
  
  // Item display
  itemIcon: ItemIcon,
  itemTitle,           // (item) => string
  itemSubtitle,        // (item) => string
  itemBadge,           // (item) => JSX
  renderItem,          // (item, selected) => JSX - custom item render
  
  // Details
  renderDetails,       // (item) => JSX
  detailsTitle,        // Title when showing details
  
  // Actions
  onCreate,
  createLabel = 'Create',
  onEdit,              // (item) => void
  onDelete,            // (item) => void
  
  // Search
  searchable = true,
  searchPlaceholder = 'Search...',
  searchKeys = ['name'],
  
  // Help
  helpContent,
  helpTitle,
  
  // Empty state
  emptyIcon,
  emptyTitle = 'No items',
  emptyDescription = 'Create your first item to get started',
  
  // Footer info
  itemName = 'item',   // For "X items" footer
  
  className
}) {
  const { isMobile } = useMobile()
  const [helpOpen, setHelpOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [listOpen, setListOpen] = useState(true)
  
  // Filter items by search
  const filteredItems = items.filter(item => {
    if (!searchTerm) return true
    const searchLower = searchTerm.toLowerCase()
    return searchKeys.some(key => {
      const value = item[key]
      return value && String(value).toLowerCase().includes(searchLower)
    })
  })
  
  // Help button
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
  
  // Tab component (inline)
  const TabsHeader = tabs?.length > 0 ? (
    <div className="flex gap-1 ml-4">
      {tabs.map(tab => {
        const Icon = tab.icon
        const isActive = activeTab === tab.id
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange?.(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors",
              isActive 
                ? "bg-accent-primary/15 text-accent-primary" 
                : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
            )}
          >
            {Icon && <Icon size={14} />}
            {tab.label}
            {tab.pro && <Badge variant="info" size="sm">Pro</Badge>}
          </button>
        )
      })}
    </div>
  ) : null
  
  // Default item renderer
  const defaultRenderItem = (item, isSelected) => {
    const Icon = ItemIcon
    const titleText = itemTitle ? itemTitle(item) : item.name
    const subtitleText = itemSubtitle ? itemSubtitle(item) : null
    const badge = itemBadge ? itemBadge(item) : null
    
    return (
      <button
        onClick={() => onSelectItem?.(item)}
        className={cn(
          "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150",
          "text-left group",
          isSelected 
            ? "bg-accent-primary/15 border border-accent-primary/30" 
            : "hover:bg-bg-tertiary/80 border border-transparent"
        )}
      >
        {Icon && (
          <div className={cn(
            "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
            isSelected ? "bg-accent-primary/20" : "bg-bg-tertiary"
          )}>
            <Icon 
              size={18} 
              className={isSelected ? "text-accent-primary" : "text-text-secondary"} 
              weight="duotone"
            />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className={cn(
            "text-sm font-medium truncate",
            isSelected ? "text-accent-primary" : "text-text-primary"
          )}>
            {titleText}
          </p>
          {subtitleText && (
            <p className="text-xs text-text-tertiary truncate mt-0.5">
              {subtitleText}
            </p>
          )}
        </div>
        {badge}
        <CaretRight 
          size={14} 
          className={cn(
            "shrink-0 transition-transform",
            isSelected ? "text-accent-primary" : "text-text-tertiary",
            "group-hover:translate-x-0.5"
          )} 
        />
      </button>
    )
  }
  
  // Item list content
  const itemListContent = (
    <div className="flex flex-col h-full">
      {/* Create button */}
      {onCreate && (
        <div className="p-3 border-b border-border shrink-0">
          <Button onClick={onCreate} size="sm" className="w-full">
            <Plus size={16} />
            {createLabel}
          </Button>
        </div>
      )}
      
      {/* Search */}
      {searchable && (
        <div className="p-3 border-b border-border shrink-0">
          <div className="relative">
            <MagnifyingGlass 
              size={14} 
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" 
            />
            <input
              type="text"
              placeholder={searchPlaceholder}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className={cn(
                "w-full pl-8 pr-3 py-2 text-sm rounded-md",
                "bg-bg-tertiary border border-border",
                "text-text-primary placeholder:text-text-tertiary",
                "focus:outline-none focus:ring-1 focus:ring-accent-primary focus:border-accent-primary"
              )}
            />
          </div>
        </div>
      )}
      
      {/* Items list */}
      <div className="flex-1 overflow-auto p-2">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-6 h-6 border-2 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="py-8 text-center">
            <p className="text-sm text-text-tertiary">
              {searchTerm ? 'No matching items' : emptyTitle}
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {filteredItems.map(item => (
              <div key={item[idKey]}>
                {renderItem 
                  ? renderItem(item, selectedItem?.[idKey] === item[idKey])
                  : defaultRenderItem(item, selectedItem?.[idKey] === item[idKey])
                }
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Footer */}
      <div className="px-3 py-2 border-t border-border text-xs text-text-tertiary shrink-0">
        {pluralize(filteredItems.length, itemName)}
      </div>
    </div>
  )
  
  // Details content
  const detailsContent = selectedItem ? (
    renderDetails?.(selectedItem)
  ) : (
    <EmptyState
      icon={emptyIcon || ItemIcon}
      title={`Select ${itemName}`}
      description={`Choose ${itemName === 'item' ? 'an item' : `a ${itemName}`} from the list to view details`}
    />
  )
  
  // Mobile layout
  if (isMobile) {
    return (
      <div className={cn("flex flex-col h-full w-full", className)}>
        {/* Header */}
        <div className="px-4 py-3 border-b border-border bg-bg-secondary shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <h1 className="text-base font-semibold text-text-primary">{title}</h1>
              {TabsHeader}
            </div>
            <div className="flex items-center gap-2">
              {onCreate && (
                <Button onClick={onCreate} size="sm">
                  <Plus size={16} />
                  {createLabel}
                </Button>
              )}
              <HelpButton />
            </div>
          </div>
        </div>
        
        {/* Search */}
        {searchable && (
          <div className="px-4 py-2 border-b border-border bg-bg-secondary shrink-0">
            <div className="relative">
              <MagnifyingGlass 
                size={14} 
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" 
              />
              <input
                type="text"
                placeholder={searchPlaceholder}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className={cn(
                  "w-full pl-8 pr-3 py-2 text-sm rounded-md",
                  "bg-bg-tertiary border border-border",
                  "text-text-primary placeholder:text-text-tertiary",
                  "focus:outline-none focus:ring-1 focus:ring-accent-primary"
                )}
              />
            </div>
          </div>
        )}
        
        {/* Items as cards */}
        <div className="flex-1 overflow-auto p-3">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-2 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
            </div>
          ) : filteredItems.length === 0 ? (
            <EmptyState
              icon={emptyIcon || ItemIcon}
              title={searchTerm ? 'No results' : emptyTitle}
              description={searchTerm ? 'Try a different search term' : emptyDescription}
              action={!searchTerm && onCreate && (
                <Button onClick={onCreate}>
                  <Plus size={16} />
                  {createLabel}
                </Button>
              )}
            />
          ) : (
            <div className="space-y-2">
              {filteredItems.map(item => {
                const Icon = ItemIcon
                const titleText = itemTitle ? itemTitle(item) : item.name
                const subtitleText = itemSubtitle ? itemSubtitle(item) : null
                const badge = itemBadge ? itemBadge(item) : null
                const isSelected = selectedItem?.[idKey] === item[idKey]
                
                return (
                  <button
                    key={item[idKey]}
                    onClick={() => onSelectItem?.(item)}
                    className={cn(
                      "w-full flex items-center gap-3 p-3 rounded-xl transition-all",
                      "bg-bg-secondary border text-left",
                      isSelected 
                        ? "border-accent-primary/50 bg-accent-primary/5" 
                        : "border-border hover:border-border/80"
                    )}
                  >
                    {Icon && (
                      <div className={cn(
                        "w-11 h-11 rounded-xl flex items-center justify-center shrink-0",
                        isSelected ? "bg-accent-primary/20" : "bg-bg-tertiary"
                      )}>
                        <Icon 
                          size={22} 
                          className={isSelected ? "text-accent-primary" : "text-text-secondary"} 
                          weight="duotone"
                        />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className={cn(
                        "text-sm font-medium",
                        isSelected ? "text-accent-primary" : "text-text-primary"
                      )}>
                        {titleText}
                      </p>
                      {subtitleText && (
                        <p className="text-xs text-text-tertiary mt-0.5">
                          {subtitleText}
                        </p>
                      )}
                    </div>
                    {badge}
                    <CaretRight size={16} className="text-text-tertiary shrink-0" />
                  </button>
                )
              })}
            </div>
          )}
        </div>
        
        {/* Footer count */}
        <div className="px-4 py-2 border-t border-border bg-bg-secondary text-xs text-text-tertiary text-center shrink-0">
          {pluralize(filteredItems.length, itemName)}
        </div>
        
        {/* Details BottomSheet */}
        {selectedItem && (
          <BottomSheet
            open={!!selectedItem}
            onOpenChange={(open) => !open && onSelectItem?.(null)}
            title={detailsTitle || (itemTitle ? itemTitle(selectedItem) : 'Details')}
            snapPoints={['50%', '85%']}
            defaultSnap={1}
          >
            {detailsContent}
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
      {/* Content Panel (main area - details) */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border bg-bg-secondary flex items-center justify-between shrink-0">
          <div className="flex items-center">
            <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
            {TabsHeader}
          </div>
          <div className="flex items-center gap-3">
            <HelpButton />
            <button
              onClick={() => setListOpen(!listOpen)}
              className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
              title={listOpen ? "Hide list" : "Show list"}
            >
              {listOpen ? <CaretRight size={16} /> : <CaretLeft size={16} />}
            </button>
          </div>
        </div>
        
        {/* Details Content */}
        <div className="flex-1 overflow-auto p-6">
          {detailsContent}
        </div>
      </div>
      
      {/* Item List Panel (right sidebar) */}
      {listOpen && (
        <div className="w-72 xl:w-80 border-l border-border bg-bg-secondary flex flex-col min-h-0 shrink-0">
          {itemListContent}
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
