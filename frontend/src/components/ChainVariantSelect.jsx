/**
 * ChainVariantSelect — pick which chain a CA or certificate presents when
 * a cross-certificate offers an alternative path (#400).
 * Values: 'auto' (the served chain), 'primary', or 'cross:<id>'.
 */
import { useTranslation } from 'react-i18next'
import { commonNameOf } from '../lib/crossCertificates'

export function variantLabel(variant, t) {
  if (variant.id === 'auto') return t('chainVariant.auto')
  if (variant.id === 'primary') return t('chainVariant.primary')
  let label = t('chainVariant.cross', { name: variant.ca_name || '', issuer: commonNameOf(variant.issuer) })
  if (variant.served) label += ` (${t('chainVariant.served')})`
  if (!variant.servable) label += ` (${t('chainVariant.notServable')})`
  return label
}

export function ChainVariantSelect({ variants, value, onChange, disableUnservable = false, id, className }) {
  const { t } = useTranslation()
  if (!variants || variants.length < 2) return null
  const options = [{ id: 'auto' }, ...variants]
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={className || 'w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm text-text-primary focus:outline-none focus:border-accent-primary'}
    >
      {options.map(v => (
        <option key={v.id} value={v.id} disabled={disableUnservable && v.servable === false && v.id !== value}>
          {variantLabel(v, t)}
        </option>
      ))}
    </select>
  )
}
