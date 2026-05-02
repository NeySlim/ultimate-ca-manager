/**
 * CAs Page — org chart view (View A)
 */
import { CaretRight } from '@phosphor-icons/react'
import { CATypeIcon } from '../../components'
import { cn } from '../../lib/utils'
import { CAInfoLine, StatusBadge, TypeBadge, HsmBadge } from './CAListUtils'

// =============================================================================
// VIEW A: ORGANIGRAMME — Root = big card, children nested inside
// =============================================================================

export function OrgView({ tree, selectedId, expandedNodes, onToggle, onSelect, isMobile, t }) {
  const roots = tree.filter(ca => ca.type === 'root')
  const orphans = tree.filter(ca => ca.type !== 'root')

  return (
    <div className="space-y-3">
      {roots.map(root => (
        <OrgRootCard
          key={root.id}
          ca={root}
          selectedId={selectedId}
          expandedNodes={expandedNodes}
          onToggle={onToggle}
          onSelect={onSelect}
          isMobile={isMobile}
          t={t}
        />
      ))}
      {orphans.length > 0 && (
        <div className="space-y-2">
          <div className="text-2xs font-semibold text-text-tertiary uppercase tracking-wider px-1">
            {t('cas.orphanCAs')}
          </div>
          {orphans.map(ca => (
            <OrgChildCard
              key={ca.id}
              ca={ca}
              selectedId={selectedId}
              onSelect={onSelect}
              isMobile={isMobile}
              t={t}
              isOrphan
            />
          ))}
        </div>
      )}
    </div>
  )
}

function OrgRootCard({ ca, selectedId, expandedNodes, onToggle, onSelect, isMobile, t }) {
  const hasChildren = ca.children && ca.children.length > 0
  const isExpanded = expandedNodes.has(ca.id)
  const isSelected = selectedId === ca.id

  return (
    <div className={cn(
      'rounded-xl border overflow-hidden transition-all duration-200',
      isSelected ? 'border-accent-primary ca-org-root-selected' : 'border-border-op60'
    )}>
      {/* Root header — gradient */}
      <div
        onClick={() => onSelect(ca)}
        className={cn(
          'ca-org-root-header cursor-pointer transition-colors',
          isMobile ? 'px-3 py-3' : 'px-4 py-3'
        )}
      >
        <div className="flex items-center gap-2.5">
          {hasChildren && (
            <button
              onClick={(e) => { e.stopPropagation(); onToggle(ca.id) }}
              className="shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-text-tertiary hover:text-accent-primary hover:bg-tertiary-op50 transition-all"
            >
              <CaretRight
                size={12} weight="bold"
                className={cn('transition-transform duration-200', isExpanded && 'rotate-90')}
              />
            </button>
          )}
          <CATypeIcon isRoot size={isMobile ? 'lg' : 'md'} />
          <div className="flex-1 min-w-0">
            <span className={cn(
              'font-bold truncate block',
              isMobile ? 'text-base' : 'text-sm',
              'text-text-primary'
            )}>
              {ca.name || ca.common_name || t('cas.unnamedCA')}
            </span>
          </div>
          <TypeBadge type="root" isMobile={isMobile} t={t} />
          <HsmBadge ca={ca} t={t} />
          <StatusBadge status={ca.status} />
        </div>
        <div className={cn('mt-1.5', hasChildren ? 'ml-8' : 'ml-0')}>
          <CAInfoLine ca={ca} isMobile={isMobile} t={t} />
        </div>
      </div>

      {/* Children area */}
      {hasChildren && isExpanded && (
        <div className={cn(
          'ca-org-children-area',
          isMobile ? 'px-2 py-2 space-y-1.5' : 'px-3 py-2.5 space-y-1.5'
        )}>
          {ca.children.map(child => (
            <OrgChildCard
              key={child.id}
              ca={child}
              selectedId={selectedId}
              expandedNodes={expandedNodes}
              onToggle={onToggle}
              onSelect={onSelect}
              isMobile={isMobile}
              t={t}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function OrgChildCard({ ca, selectedId, expandedNodes, onToggle, onSelect, isMobile, t, isOrphan, depth = 1 }) {
  const isSelected = selectedId === ca.id
  const hasChildren = ca.children && ca.children.length > 0
  const isExpanded = expandedNodes?.has(ca.id)

  return (
    <div>
      <div
        onClick={() => onSelect(ca)}
        className={cn(
          'rounded-lg border cursor-pointer transition-all duration-150',
          isMobile ? 'px-3 py-2.5' : 'px-3 py-2',
          isSelected
            ? 'ca-org-child-selected border-accent-primary'
            : 'border-border-op50 bg-bg-primary hover:border-border hover:shadow-sm',
          isOrphan && 'border-dashed'
        )}
      >
        <div className="flex items-center gap-2">
          {hasChildren ? (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onToggle(ca.id) }}
              className="shrink-0 w-5 h-5 rounded flex items-center justify-center text-text-tertiary hover:text-accent-primary hover:bg-tertiary-op50 transition-all"
            >
              <CaretRight
                size={10} weight="bold"
                className={cn('transition-transform duration-200', isExpanded && 'rotate-90')}
              />
            </button>
          ) : (
            <div className="w-5" />
          )}
          <CATypeIcon isRoot={false} size={isMobile ? 'md' : 'sm'} />
          <div className="flex-1 min-w-0">
            <span className={cn(
              'font-semibold truncate block',
              isMobile ? 'text-sm' : 'text-xs',
              isSelected ? 'text-accent-primary' : 'text-text-primary'
            )}>
              {ca.name || ca.common_name || t('cas.unnamedCA')}
            </span>
          </div>
          <TypeBadge type="intermediate" isMobile={isMobile} t={t} />
          <HsmBadge ca={ca} t={t} />
          <StatusBadge status={ca.status} />
        </div>
        <div className={cn('mt-1', isMobile ? 'ml-9' : 'ml-7')}>
          <CAInfoLine ca={ca} isMobile={isMobile} t={t} />
        </div>
      </div>
      {hasChildren && isExpanded && (
        <div className={cn('space-y-1.5', isMobile ? 'pl-4 pt-1.5' : 'pl-5 pt-1.5')}>
          {ca.children.map(child => (
            <OrgChildCard
              key={child.id}
              ca={child}
              selectedId={selectedId}
              expandedNodes={expandedNodes}
              onToggle={onToggle}
              onSelect={onSelect}
              isMobile={isMobile}
              t={t}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}
