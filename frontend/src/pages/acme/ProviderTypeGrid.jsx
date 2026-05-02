import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MagnifyingGlass } from '@phosphor-icons/react'
import { ProviderIcon, getProviderColor } from '../../components/ProviderIcons'
import { cn } from '../../lib/utils'

export default function ProviderTypeGrid({ label, providers, value, onChange, disabled }) {
  const [search, setSearch] = useState('')
  const { t } = useTranslation()

  const filtered = providers.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.description.toLowerCase().includes(search.toLowerCase())
  )

  const popularOrder = ['cloudflare', 'route53', 'azure', 'gcloud', 'ovh', 'hetzner', 'digitalocean', 'gandi', 'porkbun']
  const manualProvider = filtered.find(p => p.type === 'manual')
  const rfc2136Provider = filtered.find(p => p.type === 'rfc2136')
  const popularProviders = popularOrder
    .map(type => filtered.find(p => p.type === type))
    .filter(Boolean)
  const otherProviders = filtered
    .filter(p => p.type !== 'manual' && p.type !== 'rfc2136' && !popularOrder.includes(p.type))
    .sort((a, b) => a.name.localeCompare(b.name))

  const renderCard = (pt) => {
    const brandColor = getProviderColor(pt.type)
    const isSelected = value === pt.type
    return (
      <button
        key={pt.type}
        type="button"
        disabled={disabled}
        onClick={() => !disabled && onChange(pt.type)}
        className={cn(
          "flex flex-col items-center gap-1.5 p-2.5 rounded-lg border text-center transition-all duration-200 min-h-[72px]",
          "hover:scale-[1.03] hover:shadow-md",
          disabled && "opacity-50 cursor-not-allowed",
          isSelected
            ? "border-accent-primary bg-accent-primary-op10 ring-2 ring-accent-primary-op40 shadow-sm"
            : "border-border-op50 bg-tertiary-op40 hover:border-secondary-op40 hover:bg-tertiary-op70"
        )}
      >
        <span className="w-8 h-8 rounded-lg flex items-center justify-center text-white shadow-sm"
          style={{ backgroundColor: brandColor }}>
          <ProviderIcon type={pt.type} size={18} />
        </span>
        <span className={cn("text-[11px] font-medium leading-tight", isSelected ? "text-accent-primary" : "text-text-primary")}>
          {pt.name}
        </span>
      </button>
    )
  }

  return (
    <div className="space-y-2">
      {label && <label className="block text-sm font-medium text-text-primary">{label}</label>}

      {providers.length > 6 && (
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none" />
          <input
            type="text"
            className="w-full pl-9 pr-3 py-2 border border-border rounded-lg text-sm text-text-primary placeholder:text-text-tertiary outline-none focus:border-accent-primary transition-colors"
            placeholder={t('common.search') + '...'}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      )}

      <div className="max-h-80 overflow-y-auto space-y-2 pr-1 scrollbar-thin">
        {search === '' && (manualProvider || rfc2136Provider) && (
          <div className="grid grid-cols-3 gap-2">
            {manualProvider && renderCard(manualProvider)}
            {rfc2136Provider && renderCard(rfc2136Provider)}
          </div>
        )}
        {search === '' && popularProviders.length > 0 && (
          <>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">{t('common.popular', 'Popular')}</p>
            <div className="grid grid-cols-3 gap-2">
              {popularProviders.map(renderCard)}
            </div>
          </>
        )}
        {search === '' && otherProviders.length > 0 && (
          <>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary pt-1">{t('common.other', 'Other')}</p>
            <div className="grid grid-cols-3 gap-2">
              {otherProviders.map(renderCard)}
            </div>
          </>
        )}
        {search !== '' && (
          <div className="grid grid-cols-3 gap-2">
            {filtered.map(renderCard)}
          </div>
        )}
        {filtered.length === 0 && (
          <p className="text-xs text-text-tertiary text-center py-4">{t('common.noResults', 'No results')}</p>
        )}
      </div>
    </div>
  )
}
