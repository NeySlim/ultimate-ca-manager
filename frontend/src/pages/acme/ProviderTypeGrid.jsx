/**
 * The DNS providers to choose from, as the mockup's format cards (`.format-grid` of `.format-option`
 * radios): the brand mark, the name; a search above them past six, the manual and RFC 2136 ones
 * first, then the popular ones, then the others.
 */
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ProviderIcon, getProviderColor } from '../../components/ProviderIcons'

export default function ProviderTypeGrid({ label, providers, value, onChange, disabled }) {
  const [search, setSearch] = useState('')
  const { t } = useTranslation()
  const id = useId().replace(/:/g, '')

  const filtered = providers.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.description.toLowerCase().includes(search.toLowerCase())
  )

  const popularOrder = ['cloudflare', 'route53', 'azure', 'gcloud', 'ovh', 'hetzner', 'digitalocean', 'gandi', 'porkbun', 'tencentcloud']
  const manualProvider = filtered.find(p => p.type === 'manual')
  const rfc2136Provider = filtered.find(p => p.type === 'rfc2136')
  const popularProviders = popularOrder
    .map(type => filtered.find(p => p.type === type))
    .filter(Boolean)
  const otherProviders = filtered
    .filter(p => p.type !== 'manual' && p.type !== 'rfc2136' && !popularOrder.includes(p.type))
    .sort((a, b) => a.name.localeCompare(b.name))

  const renderCard = (pt) => (
    <label key={pt.type} className="format-option">
      <input type="radio" name={`${id}-provider`} value={pt.type} checked={value === pt.type} disabled={disabled} onChange={() => !disabled && onChange(pt.type)} />
      {/* The provider's brand colour behind its mark: a logo, not a theme colour */}
      <span aria-hidden="true" style={{ display: 'inline-grid', placeItems: 'center', width: 26, height: 26, borderRadius: 4, flexShrink: 0, color: 'var(--paper)', backgroundColor: getProviderColor(pt.type) }}>
        <ProviderIcon type={pt.type} size={16} />
      </span>
      <span>{pt.name}</span>
    </label>
  )
  const grid = (list) => <div className="format-grid" style={{ margin: '0 0 6px' }}>{list.map(renderCard)}</div>

  return (
    <fieldset className="field full">
      {label && <legend>{label}</legend>}
      {providers.length > 6 && (
        <>
          <label className="sr-only" htmlFor={`${id}-search`}>{t('common.search')}</label>
          <input id={`${id}-search`} type="search" autoComplete="off" placeholder={t('common.search') + '...'} value={search} onChange={(e) => setSearch(e.target.value)} />
        </>
      )}
      <div role="radiogroup" aria-label={label} style={{ maxHeight: 320, overflow: 'auto' }}>
        {search === '' && (manualProvider || rfc2136Provider) && grid([manualProvider, rfc2136Provider].filter(Boolean))}
        {search === '' && popularProviders.length > 0 && (
          <>
            <p className="small muted">{t('common.popular')}</p>
            {grid(popularProviders)}
          </>
        )}
        {search === '' && otherProviders.length > 0 && (
          <>
            <p className="small muted">{t('common.other')}</p>
            {grid(otherProviders)}
          </>
        )}
        {search !== '' && grid(filtered)}
        {filtered.length === 0 && <p className="small muted">{t('common.noResults', 'No results')}</p>}
      </div>
    </fieldset>
  )
}
