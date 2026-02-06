/**
 * Components - Centralized exports
 * 
 * Main components: ResponsiveLayout + ResponsiveDataTable
 * Detail panels: CompactHeader, CompactSection, CompactGrid, CompactField, CompactStats
 */

// Layout
export { AppShell } from './AppShell'
export { Sidebar } from './Sidebar'
export { BottomSheet } from './BottomSheet'
export { CommandPalette, useKeyboardShortcuts } from './CommandPalette'

// UI Components
export { Card } from './Card'
export { Button } from './Button'
export { Badge, CATypeIcon } from './Badge'
export { IconBadge, IconAvatar } from './IconBadge'
export { TreeView } from './TreeView'
export { SearchBar } from './SearchBar'
export { Modal } from './Modal'
export { Form } from './Form'
export { FormModal, ConfirmModal } from './FormModal'
export { MemberTransferModal } from './MemberTransferModal'
export { Input } from './Input'
export { SelectComponent as Select } from './Select'
export { Select as RadixSelect, FilterSelect, FormSelect } from './ui/Select'
export { Textarea } from './Textarea'
export { DatePicker } from './DatePicker'
export { FileUpload } from './FileUpload'
export { Dropdown } from './Dropdown'
export { ExportDropdown } from './ExportDropdown'
export { TabsComponent as Tabs } from './Tabs'
export { TooltipComponent as Tooltip, HelpTooltip } from './Tooltip'
export { HelpCard } from './HelpCard'
export { HelpModal } from './ui/HelpModal'
export { StatusIndicator } from './StatusIndicator'
export { LoadingSpinner } from './LoadingSpinner'
export { EmptyState } from './EmptyState'
export { Pagination } from './Pagination'
export { Logo } from './Logo'
export { PermissionsDisplay } from './PermissionsDisplay'
export { ErrorBoundary } from './ErrorBoundary'
export { KeyIndicator } from './ui/KeyIndicator'
export { WebSocketIndicator } from './WebSocketIndicator'

// Hooks
export { useAutoPageSize } from '../hooks/useAutoPageSize'

// Detail Card Components - for slide-over panels
export { 
  DetailHeader, 
  DetailSection, 
  DetailGrid, 
  DetailField, 
  DetailDivider,
  DetailContent,
  DetailTabs,
  CompactSection,
  CompactGrid,
  CompactField,
  CompactStats,
  CompactActions,
  CompactHeader
} from './DetailCard'

// Certificate Details (reusable)
export { CertificateDetails } from './CertificateDetails'
export { CertificateCompareModal } from './CertificateCompareModal'
export { TemplatePreviewModal } from './TemplatePreviewModal'
export { CADetails } from './CADetails'
export { CSRDetails } from './CSRDetails'
export { TrustCertDetails } from './TrustCertDetails'

// Filter components
export { FilterPanel, FilterChips, FilterButton } from './FilterPanel'
export { ActionBar, HeaderBar } from './ActionBar'

// Responsive Components - MAIN BUILDING BLOCKS
export { ResponsiveLayout, ResponsiveDataTable } from './ui/responsive'
export { MobileCard, SimpleMobileCard } from './ui/MobileCard'
export { UnifiedPageHeader } from './ui/UnifiedPageHeader'
export { RichStatsBar } from './ui/RichStatsBar'

// Dashboard charts
// Charts are lazy loaded - NOT exported from main bundle
// Import directly: import { CertificateTrendChart, ... } from './DashboardChart'
export { UpdateChecker } from './UpdateChecker'
