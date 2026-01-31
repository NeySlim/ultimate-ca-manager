/**
 * Components - Centralized exports
 */

// Layout
export { AppShell } from './AppShell'
export { Sidebar } from './Sidebar'
export { PageLayout, ContentSection, FocusItem } from './PageLayout'
export { ExplorerPanel, ExplorerPanel as FocusPanel } from './ExplorerPanel'
export { DetailsPanel, DetailsPanel as ContentPanel } from './DetailsPanel'
export { BottomSheet } from './BottomSheet'
export { CommandPalette, useKeyboardShortcuts } from './CommandPalette'

// UI Components
export { Card } from './Card'
export { Button } from './Button'
export { Badge } from './Badge'
export { Table } from './Table'
export { AutoTable } from './AutoTable'
export { TreeView } from './TreeView'
export { SearchBar } from './SearchBar'
export { Modal } from './Modal'
export { Form } from './Form'
export { Input } from './Input'
export { SelectComponent as Select } from './Select'
export { Textarea } from './Textarea'
export { DatePicker } from './DatePicker'
export { FileUpload } from './FileUpload'
export { Dropdown } from './Dropdown'
export { ExportDropdown } from './ExportDropdown'
export { TabsComponent as Tabs } from './Tabs'
export { TooltipComponent as Tooltip, HelpTooltip } from './Tooltip'
export { HelpCard } from './HelpCard'
export { HelpModal } from './HelpModal'
export { StatusIndicator } from './StatusIndicator'
export { LoadingSpinner } from './LoadingSpinner'
export { EmptyState } from './EmptyState'
export { Pagination } from './Pagination'
export { Logo } from './Logo'
export { PermissionsDisplay } from './PermissionsDisplay'
export { ErrorBoundary } from './ErrorBoundary'
export { ExplorerItem, ExplorerSection, ExplorerStat, ExplorerInfo } from './ExplorerItem'

// Hooks
export { useAutoPageSize } from '../hooks/useAutoPageSize'

// Responsive Content Components
export { 
  ContentHeader, 
  ContentBody, 
  ContentSection as ResponsiveContentSection, 
  DataGrid, 
  DataField, 
  InfoCard, 
  ActionBar,
  TabsResponsive,
  DetailView 
} from './ResponsiveContent'

// Detail Card Components (Mix Header A + Sections B)
export { 
  DetailHeader, 
  DetailSection, 
  DetailGrid, 
  DetailField, 
  DetailDivider,
  DetailContent,
  DetailTabs,
  // Compact components for slide-over panels
  CompactSection,
  CompactGrid,
  CompactField,
  CompactStats,
  CompactActions,
  CompactHeader
} from './DetailCard'

// Certificate Details (reusable)
export { CertificateDetails } from './CertificateDetails'
export { CADetails } from './CADetails'
export { CSRDetails } from './CSRDetails'
export { TrustCertDetails } from './TrustCertDetails'

// Data Table Components
export { DataTable, SimpleTable, CardGrid } from './DataTable'

// List Page Layout (DataTable + Details Panel)
export { ListPageLayout } from './ListPageLayout'

// Management Layout (Item list + Details for admin pages)
export { ManagementLayout } from './ManagementLayout'
export { TablePageLayout } from './TablePageLayout'
export { UnifiedManagementLayout } from './UnifiedManagementLayout'
export { SlideOverPanel, useSlideOver } from './SlideOverPanel'
