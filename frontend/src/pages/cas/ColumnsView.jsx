/**
 * CAs Page — columns/kanban view (View B)
 */
import { Certificate, ShieldCheck } from '@phosphor-icons/react'
import { CATypeIcon } from '../../components'
import { cn } from '../../lib/utils'
import { formatExpiry, StatusBadge, HsmBadge } from './CAListUtils'

// =============================================================================
// VIEW B: COLUMNS — One column per Root CA
// =============================================================================

export function ColumnsView({ tree, selectedId, onSelect, isMobile, t }) {
  const roots = tree.filter(ca => ca.type === 'root')
  const orphans = tree.filter(ca => ca.type !== 'root')

  if (isMobile) {
    // Mobile: stacked sections
    return (
      <div className="space-y-4">
        {roots.map(root => (
          <div key={root.id} className="space-y-1.5">
            <ColumnHeader ca={root} selectedId={selectedId} onSelect={onSelect} isMobile t={t} />
            {root.children?.map(child => (
              <ColumnChildCard key={child.id} ca={child} selectedId={selectedId} onSelect={onSelect} isMobile t={t} />
            ))}
            {(!root.children || root.children.length === 0) && (
              <div className="text-center py-4 text-xs text-text-tertiary rounded-lg border border-dashed border-border-op50">
                {t('cas.noIntermediate')}
              </div>
            )}
          </div>
        ))}
        {orphans.length > 0 && (
          <div className="space-y-1.5">
            <div className="ca-col-header-orphan rounded-lg px-3 py-2">
              <span className="text-xs font-bold text-text-secondary">{t('cas.orphanCAs')}</span>
            </div>
            {orphans.map(ca => (
              <ColumnChildCard key={ca.id} ca={ca} selectedId={selectedId} onSelect={onSelect} isMobile t={t} isOrphan />
            ))}
          </div>
        )}
      </div>
    )
  }

  // Desktop: side-by-side columns
  return (
    <div className="flex gap-3 overflow-x-auto pb-2" style={{ minHeight: 200 }}>
      {roots.map(root => (
        <div key={root.id} className="ca-col-wrapper flex-1 min-w-[240px] max-w-[400px] flex flex-col rounded-xl border border-border-op60 overflow-hidden">
          <ColumnHeader ca={root} selectedId={selectedId} onSelect={onSelect} isMobile={false} t={t} />
          <div className="flex-1 p-2 space-y-1.5 overflow-y-auto">
            {root.children?.map(child => (
              <ColumnChildCard key={child.id} ca={child} selectedId={selectedId} onSelect={onSelect} isMobile={false} t={t} />
            ))}
            {(!root.children || root.children.length === 0) && (
              <div className="text-center py-6 text-xs text-text-tertiary">
                {t('cas.noIntermediate')}
              </div>
            )}
          </div>
        </div>
      ))}
      {orphans.length > 0 && (
        <div className="ca-col-wrapper flex-1 min-w-[220px] max-w-[300px] flex flex-col rounded-xl border border-dashed border-border-op60 overflow-hidden">
          <div className="ca-col-header-orphan px-3 py-2.5">
            <span className="text-xs font-bold text-text-secondary">{t('cas.orphanCAs')}</span>
          </div>
          <div className="flex-1 p-2 space-y-1.5 overflow-y-auto">
            {orphans.map(ca => (
              <ColumnChildCard key={ca.id} ca={ca} selectedId={selectedId} onSelect={onSelect} isMobile={false} t={t} isOrphan />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ColumnHeader({ ca, selectedId, onSelect, isMobile, t }) {
  const isSelected = selectedId === ca.id
  return (
    <div
      onClick={() => onSelect(ca)}
      className={cn(
        'ca-org-root-header cursor-pointer transition-colors',
        isMobile ? 'px-3 py-2.5 rounded-lg' : 'px-3 py-2.5'
      )}
    >
      <div className="flex items-center gap-2">
        <CATypeIcon isRoot size="sm" />
        <span className={cn(
          'font-bold truncate flex-1',
          isMobile ? 'text-sm' : 'text-xs',
          isSelected ? 'text-accent-primary' : 'text-text-primary'
        )}>
          {ca.name || ca.common_name}
        </span>
        <HsmBadge ca={ca} t={t} />
        <StatusBadge status={ca.status} />
      </div>
      <div className="mt-1 ml-7">
        <div className="flex items-center gap-2 text-2xs text-text-tertiary">
          <span className="flex items-center gap-1">
            <Certificate size={11} weight="duotone" className="text-accent-primary" />
            <span className="font-semibold text-text-secondary">{ca.certs || 0}</span>
          </span>
          <span className="flex items-center gap-1">
            <ShieldCheck size={11} weight="duotone" className="text-text-tertiary" />
            <span className="text-text-secondary">{ca.children?.length || 0} int.</span>
          </span>
        </div>
      </div>
    </div>
  )
}

function ColumnChildCard({ ca, selectedId, onSelect, isMobile, t, isOrphan, depth = 1 }) {
  const isSelected = selectedId === ca.id
  const expiry = formatExpiry(ca.valid_to || ca.not_after, t)
  const hasChildren = ca.children && ca.children.length > 0

  return (
    <div>
      <div
        onClick={() => onSelect(ca)}
        className={cn(
          'rounded-lg border cursor-pointer transition-all duration-150',
          isMobile ? 'px-3 py-2.5' : 'px-2.5 py-2',
          isSelected
            ? 'ca-org-child-selected border-accent-primary'
            : 'border-border-op40 bg-bg-primary hover:border-border hover:shadow-sm',
          isOrphan && 'border-dashed'
        )}
      >
        <div className="flex items-center gap-2">
          <CATypeIcon isRoot={false} size="sm" />
          <span className={cn(
            'font-medium truncate flex-1 text-xs',
            isSelected ? 'text-accent-primary' : 'text-text-primary'
          )}>
            {ca.name || ca.common_name}
          </span>
          <HsmBadge ca={ca} t={t} />
          <StatusBadge status={ca.status} />
        </div>
        <div className="mt-1 ml-7 flex items-center gap-2 text-2xs text-text-tertiary">
          <span className="flex items-center gap-1">
            <Certificate size={10} weight="duotone" className="text-accent-primary" />
            <span className="font-semibold text-text-secondary">{ca.certs || 0}</span>
          </span>
          {expiry && (
            <>
              <span className="text-border">·</span>
              <span className={cn(
                'font-medium',
                expiry.variant === 'danger' ? 'text-status-danger' :
                expiry.variant === 'warning' ? 'text-status-warning' : 'text-text-secondary'
              )}>
                {expiry.text}
              </span>
            </>
          )}
        </div>
      </div>
      {hasChildren && (
        <div className="pl-3 pt-1 space-y-1.5">
          {ca.children.map(child => (
            <ColumnChildCard
              key={child.id}
              ca={child}
              selectedId={selectedId}
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
