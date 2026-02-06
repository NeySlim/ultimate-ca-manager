/**
 * UnifiedManagementLayout - Pattern for management pages (Users, Groups, CAs)
 * 
 * Different from ListPageLayout for better mobile UX:
 * - Desktop: Table + slide-over panel (from right)
 * - Mobile: Table → full-screen detail view (push navigation)
 * 
 * Features:
 * - Tabs support (Users/Groups)
 * - Stats header
 * - Inline row actions
 * - Responsive detail views
 * 
 * Usage:
 * <UnifiedManagementLayout
 *   title="Users"
 *   tabs={[{id, label, icon, pro}]}
 *   activeTab="users"
 *   onTabChange={setActiveTab}
 *   data={users}
 *   columns={columns}
 *   stats={[{label: 'Active', value: 10}]}
 *   selectedItem={selectedUser}
 *   onSelectItem={setSelectedUser}
 *   renderDetails={(user) => <UserDetails user={user} />}
 *   actions={<Button>New User</Button>}
 * />
 */
import { useState, useEffect, useCallback } from 'react'
import { cn } from '../lib/utils'
import { labels, getHelpTitle } from '../lib/ui'
import { useMobile } from '../contexts'
import { ResponsiveDataTable } from './ui/responsive/ResponsiveDataTable'
import { UnifiedPageHeader } from './ui/UnifiedPageHeader'
import { HelpModal } from './HelpModal'
import { Button } from './Button'
import { Badge } from './Badge'
import { 
  X, CaretLeft, ArrowLeft 
} from '@phosphor-icons/react'

