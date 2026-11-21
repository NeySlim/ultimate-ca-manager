/**
 * EkuMultiSelect: the Extended Key Usage OIDs a signing adds (RFC 5280 §4.2.1.12), drawn as the
 * issue form's EKU block: `fieldset.field.full`, the locked defaults and the added ones as
 * `.eku-list` check lines (name and OID), a known EKU to add from a native list, a dotted OID typed
 * in `.inline-row`, then the error and the count left.
 *
 * Props:
 *  - value:       array of dotted OID strings (currently selected extras)
 *  - onChange:    (newValue: string[]) => void
 *  - defaults:    array of dotted OID strings the certificate type sets (shown ticked, locked)
 *  - knownEkus:   [{oid, name}] — catalogue from GET /api/v2/eku/known
 *  - max:         max total extras (default 16)
 *  - disabled
 */
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FieldError } from './atelier/SettingsView'

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
  const id = useId().replace(/:/g, '')
  const [customOid, setCustomOid] = useState('')
  const [customError, setCustomError] = useState('')

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
    const byName = knownEkus.find((e) => e.name.toLowerCase() === trimmed.toLowerCase())
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

  const removeOid = (oid) => onChange?.(value.filter((o) => o !== oid))

  // The known EKUs not already locked or added
  const availableOptions = knownEkus.filter((e) => !defaults.includes(e.oid) && !value.includes(e.oid))

  return (
    <fieldset className="field full" aria-describedby={`hint-${id}`}>
      <legend>{t('certificates.eku.title')}</legend>
      {(defaults.length > 0 || value.length > 0) && (
        <div className="eku-list">
          {defaults.map((oid) => (
            // Set by the certificate type: shown ticked, it cannot be taken off (the API only adds)
            <label className="checkbox-line" key={oid} title={t('certificates.eku.defaultLocked')}>
              <input type="checkbox" checked readOnly aria-disabled="true" onClick={(e) => e.preventDefault()} />
              <span>{labelFor(oid)}<small className="mono">{oid}</small></span>
            </label>
          ))}
          {value.map((oid) => (
            <label className="checkbox-line" key={oid}>
              <input type="checkbox" checked disabled={disabled} onChange={() => removeOid(oid)} />
              <span>{labelFor(oid)}<small className="mono">{oid}</small></span>
            </label>
          ))}
        </div>
      )}
      <label className="sr-only" htmlFor={`${id}-known`}>{t('certificates.eku.addKnown')}</label>
      <select id={`${id}-known`} value="" disabled={disabled || remaining <= 0 || availableOptions.length === 0}
        onChange={(e) => { if (e.target.value) addOid(e.target.value) }}>
        <option value="">{t('certificates.eku.addKnown')}</option>
        {availableOptions.map((e) => <option key={e.oid} value={e.oid}>{e.name} ({e.oid})</option>)}
      </select>
      <div className="inline-row">
        <label className="sr-only" htmlFor={`${id}-oid`}>{t('certificates.eku.customPlaceholder')}</label>
        <input id={`${id}-oid`} className="mono" value={customOid} placeholder={t('certificates.eku.customPlaceholder')} autoComplete="off" spellCheck="false"
          disabled={disabled || remaining <= 0} aria-invalid={customError ? 'true' : undefined} aria-describedby={customError ? `err-${id}` : undefined}
          onChange={(e) => { setCustomOid(e.target.value); if (customError) setCustomError('') }}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addOid(customOid) } }} />
        <button type="button" className="btn" disabled={disabled || !customOid || remaining <= 0 || undefined} onClick={() => addOid(customOid)}>{t('common.add')}</button>
      </div>
      {customError && <FieldError id={`err-${id}`} message={customError} />}
      <small id={`hint-${id}`}>{t('certificates.eku.helper', { remaining })}</small>
    </fieldset>
  )
}

export default EkuMultiSelect
