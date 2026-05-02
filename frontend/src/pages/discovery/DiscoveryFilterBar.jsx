import { Globe, ShieldCheck, Warning, WarningCircle, Funnel, XCircle } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'

export default function DiscoveryFilterBar({ statusFilter, setStatusFilter, profileFilter, profiles, handleProfileFilter, setPage, t }) {
  const activeProfile = profiles.find(p => p.id === profileFilter)
  const statusFilters = [
    { id: null, label: t('common.all'), icon: Globe },
    { id: 'managed', label: t('discovery.managed'), icon: ShieldCheck, variant: 'success' },
    { id: 'unmanaged', label: t('discovery.unmanaged'), icon: Warning, variant: 'warning' },
    { id: 'error', label: t('common.error'), icon: WarningCircle, variant: 'danger' },
  ]
  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-border bg-secondary-op50">
      <div className="flex items-center gap-1">
        <Funnel size={13} className="text-text-tertiary mr-0.5" />
        {statusFilters.map(f => (
          <button
            key={f.id ?? 'all'}
            type="button"
            onClick={() => {
              if (f.id === null) { setStatusFilter([]); setPage(1) }
              else {
                setStatusFilter(prev => {
                  if (prev.includes(f.id)) return prev.filter(v => v !== f.id)
                  return [...prev, f.id]
                })
                setPage(1)
              }
            }}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all',
              (f.id === null && statusFilter.length === 0) || (f.id !== null && statusFilter.includes(f.id))
                ? 'bg-accent-primary text-white shadow-sm'
                : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
            )}
          >
            <f.icon size={12} />
            {f.label}
          </button>
        ))}
      </div>

      {profiles.length > 0 && (
        <>
          <div className="w-px h-5 bg-border mx-1" />
          <select
            value={profileFilter ?? ''}
            onChange={(e) => { handleProfileFilter(e.target.value ? parseInt(e.target.value) : null) }}
            className="text-xs bg-bg-secondary border border-border rounded-lg px-2 py-1 text-text-secondary focus:border-accent-primary focus:outline-none"
          >
            <option value="">{t('discovery.allProfiles')}</option>
            {profiles.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </>
      )}

      {(statusFilter.length > 0 || profileFilter) && (
        <>
          <div className="w-px h-5 bg-border mx-1" />
          <button
            type="button"
            onClick={() => { setStatusFilter([]); handleProfileFilter(null); setPage(1) }}
            className="flex items-center gap-1 px-2 py-1 rounded-full text-xs text-accent-primary hover:bg-accent-op10 transition-colors"
          >
            <XCircle size={12} />
            {t('discovery.clearFilters')}
          </button>
          {activeProfile && (
            <span className="text-xs text-text-tertiary">
              {t('discovery.filterByProfile')}: <span className="font-medium text-text-secondary">{activeProfile.name}</span>
            </span>
          )}
        </>
      )}
    </div>
  )
}
