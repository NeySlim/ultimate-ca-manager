/**
 * EkuMultiSelect — Pick well-known Extended Key Usage (EKU) OIDs from a
 * dropdown and/or enter custom dotted OIDs (RFC 5280 §4.2.1.12).
 *
 * Props:
 *  - value:       array of dotted OID strings (currently selected extras)
 *  - onChange:    (newValue: string[]) => void
 *  - defaults:    array of dotted OID strings rendered as locked chips (cert_type defaults)
 *  - knownEkus:   [{oid, name}] — catalogue from GET /api/v2/eku/known
 *  - max:         max total extras (default 16)
 *  - disabled
 */
import { useMemo, useState } from 'react'
import { Plus, X, Lock } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'
import { Button } from './Button'

const OID_REGEX = /^[0-2](?:\.(?:0|[1-9]\d*)){1,15}$/
const ANY_EKU = '2.5.29.37.0'

export function EkuMultiSelect({
  value = [],
  onChange,
  defaults = [],
  knownEkus = [],
  max = 16,
  disabled = false,
}) {
  const { t } = useTranslation()
  const [customOid, setCustomOid] = useState('')
  const [customError, setCustomError] = useState('')
  const [picker, setPicker] = useState('')

  const oidToName = useMemo(() => {
    const m = {}
    for (const e of knownEkus) m[e.oid] = e.name
    return m
  }, [knownEkus])

  const labelFor = (oid) => oidToName[oid] || oid

  const remaining = max - value.length

  const addOid = (oid) => {
    const trimmed = (oid || '').trim()
    if (!trimmed) return
    let resolved = trimmed
    // Allow entering a name from the catalogue
    const byName = knownEkus.find(
      (e) => e.name.toLowerCase() === trimmed.toLowerCase()
    )
    if (byName) resolved = byName.oid

    if (!OID_REGEX.test(resolved)) {
      setCustomError(t('certificates.eku.invalidOid'))
      return
    }
    if (resolved === ANY_EKU) {
      setCustomError(t('certificates.eku.anyNotAllowed'))
      return
    }
    if (defaults.includes(resolved) || value.includes(resolved)) {
      setCustomError(t('certificates.eku.alreadyPresent'))
      return
    }
    if (value.length >= max) {
      setCustomError(t('certificates.eku.maxReached', { max }))
      return
    }
    onChange?.([...value, resolved])
    setCustomOid('')
    setCustomError('')
  }

  const removeOid = (oid) => {
    onChange?.(value.filter((o) => o !== oid))
  }

  const handlePickerChange = (e) => {
    const oid = e.target.value
    setPicker('')
    if (oid) addOid(oid)
  }

  const handleCustomKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addOid(customOid)
    }
  }

  // Filter out OIDs already locked or selected from the dropdown
  const availableOptions = knownEkus.filter(
    (e) => !defaults.includes(e.oid) && !value.includes(e.oid)
  )

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-text-primary">
        {t('certificates.eku.title')}
      </label>

      {/* Locked defaults from cert_type */}
      {defaults.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {defaults.map((oid) => (
            <span
              key={oid}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md bg-bg-tertiary border border-border text-text-secondary"
              title={`${labelFor(oid)} (${oid}) — ${t('certificates.eku.defaultLocked')}`}
            >
              <Lock size={12} weight="fill" />
              <span>{labelFor(oid)}</span>
            </span>
          ))}
        </div>
      )}

      {/* Selected extras */}
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((oid) => (
            <span
              key={oid}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md bg-accent-primary-op20 border border-accent-primary text-accent-primary"
              title={oid}
            >
              <span>{labelFor(oid)}</span>
              {oidToName[oid] && (
                <span className="text-text-tertiary font-mono">({oid})</span>
              )}
              <button
                type="button"
                onClick={() => removeOid(oid)}
                disabled={disabled}
                className="hover:text-error"
                aria-label={t('common.remove')}
              >
                <X size={12} weight="bold" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Add controls */}
      <div className="flex flex-col sm:flex-row gap-2">
        {/* Native select keeps things simple and works with FormData-free state */}
        <select
          value={picker}
          onChange={handlePickerChange}
          disabled={disabled || remaining <= 0 || availableOptions.length === 0}
          className="flex-1 px-2.5 py-1.5 bg-tertiary-op80 border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-accent-primary-op50"
        >
          <option value="">{t('certificates.eku.addKnown')}</option>
          {availableOptions.map((e) => (
            <option key={e.oid} value={e.oid}>
              {e.name} ({e.oid})
            </option>
          ))}
        </select>

        <div className="flex flex-1 gap-2">
          <input
            type="text"
            value={customOid}
            onChange={(e) => {
              setCustomOid(e.target.value)
              if (customError) setCustomError('')
            }}
            onKeyDown={handleCustomKeyDown}
            placeholder={t('certificates.eku.customPlaceholder')}
            disabled={disabled || remaining <= 0}
            className="flex-1 px-2.5 py-1.5 bg-tertiary-op80 border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary-op50"
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => addOid(customOid)}
            disabled={disabled || !customOid || remaining <= 0}
          >
            <Plus size={14} weight="bold" />
          </Button>
        </div>
      </div>

      {customError && (
        <p className="text-xs text-error">{customError}</p>
      )}
      <p className="text-xs text-text-tertiary">
        {t('certificates.eku.helper', { remaining })}
      </p>
    </div>
  )
}

export default EkuMultiSelect
