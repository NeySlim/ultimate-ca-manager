/**
 * ListPageLayout - Global layout for list pages with DataTable
 * 
 * Combines PageLayout + DataTable for consistent list pages:
 * - ContentPanel: DataTable with search, pagination, sort, column toggle
 * - FocusPanel: Selected item details
 * 
 * Usage:
 * <ListPageLayout
 *   title="Certificates"
 *   data={certificates}
 *   columns={columns}
 *   selectedItem={selectedCert}
 *   onSelectItem={setSelectedCert}
 *   renderDetails={(item) => <CertDetails cert={item} />}
 *   actions={<Button>New</Button>}
 *   rowActions={(row) => [...]}
 * />
 */
import { useState } from 'react'
import { cn } from '../lib/utils'
import { labels, getHelpTitle } from '../lib/ui'
import { useMobile } from '../contexts'
import { DataTable } from './DataTable'
import { HelpModal } from './HelpModal'
import { Button } from './Button'
import { Badge } from './Badge'
import { Question, CaretLeft, CaretRight, X } from '@phosphor-icons/react'
import { BottomSheet } from './BottomSheet'

export function ListPageLayout({
  // Page metadata
  title,
  
  // Tabs (optional - for pages with multiple views like Users/Groups)
  tabs,                 // [{ id, label, icon, pro }]
  activeTab,
  onTabChange,
  
  // DataTable props
  data = [],
  columns = [],
  loading = false,
  
  // Selection
  selectedItem,
  onSelectItem,
  idKey = 'id',
  
  // Details panel
  renderDetails,        // (item) => JSX - render selected item details
  detailsTitle,         // Title for details panel (default: "Details")
  detailsEmpty,         // JSX for when no item selected
  
  // Actions
  actions,              // JSX for header actions (New button, etc.)
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
  selectable = false,
  multiSelect = false,
  onSelectionChange,
  variant = 'default',
  
  // Filters
  filters = [],   // [{ key, label, options: [{value, label}] }]
  
  // Hierarchy/Tree
  hierarchical = false,
  parentKey = 'parent_id',
  defaultExpanded = true,
  
  // Empty state
  emptyIcon,
  emptyTitle,
  emptyDescription,
  emptyAction,
  
  // Help
  helpContent,
  helpTitle,
  
  // Styling
  className
}) {
  const { isMobile } = useMobile()
  const [helpOpen, setHelpOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(true)
  
  // Handle row click
  const handleRowClick = (row) => {
    onSelectItem?.(row)
    if (isMobile) {
      // On mobile, details open in bottom sheet automatically
    }
  }
  
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
  
  // Details content
  const detailsContent = selectedItem ? (
    renderDetails?.(selectedItem)
  ) : (
    detailsEmpty || (
      <div className="flex items-center justify-center h-full text-text-secondary p-6">
        <p className="text-sm">Select an item to view details</p>
      </div>
    )
  )
  
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
              {actions}
              <HelpButton />
            </div>
          </div>
        </div>
        
        {/* DataTable */}
        <div className="flex-1 overflow-hidden">
          <DataTable
            data={data}
            columns={columns}
            loading={loading}
            onRowClick={handleRowClick}
            rowActions={rowActions}
            searchable={searchable}
            searchPlaceholder={searchPlaceholder}
            searchKeys={searchKeys}
            sortable={sortable}
            defaultSort={defaultSort}
            paginated={paginated}
            pageSize={pageSize}
            pageSizeOptions={pageSizeOptions}
            columnToggle={columnToggle}
            selectable={selectable}
            multiSelect={multiSelect}
            onSelectionChange={onSelectionChange}
            variant="compact"
            filters={filters}
            hierarchical={hierarchical}
            parentKey={parentKey}
            defaultExpanded={defaultExpanded}
            emptyIcon={emptyIcon}
            emptyTitle={emptyTitle}
            emptyDescription={emptyDescription}
            emptyAction={emptyAction}
          />
        </div>
        
        {/* Details as BottomSheet */}
        {selectedItem && (
          <BottomSheet
            open={!!selectedItem}
            onOpenChange={(open) => !open && onSelectItem?.(null)}
            title={detailsTitle || "Details"}
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
      {/* Main content with DataTable */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border bg-bg-secondary flex items-center justify-between shrink-0">
          <div className="flex items-center">
            <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
            {TabsHeader}
          </div>
          <div className="flex items-center gap-3">
            {actions}
            <HelpButton />
            {renderDetails && (
              <button
                onClick={() => setDetailsOpen(!detailsOpen)}
                className="p-1.5 rounded-md hover:bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
                title={detailsOpen ? "Hide details" : "Show details"}
              >
                {detailsOpen ? <CaretRight size={16} /> : <CaretLeft size={16} />}
              </button>
            )}
          </div>
        </div>
        
        {/* DataTable */}
        <div className="flex-1 overflow-hidden">
          <DataTable
            data={data}
            columns={columns}
            loading={loading}
            onRowClick={handleRowClick}
            rowActions={rowActions}
            searchable={searchable}
            searchPlaceholder={searchPlaceholder}
            searchKeys={searchKeys}
            sortable={sortable}
            defaultSort={defaultSort}
            paginated={paginated}
            pageSize={pageSize}
            pageSizeOptions={pageSizeOptions}
            columnToggle={columnToggle}
            selectable={selectable}
            multiSelect={multiSelect}
            onSelectionChange={onSelectionChange}
            variant={variant}
            filters={filters}
            hierarchical={hierarchical}
            parentKey={parentKey}
            defaultExpanded={defaultExpanded}
            emptyIcon={emptyIcon}
            emptyTitle={emptyTitle}
            emptyDescription={emptyDescription}
            emptyAction={emptyAction}
            rowClassName={(row) => 
              selectedItem && row[idKey] === selectedItem[idKey] 
                ? 'bg-accent-primary/10' 
                : ''
            }
          />
        </div>
      </div>
      
      {/* Details Panel */}
      {renderDetails && detailsOpen && (
        <div className="w-80 xl:w-96 border-l border-border bg-bg-secondary flex flex-col min-h-0 shrink-0">
          {/* Details Header */}
          <div className="px-4 py-3 border-b border-border flex items-center justify-between shrink-0">
            <h2 className="text-sm font-semibold text-text-primary">
              {detailsTitle || 'Details'}
            </h2>
            {selectedItem && (
              <button
                onClick={() => onSelectItem?.(null)}
                className="p-1 rounded hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary"
              >
                <X size={14} />
              </button>
            )}
          </div>
          
          {/* Details Content */}
          <div className="flex-1 overflow-auto">
            {detailsContent}
          </div>
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
