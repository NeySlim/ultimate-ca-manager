/**
 * MobileCard - Unified mobile card component for ResponsiveDataTable
 * 
 * Provides consistent styling for mobile list items across all pages.
 * Use via the `renderMobileCard` prop of ResponsiveDataTable, or standalone.
 * 
 * @example
 * // In ResponsiveDataTable:
 * renderMobileCard={(row, isSelected) => (
 *   <MobileCard
 *     icon={Certificate}
 *     iconColor="blue"
 *     title={row.cn}
 *     badge={<Badge variant="success">Valid</Badge>}
 *     subtitle="CA: Root CA"
 *     metadata={[
 *       { label: 'Expires', value: formatDate(row.expires) },
 *       { label: 'Type', value: row.key_type }
 *     ]}
 *     isSelected={isSelected}
 *   />
 * )}
 * 
 * @example
 * // Minimal usage:
 * <MobileCard
 *   icon={User}
 *   title={user.name}
 *   subtitle={user.email}
 * />
 */
import { cn } from '../../lib/utils'
import { IconBadge } from '../IconBadge'

export function MobileCard({
  // Icon (left side)
  icon: Icon,
  iconColor = 'primary',
  iconElement,  // Alternative: pass a custom icon element instead of Icon + iconColor
  
  // Content
  title,
  titleExtra,   // Element to show after title (e.g., KeyIndicator)
  badge,        // Badge element to show on the right of title row
  subtitle,     // Secondary text below title
  metadata = [],  // Array of { label, value } or { icon, value } for bottom row
  
  // Actions
  actions,      // Element for action buttons (usually on right side)
  
  // State
  isSelected = false,
  
  // Styling
  className,
  density = 'default',  // 'compact' | 'default' | 'comfortable'
  onClick,
}) {
  // Density-based styling
  const densityStyles = {
    compact: {
      padding: 'p-2.5',
      gap: 'gap-2',
      iconSize: 'table',  // w-7 h-7
    },
    default: {
      padding: 'p-3',
      gap: 'gap-3',
      iconSize: 'sm',     // w-8 h-8
    },
    comfortable: {
      padding: 'p-4',
      gap: 'gap-4',
      iconSize: 'md',     // w-10 h-10
    }
  }

  const style = densityStyles[density] || densityStyles.default

  return (
    <div
      className={cn(
        style.padding,
        'transition-colors duration-150',
        isSelected && 'mobile-row-selected',
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      {/* Main row: Icon + Content + Badge/Actions */}
      <div className={cn('flex items-start', style.gap)}>
        {/* Icon */}
        {(Icon || iconElement) && (
          <div className="shrink-0">
            {iconElement || (
              <IconBadge 
                icon={Icon} 
                color={iconColor} 
                size={style.iconSize}
                rounded="lg"
              />
            )}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0 flex-1">
              <span className="font-medium text-text-primary truncate">
                {title}
              </span>
              {titleExtra}
            </div>
            {badge && <div className="shrink-0">{badge}</div>}
            {actions && <div className="shrink-0">{actions}</div>}
          </div>

          {/* Subtitle */}
          {subtitle && (
            <p className="text-sm text-text-secondary truncate mt-0.5">
              {subtitle}
            </p>
          )}

          {/* Metadata row */}
          {metadata.length > 0 && (
            <div className="flex items-center gap-3 flex-wrap mt-1.5 text-xs text-text-tertiary">
              {metadata.map((item, idx) => (
                <span key={idx} className="flex items-center gap-1">
                  {item.icon && <item.icon size={12} />}
                  {item.label && <span className="text-text-tertiary">{item.label}:</span>}
                  <span className="text-text-secondary">{item.value}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * SimpleMobileCard - Minimal mobile card without icon
 * Use for simpler lists where icons aren't needed
 */
export function SimpleMobileCard({
  title,
  badge,
  subtitle,
  metadata = [],
  isSelected = false,
  className,
  onClick,
}) {
  return (
    <div
      className={cn(
        'p-3',
        'transition-colors duration-150',
        isSelected && 'mobile-row-selected',
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      {/* Title row */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-text-primary truncate flex-1 min-w-0">
          {title}
        </span>
        {badge && <div className="shrink-0">{badge}</div>}
      </div>

      {/* Subtitle */}
      {subtitle && (
        <p className="text-sm text-text-secondary truncate mt-0.5">
          {subtitle}
        </p>
      )}

      {/* Metadata row */}
      {metadata.length > 0 && (
        <div className="flex items-center gap-3 flex-wrap mt-1.5 text-xs text-text-tertiary">
          {metadata.map((item, idx) => (
            <span key={idx} className="flex items-center gap-1">
              {item.icon && <item.icon size={12} />}
              {item.label && <span>{item.label}:</span>}
              <span className="text-text-secondary">{item.value}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export default MobileCard
