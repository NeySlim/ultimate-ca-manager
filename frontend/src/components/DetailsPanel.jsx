/**
 * Details Panel Component - Right panel with breadcrumb and content
 */
import { CaretRight } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

export function DetailsPanel({ 
  pageTitle,  // Titre de page (pour pages sans ExplorerPanel)
  breadcrumb = [], 
  title,      // Titre dynamique de l'élément sélectionné
  actions,
  children,
  className 
}) {
  return (
    <div className={cn("flex-1 bg-bg-primary flex flex-col min-h-0 min-w-0", className)}>
      {/* Page Header - For pages without ExplorerPanel */}
      {pageTitle && (
        <div className="px-3 py-2 border-b border-border bg-bg-secondary flex-shrink-0">
          <h1 className="text-sm font-semibold text-text-primary uppercase tracking-wide">
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
          <div className="flex items-center justify-between">
            {title && (
              <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
            )}
            {actions && (
              <div className="flex items-center gap-1.5">
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
