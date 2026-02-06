/**
 * Details Panel Component - Right panel with breadcrumb and content
 * On mobile, content displays above the peek bar
 */
import { CaretRight } from '@phosphor-icons/react'
import { useMobile } from '../contexts'
import { cn } from '../lib/utils'

export function DetailsPanel({ 
  pageTitle,
  breadcrumb = [], 
  title,
  actions,
  children,
  className
}) {
  const { isMobile } = useMobile()

  return (
    <div className={cn(
      "flex-1 bg-bg-primary flex flex-col min-h-0 min-w-0",
      isMobile && "pb-14", // Space for peek bar
      className
    )}>
      {/* Page Header */}
      {pageTitle && (
        <div className="px-3 py-2 border-b border-border bg-bg-secondary flex-shrink-0">
          <h1 className="text-sm font-semibold text-text-primary tracking-wide">
            {pageTitle}
          </h1>
        </div>
      )}

      {/* Breadcrumb */}
      {breadcrumb.length > 0 && (
        <div className="px-4 py-2 border-b border-border bg-bg-secondary/50 flex-shrink-0">
          <div className="flex items-center gap-1.5 text-xs">
            {breadcrumb.map((item, index) => (
              <div key={index} className="flex items-center gap-1.5">
                {index > 0 && <CaretRight size={10} className="text-text-secondary" />}
                <span className={cn(
                  index === breadcrumb.length - 1 
                    ? "text-text-primary font-medium" 
                    : "text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
                )}
                  onClick={item.onClick}
                >
                  {item.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Item title and actions */}
      {(title || actions) && (
        <div className="px-4 py-2.5 border-b border-border flex-shrink-0">
          <div className="flex items-center justify-between gap-2">
            {title && (
              <h2 className="text-sm font-semibold text-text-primary truncate">{title}</h2>
            )}
            {actions && (
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {actions}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 min-h-0">
        {children}
      </div>
    </div>
  )
}