export function UnifiedManagementLayout({
  // Page metadata
  title,
  subtitle,              // e.g. "X items"
  icon: Icon,            // Page icon (Phosphor icon component)
  
  // Tabs (optional)
  tabs,                 // [{ id, label, icon, pro }]
  activeTab,
  onTabChange,
  
  // Stats
  stats = [],          // [{ label, value, icon?, variant? }]
  
  // DataTable props
  data = [],
  columns = [],
  loading = false,
  
  // Selection
  selectedItem,
  onSelectItem,
  idKey = 'id',
  
  // Details
  renderDetails,        // (item) => JSX
  detailsTitle,         // Default: "Details"
  
  // Actions
  actions,              // JSX for header
  rowActions,           // (row) => [{ label, icon, onClick, variant }]
  
  // DataTable options
  searchable = true,
  searchPlaceholder,
  searchKeys,
  sortable = true,
  defaultSort,
  paginated = true,
  pageSize = 25,
  pageSizeOptions = [10, 25, 50, 100],
  columnToggle = true,
  
  // Filters
  filters = [],
  
  // Empty state
  emptyIcon,
  emptyTitle,
  emptyDescription,
  emptyAction,
  
  // Help
  helpContent,
  helpTitle,
  
  // Split view (xl+ screens) - panel always visible
  splitView = false,
  splitEmptyContent, // Content to show when nothing selected
  
  // Styling
  className
}) {
  const { isMobile, isLargeScreen } = useMobile()
  const [helpOpen, setHelpOpen] = useState(false)
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false)
  
  // On mobile, when item is selected, show full-screen detail
  useEffect(() => {
    if (isMobile && selectedItem) {
      setMobileDetailOpen(true)
    }
  }, [isMobile, selectedItem])
  
  // Handle back on mobile
  const handleMobileBack = useCallback(() => {
    setMobileDetailOpen(false)
    setTimeout(() => onSelectItem?.(null), 300) // After animation
  }, [onSelectItem])
  
  // Handle row click
  const handleRowClick = useCallback((row) => {
    onSelectItem?.(row)
  }, [onSelectItem])
  
  // Handle close on desktop
  const handleDesktopClose = useCallback(() => {
    onSelectItem?.(null)
  }, [onSelectItem])
  
  // Transform tabs to UnifiedPageHeader format
  const headerTabs = tabs?.map(tab => ({
    id: tab.id,
    label: tab.label,
    icon: tab.icon,
    badge: tab.pro ? { label: 'Pro', variant: 'info' } : undefined
  }))
  
  // Stats bar component (kept for placement flexibility)
  const StatsBar = () => stats.length > 0 ? (
    <div className={cn(
      "flex flex-wrap gap-3 sm:gap-4 border-b border-border bg-bg-secondary/50",
      isMobile ? "px-4 py-2" : "px-6 py-2"
    )}>
      {stats.map((stat, i) => (
        <div key={i} className="flex items-center gap-2">
          {stat.icon && <stat.icon size={14} className="text-text-tertiary" />}
          <span className="text-xs text-text-tertiary">{stat.label}:</span>
          <Badge variant={stat.variant || 'secondary'} size="sm">
            {stat.value}
          </Badge>
        </div>
      ))}
    </div>
  ) : null
  
  // ===================
  // MOBILE LAYOUT
  // ===================
  if (isMobile) {
    return (
      <div className={cn("flex flex-col h-full w-full", className)}>
        {/* Mobile Detail View (full-screen overlay) */}
        <div 
          className={cn(
            "fixed inset-0 z-50 bg-bg-primary flex flex-col transition-transform duration-300 ease-out",
            mobileDetailOpen ? "translate-x-0" : "translate-x-full"
          )}
        >
          {/* Detail Header */}
          <div className="px-4 py-3 border-b border-border bg-bg-secondary flex items-center gap-3 shrink-0">
            <button
              onClick={handleMobileBack}
              className="p-1.5 -ml-1.5 rounded-md hover:bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
            >
              <ArrowLeft size={20} />
            </button>
            <h2 className="text-base font-semibold text-text-primary flex-1 truncate">
              {detailsTitle || 'Details'}
            </h2>
          </div>
          
          {/* Detail Content */}
          <div className="flex-1 overflow-auto">
            {selectedItem && renderDetails?.(selectedItem)}
          </div>
        </div>
        
        {/* Main Content (behind overlay) */}
        <div className={cn(
          "flex flex-col h-full transition-opacity duration-300",
          mobileDetailOpen ? "opacity-50" : "opacity-100"
        )}>
          {/* Header - Using UnifiedPageHeader */}
          <UnifiedPageHeader
            icon={Icon}
            title={title}
            subtitle={subtitle}
            tabs={headerTabs}
            activeTab={activeTab}
            onTabChange={onTabChange}
            showHelp={!!helpContent}
            onHelpClick={() => setHelpOpen(true)}
            isMobile={true}
          />
          <StatsBar />
          
          {/* DataTable */}
          <div className="flex-1 overflow-hidden">
            <ResponsiveDataTable
              data={data}
              columns={columns}
              loading={loading}
              onRowClick={handleRowClick}
              selectedId={selectedItem?.[idKey]}
              rowActions={rowActions}
              searchable={searchable}
              searchPlaceholder={searchPlaceholder}
              searchKeys={searchKeys}
              toolbarFilters={filters}
              toolbarActions={actions}
              sortable={sortable}
              defaultSort={defaultSort}
              emptyIcon={emptyIcon}
              emptyTitle={emptyTitle}
              emptyDescription={emptyDescription}
              emptyAction={emptyAction}
            />
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
  
  // ===================
  // DESKTOP LAYOUT
  // ===================
  return (
    <div className={cn("flex h-full w-full", className)}>
      {/* Main content area */}
      <div className={cn(
        "flex-1 flex flex-col min-w-0 min-h-0 transition-all duration-300",
        selectedItem ? "pr-0" : ""
      )}>
        {/* Header - Using UnifiedPageHeader */}
        <UnifiedPageHeader
          icon={Icon}
          title={title}
          subtitle={subtitle}
          tabs={headerTabs}
          activeTab={activeTab}
          onTabChange={onTabChange}
          showHelp={!!helpContent}
          onHelpClick={() => setHelpOpen(true)}
          isMobile={false}
        />
        <StatsBar />
        
        {/* DataTable */}
        <div className="flex-1 overflow-hidden">
          <ResponsiveDataTable
            data={data}
            columns={columns}
            loading={loading}
            onRowClick={handleRowClick}
            selectedId={selectedItem?.[idKey]}
            rowActions={rowActions}
            searchable={searchable}
            searchPlaceholder={searchPlaceholder}
            searchKeys={searchKeys}
            toolbarFilters={filters}
            toolbarActions={actions}
            sortable={sortable}
            defaultSort={defaultSort}
            emptyIcon={emptyIcon}
            emptyTitle={emptyTitle}
            emptyDescription={emptyDescription}
            emptyAction={emptyAction}
          />
        </div>
      </div>
      
      {/* Slide-over Panel */}
      {(splitView && isLargeScreen) ? (
        // Split view mode - always visible panel (but hidden when no data)
        data.length > 0 ? (
          <div 
            className={cn(
              "border-l border-border bg-bg-secondary/30 flex flex-col shrink-0 overflow-hidden",
              "w-96 xl:w-[420px] 2xl:w-[480px]"
            )}
          >
            {selectedItem ? (
              <>
                {/* Panel Header */}
                <div className="px-4 py-3 border-b border-border flex items-center justify-between shrink-0">
                  <h2 className="text-sm font-semibold text-text-primary">
                    {detailsTitle || 'Details'}
                  </h2>
                  <button
                    onClick={handleDesktopClose}
                    className="p-1 rounded hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary transition-colors"
                  >
                    <X size={16} />
                  </button>
                </div>
                
                {/* Panel Content */}
                <div className="flex-1 overflow-auto">
                  {renderDetails?.(selectedItem)}
                </div>
              </>
            ) : (
              // Empty state when nothing selected
              splitEmptyContent || (
                <div className="h-full flex flex-col items-center justify-center p-6 text-center">
                  <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
                    <Question size={24} className="text-text-tertiary" />
                  </div>
                  <p className="text-sm text-text-secondary">Select an item to view details</p>
                </div>
              )
            )}
          </div>
        ) : null // No panel when data is empty
      ) : (
        // Standard slide-over panel (collapses when nothing selected)
        <div 
          className={cn(
            "border-l border-border bg-bg-secondary flex flex-col shrink-0 transition-all duration-300 overflow-hidden",
            selectedItem 
              ? "w-96 xl:w-[420px] 2xl:w-[480px]" 
              : "w-0 border-l-0"
          )}
        >
          {selectedItem && (
            <>
              {/* Panel Header */}
              <div className="px-4 py-3 border-b border-border flex items-center justify-between shrink-0">
                <h2 className="text-sm font-semibold text-text-primary">
                  {detailsTitle || 'Details'}
                </h2>
                <button
                  onClick={handleDesktopClose}
                  className="p-1 rounded hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary transition-colors"
                >
                  <X size={16} />
                </button>
              </div>
              
              {/* Panel Content */}
              <div className="flex-1 overflow-auto">
                {renderDetails?.(selectedItem)}
              </div>
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
