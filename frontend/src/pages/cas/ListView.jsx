/**
 * CAs Page — list/table view (View C)
 */
import { TreeStructure } from '@phosphor-icons/react'
import { CATypeIcon } from '../../components'
import { cn } from '../../lib/utils'
import { CAInfoLine, TypeBadge, HsmBadge, StatusBadge } from './CAListUtils'

// =============================================================================
// VIEW C: LIST — Flat card rows
// =============================================================================

export function ListView({ cas, allCAs, selectedId, onSelect, isMobile, t }) {
  return (
    <div className="rounded-xl border border-border-op60 bg-secondary-op30 overflow-hidden">
      <div className={cn(isMobile ? 'p-1.5 space-y-0.5' : 'p-2 space-y-0.5')}>
        {cas.map(ca => {
          const isSelected = selectedId === ca.id
          const parentCA = ca.parent_id ? allCAs.find(c => c.id === ca.parent_id) : null

          return (
            <div
              key={ca.id}
              onClick={() => onSelect(ca)}
              className={cn(
                'relative rounded-lg cursor-pointer transition-all duration-150',
                'border border-transparent',
                isMobile ? 'px-3 py-2.5' : 'px-3 py-2',
                isSelected
                  ? 'ca-org-child-selected border-accent-primary'
                  : 'hover:bg-bg-tertiary hover:border-border'
              )}
            >
              {isSelected && (
                <div className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r-full bg-accent-primary" />
              )}
              {/* Row 1 */}
              <div className="flex items-center gap-2">
                <CATypeIcon isRoot={ca.type === 'root'} size={isMobile ? 'md' : 'sm'} />
                <span className={cn(
                  'font-semibold truncate flex-1',
                  isMobile ? 'text-sm' : 'text-xs',
                  isSelected ? 'text-accent-primary' : 'text-text-primary'
                )}>
                  {ca.name || ca.common_name || t('cas.unnamedCA')}
                </span>
                <TypeBadge type={ca.type} isMobile={isMobile} t={t} />
                <HsmBadge ca={ca} t={t} />
                <StatusBadge status={ca.status} />
              </div>
              {/* Row 2 */}
              <div className={cn('mt-1 flex items-center gap-2 text-2xs text-text-tertiary', isMobile ? 'ml-9' : 'ml-7')}>
                {parentCA && (
                  <span className="flex items-center gap-1 shrink-0">
                    <TreeStructure size={10} className="text-text-tertiary" />
                    <span className="text-text-secondary truncate max-w-[100px]">{parentCA.name || parentCA.common_name}</span>
                    <span className="text-border">·</span>
                  </span>
                )}
                <CAInfoLine ca={ca} isMobile={isMobile} t={t} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
